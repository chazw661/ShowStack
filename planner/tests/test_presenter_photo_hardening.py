"""Presenter photo hardening: tenant isolation, upload validation, SSRF, and
the slot writes that used to re-send every headshot.

Same shape as ``test_tenant_isolation``: two mirrored tenants, the session we
drive is project A, and every write aimed at project B must leave B's row
byte-for-byte unchanged. Photos carry ``MARKER_B`` in their payload so a leak
is a plain substring match.

Run with::

    python manage.py test planner.tests.test_presenter_photo_hardening \\
        --settings=audiopatch.test_settings
"""

import base64
import json
import shutil
import tempfile
from io import BytesIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, SimpleTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from PIL import Image
from urllib3._collections import HTTPHeaderDict

from planner.models import Presenter, PresenterSlot, ProjectMember, UserProfile
from planner.tests.test_tenant_isolation import TenantIsolationBase
from planner.utils import safe_fetch
from planner.utils.image_upload import MAX_PHOTO_BYTES
from planner.utils.safe_fetch import UnsafeFetchError, fetch_public


# ---------------------------------------------------------------------------
# Image fixtures
# ---------------------------------------------------------------------------

def _image_bytes(fmt, size=(4, 4), mode='RGB'):
    buf = BytesIO()
    Image.new(mode, size, (200, 10, 10) if mode == 'RGB' else 0).save(buf, format=fmt)
    return buf.getvalue()


PNG = _image_bytes('PNG')
JPEG = _image_bytes('JPEG')
WEBP = _image_bytes('WEBP')
GIF = _image_bytes('GIF')
SVG = (b'<svg xmlns="http://www.w3.org/2000/svg">'
       b'<script>alert(1)</script></svg>')
HTML = b'<html><body><script>alert(document.cookie)</script></body></html>'


def _data_url(mime, raw):
    return f'data:{mime};base64,{base64.b64encode(raw).decode()}'


def _queries_touching_photo(ctx):
    return [q['sql'] for q in ctx.captured_queries if 'photo_data' in q['sql']]


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

class PhotoTenantBase(TenantIsolationBase):
    """Adds a photo'd presenter slot to each tenant, and an A viewer/editor."""

    def setUp(self):
        super().setUp()
        self.photo_a = _data_url('image/png', b'AAA-photo-bytes')
        self.photo_b = _data_url('image/png', f'{self.MARKER_B}-photo-bytes'.encode())
        for tag in ('a', 'b'):
            assignment = getattr(self, f'mic_assignment_{tag}')
            project = getattr(self, f'project_{tag}')
            mark = self.MARKER_B if tag == 'b' else 'AAA'
            presenter = Presenter.objects.create(project=project, name=f'Presenter {mark}')
            slot = assignment.presenter_slots.order_by('order').first()
            if slot is None:
                slot = PresenterSlot.objects.create(assignment=assignment, order=0)
            slot.presenter = presenter
            slot.is_active = True
            slot.photo_data = getattr(self, f'photo_{tag}')
            slot.save()
            setattr(self, f'presenter_{tag}', presenter)
            setattr(self, f'slot_{tag}', slot)

        self.viewer = self._member('viewer_a', 'viewer')
        self.editor = self._member('editor_a', 'editor')

    def _member(self, username, role):
        user = User.objects.create_user(username, f'{username}@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'free'})
        ProjectMember.objects.create(project=self.project_a, user=user, role=role,
                                     invited_by=self.user_a)
        client = Client()
        client.force_login(user)
        s = client.session
        s['current_project_id'] = self.project_a.id
        s.save()
        return client

    def assertPhotoUnchanged(self, slot, expected, label):
        slot.refresh_from_db()
        self.assertEqual(expected, slot.photo_data, f'{label}: photo was rewritten')

    def assertDenied(self, resp, label):
        self.assertIn(resp.status_code, (302, 400, 401, 403, 404),
                      f'{label}: request was accepted (HTTP {resp.status_code})')

    def upload(self, client, slot, raw, name='p.png', content_type='image/png'):
        return client.post(reverse('planner:upload_slot_photo'), {
            'slot_id': slot.id,
            'photo': SimpleUploadedFile(name, raw, content_type=content_type),
        })


# ---------------------------------------------------------------------------
# 1. upload_slot_photo
# ---------------------------------------------------------------------------

class UploadSlotPhotoTests(PhotoTenantBase):

    def test_cannot_overwrite_another_tenants_slot(self):
        resp = self.upload(self.client, self.slot_b, PNG)
        self.assertEqual(404, resp.status_code)
        self.assertPhotoUnchanged(self.slot_b, self.photo_b, 'cross-tenant upload')

    def test_anonymous_cannot_upload(self):
        resp = self.upload(self.anon, self.slot_a, PNG)
        self.assertDenied(resp, 'anonymous upload')
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, 'anonymous upload')

    def test_viewer_cannot_upload(self):
        resp = self.upload(self.viewer, self.slot_a, PNG)
        self.assertEqual(403, resp.status_code)
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, 'viewer upload')

    def test_editor_member_can_upload(self):
        resp = self.upload(self.editor, self.slot_a, PNG)
        self.assertEqual(200, resp.status_code, resp.content)
        self.slot_a.refresh_from_db()
        self.assertEqual(_data_url('image/png', PNG), self.slot_a.photo_data)

    def test_type_comes_from_bytes_not_header(self):
        """A JPEG sent as image/png is stored as image/jpeg."""
        resp = self.upload(self.client, self.slot_a, JPEG, 'x.png', 'image/png')
        self.assertEqual(200, resp.status_code, resp.content)
        self.slot_a.refresh_from_db()
        self.assertTrue(self.slot_a.photo_data.startswith('data:image/jpeg;base64,'))

    def test_webp_accepted(self):
        resp = self.upload(self.client, self.slot_a, WEBP, 'x.webp', 'image/webp')
        self.assertEqual(200, resp.status_code, resp.content)

    def test_rejects_non_images_whatever_the_header_says(self):
        for label, raw, ctype in (
            ('html as png', HTML, 'image/png'),
            ('svg', SVG, 'image/svg+xml'),
            ('gif', GIF, 'image/gif'),
            ('truncated png', PNG[:20], 'image/png'),
            ('empty', b'', 'image/png'),
        ):
            with self.subTest(label):
                resp = self.upload(self.client, self.slot_a, raw, content_type=ctype)
                self.assertDenied(resp, label)
                self.assertPhotoUnchanged(self.slot_a, self.photo_a, label)

    def test_rejects_oversize_file(self):
        raw = PNG + b'\0' * (MAX_PHOTO_BYTES + 1 - len(PNG))
        resp = self.upload(self.client, self.slot_a, raw)
        self.assertEqual(400, resp.status_code)
        self.assertIn('limit', resp.json()['error'])
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, 'oversize')

    def test_rejects_decompression_bomb_dimensions(self):
        bomb = _image_bytes('PNG', size=(10000, 10000), mode='1')
        self.assertLess(len(bomb), MAX_PHOTO_BYTES)
        resp = self.upload(self.client, self.slot_a, bomb)
        self.assertEqual(400, resp.status_code)
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, 'pixel bomb')

    def test_get_not_allowed(self):
        resp = self.client.get(reverse('planner:upload_slot_photo'))
        self.assertEqual(405, resp.status_code)

    def test_write_touches_only_photo_data(self):
        with CaptureQueriesContext(connection) as ctx:
            self.upload(self.client, self.slot_a, PNG)
        updates = [q['sql'] for q in ctx.captured_queries
                   if q['sql'].startswith('UPDATE') and 'planner_presenterslot' in q['sql']]
        self.assertEqual(1, len(updates), updates)
        self.assertNotIn('"notes"', updates[0])


# ---------------------------------------------------------------------------
# 2. The two unused upload endpoints are gone
# ---------------------------------------------------------------------------

class DeletedUploadEndpointTests(PhotoTenantBase):

    def test_routes_no_longer_exist(self):
        for name in ('upload_presenter_photo', 'upload_photo_by_assignment'):
            with self.subTest(name):
                with self.assertRaises(NoReverseMatch):
                    reverse(f'planner:{name}')

    def test_old_paths_404(self):
        for path, data in (
            ('/audiopatch/api/mic/upload-presenter-photo/',
             {'presenter_id': self.presenter_b.id}),
            ('/audiopatch/api/mic/upload-photo-by-assignment/',
             {'assignment_id': self.mic_assignment_b.id}),
        ):
            with self.subTest(path):
                data['photo'] = SimpleUploadedFile('p.png', PNG, content_type='image/png')
                self.assertEqual(404, self.client.post(path, data).status_code)
        self.assertPhotoUnchanged(self.slot_b, self.photo_b, 'old endpoints')
        self.presenter_b.refresh_from_db()
        self.assertFalse(self.presenter_b.photo)


# ---------------------------------------------------------------------------
# 3. upload_slot_photo_from_url -- permission checks precede any fetch
# ---------------------------------------------------------------------------

class UploadFromUrlEndpointTests(PhotoTenantBase):

    URL = 'https://images.example.com/face.png'

    def post(self, client, slot, url=None):
        return client.post(
            reverse('planner:upload_slot_photo_from_url'),
            data=json.dumps({'slot_id': slot.id, 'url': url or self.URL}),
            content_type='application/json',
        )

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_other_tenants_slot_is_404_and_nothing_is_fetched(self, fetch):
        resp = self.post(self.client, self.slot_b)
        self.assertEqual(404, resp.status_code)
        fetch.assert_not_called()
        self.assertPhotoUnchanged(self.slot_b, self.photo_b, 'cross-tenant url upload')

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_viewer_is_403_and_nothing_is_fetched(self, fetch):
        resp = self.post(self.viewer, self.slot_a)
        self.assertEqual(403, resp.status_code)
        fetch.assert_not_called()
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, 'viewer url upload')

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_anonymous_is_denied_and_nothing_is_fetched(self, fetch):
        resp = self.post(self.anon, self.slot_a)
        self.assertDenied(resp, 'anonymous url upload')
        fetch.assert_not_called()

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_stores_type_from_bytes_not_remote_header(self, fetch):
        fetch.return_value = (PNG, {'Content-Type': 'text/html'})
        resp = self.post(self.client, self.slot_a)
        self.assertEqual(200, resp.status_code, resp.content)
        self.slot_a.refresh_from_db()
        self.assertEqual(_data_url('image/png', PNG), self.slot_a.photo_data)

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_non_image_body_is_rejected(self, fetch):
        fetch.return_value = (HTML, {'Content-Type': 'image/png'})
        resp = self.post(self.client, self.slot_a)
        self.assertEqual(400, resp.status_code)
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, 'html from url')

    def test_internal_url_is_refused_end_to_end(self):
        with mock.patch.object(safe_fetch.socket, 'getaddrinfo',
                               return_value=_addrinfo('169.254.169.254')), \
             mock.patch.object(safe_fetch, '_open') as opened:
            resp = self.post(self.client, self.slot_a, 'http://metadata.example/latest/')
        self.assertEqual(400, resp.status_code)
        opened.assert_not_called()
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, 'ssrf')


# ---------------------------------------------------------------------------
# 4. safe_fetch unit tests -- pinning, redirects, limits
# ---------------------------------------------------------------------------

def _addrinfo(*ips):
    import socket
    out = []
    for ip in ips:
        fam = socket.AF_INET6 if ':' in ip else socket.AF_INET
        out.append((fam, socket.SOCK_STREAM, 6, '', (ip, 443)))
    return out


class _FakeResponse:
    def __init__(self, status=200, headers=None, chunks=(PNG,)):
        self.status = status
        self.headers = HTTPHeaderDict(headers or {})
        self._chunks = chunks
        self.closed = False

    def stream(self, _amt):
        yield from self._chunks

    def release_conn(self):
        pass

    def close(self):
        self.closed = True


PUBLIC = '93.184.216.34'


class SafeFetchTests(SimpleTestCase):

    def fetch(self, url, responses, resolve, **kw):
        """Run fetch_public with DNS and the network both faked.

        ``resolve`` maps hostname -> list of IPs (or a callable side effect).
        ``responses`` is consumed one per request. Returns (result_or_exc, opens).
        """
        opens = []

        def fake_open(scheme, ip, port, hostname, path, timeout):
            opens.append((scheme, ip, port, hostname, path))
            return responses.pop(0)

        def fake_getaddrinfo(host, port, **_):
            return _addrinfo(*resolve(host)) if callable(resolve) else _addrinfo(*resolve[host])

        with mock.patch.object(safe_fetch.socket, 'getaddrinfo', side_effect=fake_getaddrinfo), \
             mock.patch.object(safe_fetch, '_open', side_effect=fake_open):
            try:
                return fetch_public(url, max_bytes=kw.pop('max_bytes', MAX_PHOTO_BYTES), **kw), opens
            except UnsafeFetchError as e:
                return e, opens

    def assertRefused(self, result, opens, label):
        self.assertIsInstance(result[0] if not isinstance(result, Exception) else result,
                              UnsafeFetchError, f'{label}: fetch was allowed')

    def test_happy_path_connects_to_the_resolved_ip(self):
        (body, _h), opens = self.fetch('https://img.example.com/a.png', [_FakeResponse()],
                                       {'img.example.com': [PUBLIC]})
        self.assertEqual(PNG, body)
        self.assertEqual([('https', PUBLIC, 443, 'img.example.com', '/a.png')], opens)

    def test_blocked_address_ranges(self):
        for ip in ('127.0.0.1', '10.0.0.5', '172.16.0.1', '192.168.1.1',
                   '169.254.169.254', '100.64.0.1', '0.0.0.0', '224.0.0.1',
                   '::1', 'fe80::1', 'fc00::1', '::ffff:127.0.0.1', '::ffff:10.0.0.1'):
            with self.subTest(ip):
                result, opens = self.fetch('http://h.example/', [_FakeResponse()],
                                           {'h.example': [ip]})
                self.assertIsInstance(result, UnsafeFetchError)
                self.assertEqual([], opens, f'{ip}: a connection was made')

    def test_any_private_record_refuses_the_host(self):
        result, opens = self.fetch('http://h.example/', [_FakeResponse()],
                                   {'h.example': [PUBLIC, '10.0.0.5']})
        self.assertIsInstance(result, UnsafeFetchError)
        self.assertEqual([], opens)

    def test_dns_rebinding_cannot_swap_the_address(self):
        """The name is resolved once per hop and the connection uses that answer."""
        answers = iter([[PUBLIC], ['127.0.0.1']])
        (body, _h), opens = self.fetch('http://rebind.example/x.png', [_FakeResponse()],
                                       lambda host: next(answers))
        self.assertEqual(PUBLIC, opens[0][1])

    def test_redirect_to_internal_host_is_refused(self):
        resp = _FakeResponse(302, {'Location': 'http://internal.example/secret'})
        result, opens = self.fetch('http://public.example/', [resp, _FakeResponse()],
                                   {'public.example': [PUBLIC], 'internal.example': ['10.1.2.3']})
        self.assertIsInstance(result, UnsafeFetchError)
        self.assertEqual(1, len(opens), 'the internal hop was connected to')

    def test_redirect_to_literal_metadata_ip_is_refused(self):
        resp = _FakeResponse(301, {'Location': 'http://169.254.169.254/latest/meta-data/'})
        result, opens = self.fetch('http://public.example/', [resp, _FakeResponse()],
                                   {'public.example': [PUBLIC], '169.254.169.254': ['169.254.169.254']})
        self.assertIsInstance(result, UnsafeFetchError)
        self.assertEqual(1, len(opens))

    def test_public_redirect_is_followed_and_rechecked(self):
        resp = _FakeResponse(302, {'Location': '/cdn/a.png'})
        (body, _h), opens = self.fetch('https://img.example.com/a', [resp, _FakeResponse()],
                                       {'img.example.com': [PUBLIC]})
        self.assertEqual(PNG, body)
        self.assertEqual('/cdn/a.png', opens[1][4])

    def test_redirect_loop_is_capped(self):
        loop = [_FakeResponse(302, {'Location': '/again'}) for _ in range(10)]
        result, opens = self.fetch('http://img.example.com/', loop,
                                   {'img.example.com': [PUBLIC]})
        self.assertIsInstance(result, UnsafeFetchError)
        self.assertEqual(safe_fetch.MAX_REDIRECTS + 1, len(opens))

    def test_url_shape_refusals_never_resolve(self):
        for url in ('file:///etc/passwd', 'gopher://h.example/', 'ftp://h.example/a.png',
                    'http://h.example:8080/a.png', 'https://h.example:22/',
                    'http://user:pw@h.example/a.png', 'http:///nohost'):
            with self.subTest(url):
                with mock.patch.object(safe_fetch.socket, 'getaddrinfo') as gai:
                    with self.assertRaises(UnsafeFetchError):
                        fetch_public(url, max_bytes=MAX_PHOTO_BYTES)
                    gai.assert_not_called()

    def test_declared_length_over_cap_is_refused(self):
        resp = _FakeResponse(200, {'Content-Length': str(MAX_PHOTO_BYTES + 1)})
        result, _ = self.fetch('http://img.example.com/', [resp], {'img.example.com': [PUBLIC]})
        self.assertIsInstance(result, UnsafeFetchError)

    def test_streamed_body_over_cap_is_cut_off(self):
        resp = _FakeResponse(200, {}, chunks=[b'x' * 1024] * 10)
        result, _ = self.fetch('http://img.example.com/', [resp], {'img.example.com': [PUBLIC]},
                               max_bytes=4096)
        self.assertIsInstance(result, UnsafeFetchError)

    def test_overall_deadline(self):
        """A server trickling bytes inside the per-read timeout still hits the deadline."""
        clock = iter([0.0, 0.0] + [i * 5.0 for i in range(1, 100)])
        resp = _FakeResponse(200, {}, chunks=[b'x'] * 50)
        with mock.patch.object(safe_fetch.time, 'monotonic', side_effect=lambda: next(clock)):
            result, _ = self.fetch('http://img.example.com/', [resp],
                                   {'img.example.com': [PUBLIC]}, total_timeout=15.0)
        self.assertIsInstance(result, UnsafeFetchError)
        self.assertIn('timed out', str(result))

    def test_non_200_is_refused(self):
        result, _ = self.fetch('http://img.example.com/', [_FakeResponse(500)],
                               {'img.example.com': [PUBLIC]})
        self.assertIsInstance(result, UnsafeFetchError)

    def test_https_pool_verifies_the_real_hostname(self):
        with mock.patch.object(safe_fetch.urllib3, 'HTTPSConnectionPool') as pool_cls:
            pool_cls.return_value.urlopen.return_value = _FakeResponse()
            safe_fetch._open('https', PUBLIC, 443, 'img.example.com', '/a.png', 5)
        args, kwargs = pool_cls.call_args
        self.assertEqual(PUBLIC, args[0])
        self.assertEqual('img.example.com', kwargs['server_hostname'])
        self.assertEqual('img.example.com', kwargs['assert_hostname'])
        self.assertEqual('CERT_REQUIRED', kwargs['cert_reqs'])
        _, open_kwargs = pool_cls.return_value.urlopen.call_args
        self.assertFalse(open_kwargs['redirect'])
        self.assertEqual('img.example.com', open_kwargs['headers']['Host'])


# ---------------------------------------------------------------------------
# 5. Presenter lookups stay inside the project
# ---------------------------------------------------------------------------

class PresenterScopingTests(PhotoTenantBase):

    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def test_presenter_id_cannot_borrow_another_tenants_presenter_or_photo(self):
        """Issue #10's sync copies Presenter.photo into the slot. With an
        unscoped lookup, naming B's presenter id put B's headshot in A's
        response and A's slot."""
        b_headshot = PNG + self.MARKER_B.encode()
        with override_settings(MEDIA_ROOT=self.media):
            self.presenter_b.photo.save('b.png', SimpleUploadedFile('b.png', b_headshot),
                                        save=True)
            resp = self.client.post(
                reverse('planner:update_mic_assignment'),
                data=json.dumps({'assignment_id': self.mic_assignment_a.id,
                                 'field': 'presenter_id',
                                 'value': str(self.presenter_b.id)}),
                content_type='application/json',
            )
        self.assertNoLeak(resp, 'update_mic_assignment presenter_id')
        self.assertNotIn(base64.b64encode(b_headshot).decode(), resp.content.decode())
        self.slot_a.refresh_from_db()
        self.assertNotEqual(self.presenter_b.id, self.slot_a.presenter_id)
        self.assertEqual(self.project_a.id, self.slot_a.presenter.project_id)
        self.assertNotIn(self.MARKER_B, base64.b64decode(
            (self.slot_a.photo_data or 'data:,').split(',', 1)[1] or b'').decode('latin-1'))

    def test_presenter_id_still_works_within_the_project(self):
        other_a = Presenter.objects.create(project=self.project_a, name='Second A')
        resp = self.client.post(
            reverse('planner:update_mic_assignment'),
            data=json.dumps({'assignment_id': self.mic_assignment_a.id,
                             'field': 'presenter_id', 'value': str(other_a.id)}),
            content_type='application/json',
        )
        self.assertEqual(200, resp.status_code)
        self.slot_a.refresh_from_db()
        self.assertEqual(other_a.id, self.slot_a.presenter_id)

    def test_presenter_list_without_a_project_is_empty(self):
        """It used to skip the project filter when the session had none."""
        loner = User.objects.create_user('loner', 'l@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=loner, defaults={'account_type': 'free'})
        c = Client()
        c.force_login(loner)
        resp = c.get(reverse('planner:get_presenters_list'), {'q': ''})
        self.assertNoLeak(resp, 'get_presenters_list (no project)')
        if resp.status_code == 200:
            self.assertEqual([], resp.json()['presenters'])

    def test_presenter_list_is_scoped(self):
        resp = self.client.get(reverse('planner:get_presenters_list'), {'q': 'Presenter'})
        self.assertNoLeak(resp, 'get_presenters_list')
        names = [p['name'] for p in resp.json()['presenters']]
        self.assertIn('Presenter AAA', names)


# ---------------------------------------------------------------------------
# 6. Slot writes no longer read or rewrite the headshot
# ---------------------------------------------------------------------------

class SlotWritesSkipPhotoTests(PhotoTenantBase):
    """Each of these endpoints did a full slot.save(), re-sending the whole
    base64 photo for a one-column change. The SQL must not mention
    photo_data at all -- neither the UPDATE nor the SELECT before it."""

    def setUp(self):
        super().setUp()
        # A second slot on A so next/prev/activate/remove have somewhere to go.
        self.slot_a2 = PresenterSlot.objects.create(
            assignment=self.mic_assignment_a, order=1,
            photo_data=_data_url('image/png', b'second-slot'),
        )

    def post_json(self, name, payload, client=None):
        return (client or self.client).post(
            reverse(f'planner:{name}'), data=json.dumps(payload),
            content_type='application/json',
        )

    def assertNoPhotoSql(self, name, payload):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.post_json(name, payload)
        self.assertEqual(200, resp.status_code, f'{name}: {resp.content[:200]}')
        self.assertTrue(resp.json().get('success', True), f'{name}: {resp.content[:200]}')
        self.assertEqual([], _queries_touching_photo(ctx),
                         f'{name} read or wrote photo_data')
        self.assertPhotoUnchanged(self.slot_a, self.photo_a, name)
        return resp

    def test_toggle_micd(self):
        self.assertNoPhotoSql('toggle_slot_micd', {'slot_id': self.slot_a.id, 'is_micd': True})
        self.slot_a.refresh_from_db()
        self.assertTrue(self.slot_a.is_micd)

    def test_update_slot_field_notes(self):
        self.assertNoPhotoSql('update_slot_field',
                              {'slot_id': self.slot_a.id, 'field': 'notes', 'value': 'n'})
        self.slot_a.refresh_from_db()
        self.assertEqual('n', self.slot_a.notes)

    def test_update_mic_assignment_notes(self):
        resp = self.assertNoPhotoSql('update_mic_assignment', {
            'assignment_id': self.mic_assignment_a.id, 'field': 'notes', 'value': 'hello'})
        self.assertEqual('', resp.json()['slot_photo_data'])

    def test_activate_writes_only_is_active(self):
        """The response still carries the newly active slot's photo -- loaded
        for that one slot only, after the writes."""
        with CaptureQueriesContext(connection) as ctx:
            resp = self.post_json('activate_presenter_slot', {
                'assignment_id': self.mic_assignment_a.id, 'slot_id': self.slot_a2.id})
        self.assertEqual(self.slot_a2.photo_data, resp.json()['photo_url'])
        photo_sql = _queries_touching_photo(ctx)
        self.assertEqual(1, len(photo_sql), photo_sql)
        self.assertTrue(photo_sql[0].startswith('SELECT'), photo_sql)

    def test_advance_and_previous_write_only_is_active(self):
        for name in ('advance_presenter_slot', 'previous_presenter_slot'):
            with self.subTest(name):
                with CaptureQueriesContext(connection) as ctx:
                    resp = self.post_json(name, {'assignment_id': self.mic_assignment_a.id})
                self.assertTrue(resp.json()['success'])
                writes = [s for s in _queries_touching_photo(ctx) if not s.startswith('SELECT')]
                self.assertEqual([], writes, f'{name} rewrote photo_data')
                active = PresenterSlot.objects.get(id=resp.json()['slot_id'])
                self.assertEqual(active.photo_data or None, resp.json()['photo_url'])

    def test_remove_slot(self):
        self.assertNoPhotoSql('remove_presenter_slot', {
            'assignment_id': self.mic_assignment_a.id, 'slot_id': self.slot_a2.id})

    def test_presenter_change_still_syncs_the_photo(self):
        """The one write that is meant to touch photo_data still does."""
        resp = self.post_json('update_slot_field', {
            'slot_id': self.slot_a.id, 'field': 'presenter_name', 'value': ''})
        self.assertTrue(resp.json()['success'])
        self.slot_a.refresh_from_db()
        self.assertIsNone(self.slot_a.presenter)
        self.assertEqual('', self.slot_a.photo_data)

    def test_sync_poll_does_not_load_photos(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(reverse('planner:mic_tracker_sync'))
        self.assertEqual(200, resp.status_code)
        self.assertEqual([], _queries_touching_photo(ctx), 'sync poll loaded photo_data')
        self.assertNoLeak(resp, 'mic_tracker_sync')
        self.assertIn('Presenter AAA', resp.content.decode())

    def test_cross_tenant_slot_writes_are_still_404(self):
        """Deferring the column must not have loosened the lookups."""
        for name, payload in (
            ('toggle_slot_micd', {'slot_id': self.slot_b.id, 'is_micd': True}),
            ('update_slot_field', {'slot_id': self.slot_b.id, 'field': 'notes', 'value': 'PWNED'}),
            ('advance_presenter_slot', {'assignment_id': self.mic_assignment_b.id}),
            ('previous_presenter_slot', {'assignment_id': self.mic_assignment_b.id}),
            ('activate_presenter_slot', {'assignment_id': self.mic_assignment_b.id,
                                         'slot_id': self.slot_b.id}),
            ('update_mic_assignment', {'assignment_id': self.mic_assignment_b.id,
                                       'field': 'notes', 'value': 'PWNED'}),
        ):
            with self.subTest(name):
                resp = self.post_json(name, payload)
                body = resp.content.decode('utf-8', 'replace')
                self.assertTrue(resp.status_code == 404 or '"success": false' in body,
                                f'{name} accepted project B ({resp.status_code})')
                self.assertNotIn(self.MARKER_B, body)
        self.slot_b.refresh_from_db()
        self.assertNotEqual('PWNED', self.slot_b.notes)
        self.assertFalse(self.slot_b.is_micd)
        self.assertEqual(self.photo_b, self.slot_b.photo_data)


# ---------------------------------------------------------------------------
# 7. The mic tracker page reads each headshot once, not once per active_slot
# ---------------------------------------------------------------------------

class MicTrackerPageTests(PhotoTenantBase):

    def test_page_loads_photos_once_and_still_shows_them(self):
        """MicAssignment.active_slot runs a fresh query per call and the A2
        card calls it ~6 times. Each used to pull photo_data: 281 photo
        SELECTs for one 16-card session."""
        cards = self.mic_session_a.mic_assignments.count()
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(reverse('planner:mic_tracker'))
        self.assertEqual(200, resp.status_code)
        body = resp.content.decode()
        self.assertIn(self.photo_a, body)
        self.assertNotIn(self.MARKER_B, body)
        photo_selects = _queries_touching_photo(ctx)
        self.assertLess(len(photo_selects), cards,
                        f'{len(photo_selects)} photo-loading queries for {cards} cards')
