"""Presenter photos: a person's follows them, a mic position's stays per
session, and neither leaves the project.

Isolation tests are in the #101 shape (``TenantIsolationBase``): project A is
the session we drive, project B is the victim, and B's photo bytes must never
appear in anything A is served. The rest pin the behaviour:

* the display rule -- a slot's session photo, else a person's headshot, else
  nothing (planner.utils.presenter_photos);
* uploads -- "this person, all sessions" vs "this session only", and a mic
  label never getting a headshot;
* the slot-to-presenter migration's classification.

Run with::

    python manage.py test planner.tests.test_presenter_headshots \\
        --settings=audiopatch.test_settings
"""

import base64
import json
import random
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import Client, SimpleTestCase
from django.urls import reverse
from PIL import Image

from planner.models import (
    MicSession, Presenter, PresenterPhoto, PresenterSlot, Project, UserProfile,
)
from planner.tests.test_presenter_photo_hardening import PhotoTenantBase
from planner.utils.image_upload import (
    NEAR_IDENTICAL_BITS, fingerprint_distance, normalize_headshot, photo_fingerprint,
)
from planner.utils.mic_labels import looks_like_mic_label


def _pic(seed, size=(96, 96)):
    """A distinct picture per seed: an 8x8 grid of random greys, blown up.
    Solid colours would all fingerprint the same, so they can't stand in for
    different faces."""
    rnd = random.Random(seed)
    img = Image.new('RGB', (8, 8))
    img.putdata([(v, v, v) for v in (rnd.randrange(256) for _ in range(64))])
    buf = BytesIO()
    img.resize(size, Image.NEAREST).save(buf, format='PNG')
    return buf.getvalue()


def _resaved(raw, size=(80, 80)):
    """The same picture uploaded again: rescaled and re-encoded."""
    buf = BytesIO()
    Image.open(BytesIO(raw)).convert('RGB').resize(size).save(buf, format='JPEG', quality=70)
    return buf.getvalue()


def _data_url(raw, mime='image/png'):
    return f'data:{mime};base64,{base64.b64encode(raw).decode()}'


RED, GREEN, BLUE, GOLD, GREY = (_pic(n) for n in range(1, 6))


def _session_url_prefix(slot):
    return reverse('planner:slot_photo', args=[slot.id]) + '?v='


class HeadshotBase(PhotoTenantBase):
    """PhotoTenantBase's slots, but holding real images, plus a headshot for B."""

    def setUp(self):
        super().setUp()
        for tag, raw in (('a', RED), ('b', BLUE)):
            slot = getattr(self, f'slot_{tag}')
            slot.photo_data = _data_url(raw)
            slot.save(update_fields=['photo_data'])
        self.headshot_b = PresenterPhoto.store(self.presenter_b, _pic(99))

    def loner(self):
        """Logged in, but a member of nothing."""
        user = User.objects.create_user('loner', 'l@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'free'})
        c = Client()
        c.force_login(user)
        return c

    def second_session_slot(self, presenter, name='Second AAA', photo=None):
        """``presenter`` on RF 1 of another session in project A."""
        session = MicSession.objects.create(day=self.show_day_a, name=name)
        assignment = session.mic_assignments.get(rf_number=1)
        slot = assignment.presenter_slots.order_by('order').first() or \
            PresenterSlot.objects.create(assignment=assignment, order=0)
        slot.presenter = presenter
        slot.is_active = True
        slot.photo_data = _data_url(photo) if photo else ''
        slot.save()
        return slot

    def upload(self, slot, raw=GREEN, scope=None, client=None):
        data = {'slot_id': slot.id,
                'photo': SimpleUploadedFile('p.png', raw, content_type='image/png')}
        if scope:
            data['scope'] = scope
        return (client or self.client).post(reverse('planner:upload_slot_photo'), data)

    def shown(self):
        """slot id -> the photo URL the sync poll says each card shows."""
        rows = self.client.get(reverse('planner:mic_tracker_sync')).json()['slots']
        return {r['slot_id']: r['photo'] for r in rows}

    def served(self, url):
        """The bytes behind a photo URL, as the browser would fetch them."""
        path, _, query = url.partition('?')
        resp = self.client.get(path, dict(p.split('=') for p in query.split('&') if p))
        self.assertEqual(200, resp.status_code, url)
        return resp.content

    def assertSamePicture(self, raw_a, raw_b, msg=None):
        self.assertLessEqual(
            fingerprint_distance(photo_fingerprint(raw_a), photo_fingerprint(raw_b)), 2, msg)


# ---------------------------------------------------------------------------
# 1. Serving a headshot
# ---------------------------------------------------------------------------

class PresenterPhotoServingTests(HeadshotBase):

    def get(self, client, presenter, **params):
        return client.get(reverse('planner:presenter_photo', args=[presenter.id]), params)

    def test_other_tenants_headshot_is_404(self):
        resp = self.get(self.client, self.presenter_b)
        self.assertEqual(404, resp.status_code)
        self.assertNotIn(bytes(self.headshot_b.content), resp.content)

    def test_anonymous_gets_no_bytes(self):
        resp = self.get(self.anon, self.presenter_b)
        self.assertIn(resp.status_code, (302, 401, 403, 404))
        self.assertNotIn(bytes(self.headshot_b.content), resp.content)

    def test_member_of_nothing_is_404(self):
        resp = self.get(self.loner(), self.presenter_b)
        self.assertEqual(404, resp.status_code)

    def test_viewer_can_see_their_projects_headshot(self):
        PresenterPhoto.store(self.presenter_a, RED)
        resp = self.get(self.viewer, self.presenter_a)
        self.assertEqual(200, resp.status_code)

    def test_headers(self):
        photo = PresenterPhoto.store(self.presenter_a, RED)
        resp = self.get(self.client, self.presenter_a, v=photo.sha256[:12])
        self.assertEqual(200, resp.status_code)
        self.assertEqual('image/jpeg', resp['Content-Type'])
        self.assertEqual('nosniff', resp['X-Content-Type-Options'])
        self.assertIn('private', resp['Cache-Control'])
        self.assertIn('immutable', resp['Cache-Control'])
        self.assertIn('Cookie', resp['Vary'])
        self.assertEqual(bytes(photo.content), resp.content)

    def test_stale_version_is_not_cached_forever(self):
        PresenterPhoto.store(self.presenter_a, RED)
        resp = self.get(self.client, self.presenter_a, v='000000000000')
        self.assertIn('no-cache', resp['Cache-Control'])
        self.assertNotIn('immutable', resp['Cache-Control'])

    def test_etag_revalidation(self):
        photo = PresenterPhoto.store(self.presenter_a, RED)
        resp = self.client.get(reverse('planner:presenter_photo', args=[self.presenter_a.id]),
                               HTTP_IF_NONE_MATCH=f'"{photo.sha256}"')
        self.assertEqual(304, resp.status_code)
        self.assertEqual(b'', resp.content)

    def test_etag_does_not_confirm_another_tenants_photo(self):
        resp = self.client.get(reverse('planner:presenter_photo', args=[self.presenter_b.id]),
                               HTTP_IF_NONE_MATCH=f'"{self.headshot_b.sha256}"')
        self.assertEqual(404, resp.status_code)


# ---------------------------------------------------------------------------
# 2. Serving a session photo
# ---------------------------------------------------------------------------

class SessionPhotoServingTests(HeadshotBase):

    def get(self, client, slot, name='slot_photo', **headers):
        return client.get(reverse(f'planner:{name}', args=[slot.id]), **headers)

    def test_other_tenants_slot_is_404(self):
        for name in ('slot_photo', 'legacy_slot_photo'):
            with self.subTest(name):
                resp = self.get(self.client, self.slot_b, name)
                self.assertEqual(404, resp.status_code)
                self.assertNotIn(BLUE, resp.content)

    def test_anonymous_and_non_member(self):
        for label, client in (('anon', self.anon), ('loner', self.loner())):
            with self.subTest(label):
                resp = self.get(client, self.slot_b)
                self.assertIn(resp.status_code, (302, 404))
                self.assertNotIn(BLUE, resp.content)

    def test_serves_own_slot_with_the_type_pillow_found(self):
        self.slot_a.photo_data = _data_url(RED, mime='text/html')
        self.slot_a.save(update_fields=['photo_data'])
        resp = self.get(self.client, self.slot_a)
        self.assertEqual(200, resp.status_code)
        self.assertEqual('image/png', resp['Content-Type'])
        self.assertEqual(RED, resp.content)
        self.assertIn('no-cache', resp['Cache-Control'])

    def test_old_url_name_still_serves(self):
        """Trackers left open across the deploy still hold legacy-photo/ URLs."""
        self.assertEqual(RED, self.get(self.client, self.slot_a, 'legacy_slot_photo').content)

    def test_etag_revalidation(self):
        etag = self.get(self.client, self.slot_a)['ETag']
        resp = self.get(self.client, self.slot_a, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(304, resp.status_code)

    def test_never_serves_non_image_bytes(self):
        """The old upload trusted the browser's Content-Type, so a stored
        'image/png' can hold HTML. It must not come back out."""
        self.slot_a.photo_data = _data_url(b'<script>alert(1)</script>', mime='image/png')
        self.slot_a.save(update_fields=['photo_data'])
        self.assertEqual(404, self.get(self.client, self.slot_a).status_code)


# ---------------------------------------------------------------------------
# 3. A person's photo follows them; the display rule
# ---------------------------------------------------------------------------

class PersonPhotoTests(HeadshotBase):

    def test_all_sessions_upload_updates_every_card(self):
        """The feature, for a person: one upload, every card they are on --
        including cards that had a session photo of them already."""
        with_old_photo = self.second_session_slot(self.presenter_a, 'Day 2', photo=GOLD)
        without_photo = self.second_session_slot(self.presenter_a, 'Day 3')
        resp = self.upload(self.slot_a, GREEN, scope='all')
        self.assertEqual(200, resp.status_code, resp.content)
        url = resp.json()['photo_url']
        self.assertEqual('all', resp.json()['scope'])
        self.assertTrue(url.startswith(reverse('planner:presenter_photo',
                                               args=[self.presenter_a.id])))

        shown = self.shown()
        for slot in (self.slot_a, with_old_photo, without_photo):
            self.assertEqual(url, shown[slot.id], f'slot {slot.id} still shows another photo')
        self.assertSamePicture(GREEN, self.served(url))

        page = self.client.get(reverse('planner:mic_tracker')).content.decode()
        self.assertGreaterEqual(page.count(f'data-photo="{url}"'), 3)

    def test_default_scope_for_a_person_is_all_sessions(self):
        """An upload from a page loaded before this deploy sends no scope."""
        other = self.second_session_slot(self.presenter_a)
        resp = self.upload(self.slot_a, GREEN)
        self.assertEqual('all', resp.json()['scope'])
        self.assertEqual(resp.json()['photo_url'], self.shown()[other.id])

    def test_session_only_upload_changes_only_that_card(self):
        PresenterPhoto.store(self.presenter_a, GOLD)
        other = self.second_session_slot(self.presenter_a)
        before = self.shown()[other.id]
        resp = self.upload(self.slot_a, GREEN, scope='session')
        self.assertEqual(200, resp.status_code, resp.content)
        self.assertEqual('session', resp.json()['scope'])
        shown = self.shown()
        self.assertEqual(resp.json()['photo_url'], shown[self.slot_a.id])
        self.assertTrue(shown[self.slot_a.id].startswith(_session_url_prefix(self.slot_a)))
        self.assertSamePicture(GREEN, self.served(shown[self.slot_a.id]))
        self.assertEqual(before, shown[other.id])
        self.assertSamePicture(GOLD, bytes(PresenterPhoto.objects.get(
            presenter=self.presenter_a).content), 'the headshot was replaced')

    def test_session_photo_url_changes_when_the_photo_does(self):
        first = self.upload(self.slot_a, GREEN, scope='session').json()['photo_url']
        second = self.upload(self.slot_a, GOLD, scope='session').json()['photo_url']
        self.assertNotEqual(first, second)

    def test_session_photo_beats_the_headshot(self):
        PresenterPhoto.store(self.presenter_a, GREEN)
        shown = self.shown()[self.slot_a.id]
        self.assertTrue(shown.startswith(_session_url_prefix(self.slot_a)))
        self.assertSamePicture(RED, self.served(shown))

    def test_presenter_change_brings_their_headshot(self):
        photo = PresenterPhoto.store(self.presenter_a, GREEN)
        slot = self.second_session_slot(None)
        resp = self.client.post(
            reverse('planner:update_mic_assignment'),
            data=json.dumps({'assignment_id': slot.assignment_id,
                             'field': 'presenter_name', 'value': self.presenter_a.name}),
            content_type='application/json')
        self.assertEqual(photo.url, resp.json()['photo_url'])
        self.assertEqual(self.presenter_a.id, resp.json()['presenter_id'])
        self.assertFalse(resp.json()['presenter_is_mic_label'])

    def test_presenter_change_drops_the_previous_presenters_session_photo(self):
        """Otherwise the old presenter's face would show on the new one."""
        newcomer = Presenter.objects.create(project=self.project_a, name='Newcomer')
        resp = self.client.post(
            reverse('planner:update_mic_assignment'),
            data=json.dumps({'assignment_id': self.mic_assignment_a.id,
                             'field': 'presenter_id', 'value': str(newcomer.id)}),
            content_type='application/json')
        self.assertEqual('', resp.json()['photo_url'])
        self.slot_a.refresh_from_db()
        self.assertEqual('', self.slot_a.photo_data)

    def test_card_with_no_presenter_takes_only_a_session_photo(self):
        self.slot_a.presenter = None
        self.slot_a.save(update_fields=['presenter'])
        resp = self.upload(self.slot_a, GREEN, scope='all')
        self.assertEqual(400, resp.status_code)
        self.assertIn('presenter', resp.json()['error'])
        resp = self.upload(self.slot_a, GREEN)   # no scope: session
        self.assertEqual(200, resp.status_code, resp.content)
        self.assertEqual('session', resp.json()['scope'])
        self.assertFalse(PresenterPhoto.objects.filter(presenter__project=self.project_a).exists())

    def test_unknown_scope_is_refused(self):
        resp = self.upload(self.slot_a, GREEN, scope='everyone')
        self.assertEqual(400, resp.status_code)

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_refused_url_upload_fetches_nothing(self, fetch):
        self.slot_a.presenter = None
        self.slot_a.save(update_fields=['presenter'])
        resp = self.client.post(
            reverse('planner:upload_slot_photo_from_url'),
            data=json.dumps({'slot_id': self.slot_a.id, 'url': 'https://img.example.com/a.png',
                             'scope': 'all'}),
            content_type='application/json')
        self.assertEqual(400, resp.status_code)
        fetch.assert_not_called()

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_url_upload_takes_a_scope(self, fetch):
        fetch.return_value = (GREEN, {})
        resp = self.client.post(
            reverse('planner:upload_slot_photo_from_url'),
            data=json.dumps({'slot_id': self.slot_a.id, 'url': 'https://img.example.com/a.png',
                             'scope': 'session'}),
            content_type='application/json')
        self.assertEqual(200, resp.status_code, resp.content)
        self.assertEqual('session', resp.json()['scope'])
        self.assertFalse(PresenterPhoto.objects.filter(presenter=self.presenter_a).exists())

    def test_slot_pointing_at_another_tenants_presenter_cannot_write_it(self):
        """Corrupt data (a slot in A naming B's presenter) must not become a
        way to replace B's headshot -- or to put a photo on that slot."""
        self.slot_a.presenter = self.presenter_b
        self.slot_a.save(update_fields=['presenter'])
        before = self.headshot_b.sha256
        for scope in ('all', 'session'):
            with self.subTest(scope):
                resp = self.upload(self.slot_a, GREEN, scope=scope)
                self.assertEqual(404, resp.status_code)
        self.headshot_b.refresh_from_db()
        self.assertEqual(before, self.headshot_b.sha256)
        self.slot_a.refresh_from_db()
        self.assertEqual(_data_url(RED), self.slot_a.photo_data)

    def test_all_sessions_upload_clears_only_this_presenters_session_photos(self):
        bystander = Presenter.objects.create(project=self.project_a, name='Bystander')
        theirs = self.second_session_slot(bystander, photo=GOLD)
        self.upload(self.slot_a, GREEN, scope='all')
        theirs.refresh_from_db()
        self.assertEqual(_data_url(GOLD), theirs.photo_data)
        self.slot_b.refresh_from_db()
        self.assertEqual(_data_url(BLUE), self.slot_b.photo_data, "another tenant's slot changed")

    def test_swap_carries_session_photos_with_their_presenters(self):
        other_assignment = self.mic_session_a.mic_assignments.get(rf_number=2)
        other = other_assignment.presenter_slots.order_by('order').first() or \
            PresenterSlot.objects.create(assignment=other_assignment, order=0)
        second = Presenter.objects.create(project=self.project_a, name='Second')
        other.presenter, other.is_active, other.photo_data = second, True, _data_url(GREEN)
        other.save()
        resp = self.client.post(
            reverse('planner:mic_assignment_reorder'),
            data=json.dumps({'action': 'swap', 'source_id': self.mic_assignment_a.id,
                             'target_id': other_assignment.id}),
            content_type='application/json')
        self.assertTrue(resp.json()['success'], resp.content)
        self.slot_a.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((second.id, _data_url(GREEN)), (self.slot_a.presenter_id, self.slot_a.photo_data))
        self.assertEqual((self.presenter_a.id, _data_url(RED)), (other.presenter_id, other.photo_data))

    def test_sync_and_page_never_carry_another_tenants_photo(self):
        b_url = self.headshot_b.url
        page = self.client.get(reverse('planner:mic_tracker')).content.decode()
        sync = self.client.get(reverse('planner:mic_tracker_sync')).content.decode()
        for label, body in (('page', page), ('sync', sync)):
            with self.subTest(label):
                self.assertNotIn(b_url, body)
                self.assertNotIn(reverse('planner:slot_photo', args=[self.slot_b.id]), body)
                self.assertNotIn(self.MARKER_B, body)

    def test_typing_orphan_with_a_headshot_is_kept(self):
        dan = Presenter.objects.create(project=self.project_a, name='Dan')
        PresenterPhoto.store(dan, GREEN)
        self.assertFalse(dan.retire_if_typing_orphan('Dana'))
        self.assertTrue(Presenter.objects.filter(id=dan.id).exists())


# ---------------------------------------------------------------------------
# 4. A mic label's photos stay per session
# ---------------------------------------------------------------------------

class MicLabelPhotoTests(HeadshotBase):

    def setUp(self):
        super().setUp()
        self.hh13 = Presenter.objects.create(project=self.project_a, name='HH13',
                                             is_mic_label=True)
        self.day1 = self.second_session_slot(self.hh13, 'Day 1 Keynote', photo=GOLD)
        self.day2 = self.second_session_slot(self.hh13, 'Day 2 Keynote', photo=GREY)

    def test_hh13_day1_upload_leaves_day2_unchanged(self):
        before = self.shown()[self.day2.id]
        resp = self.upload(self.day1, GREEN, scope='session')
        self.assertEqual(200, resp.status_code, resp.content)
        shown = self.shown()
        self.assertSamePicture(GREEN, self.served(shown[self.day1.id]))
        self.assertEqual(before, shown[self.day2.id])
        self.assertSamePicture(GREY, self.served(shown[self.day2.id]))
        self.day2.refresh_from_db()
        self.assertEqual(_data_url(GREY), self.day2.photo_data)
        self.assertFalse(PresenterPhoto.objects.filter(presenter=self.hh13).exists())

    def test_default_scope_for_a_mic_label_is_this_session(self):
        resp = self.upload(self.day1, GREEN)
        self.assertEqual('session', resp.json()['scope'])
        self.assertFalse(PresenterPhoto.objects.filter(presenter=self.hh13).exists())

    def test_a_mic_label_never_gets_a_headshot(self):
        resp = self.upload(self.day1, GREEN, scope='all')
        self.assertEqual(400, resp.status_code)
        self.assertIn('mic position', resp.json()['error'])
        self.assertFalse(PresenterPhoto.objects.filter(presenter=self.hh13).exists())
        self.day1.refresh_from_db()
        self.assertEqual(_data_url(GOLD), self.day1.photo_data)

    def test_mic_label_card_without_a_session_photo_shows_nothing(self):
        """Even if a headshot is stored (from before it was flagged)."""
        PresenterPhoto.store(self.hh13, GREEN)
        day3 = self.second_session_slot(self.hh13, 'Day 3')
        self.assertEqual('', self.shown()[day3.id])

    def test_flipping_is_mic_label_changes_the_photo_shown_and_loses_nothing(self):
        PresenterPhoto.store(self.hh13, GREEN)
        empty = self.second_session_slot(self.hh13, 'Day 3')
        stored = (bytes(PresenterPhoto.objects.get(presenter=self.hh13).content),
                  PresenterSlot.objects.get(id=self.day1.id).photo_data,
                  PresenterSlot.objects.get(id=self.day2.id).photo_data)
        checksum = self.client.get(reverse('planner:mic_tracker_sync')).json().get('checksum')

        as_label = self.shown()
        self.assertEqual('', as_label[empty.id])

        Presenter.objects.filter(id=self.hh13.id).update(is_mic_label=False)
        as_person = self.shown()
        headshot = PresenterPhoto.objects.get(presenter=self.hh13).url
        self.assertEqual(headshot, as_person[empty.id])
        # Session photos still win on their own cards.
        self.assertEqual(as_label[self.day1.id], as_person[self.day1.id])
        self.assertEqual(as_label[self.day2.id], as_person[self.day2.id])
        self.assertIsNotNone(checksum)
        self.assertNotEqual(checksum, self.client.get(
            reverse('planner:mic_tracker_sync')).json().get('checksum'),
            'other open trackers would not notice the flip')

        Presenter.objects.filter(id=self.hh13.id).update(is_mic_label=True)
        self.assertEqual(as_label, self.shown())
        self.assertEqual(stored, (
            bytes(PresenterPhoto.objects.get(presenter=self.hh13).content),
            PresenterSlot.objects.get(id=self.day1.id).photo_data,
            PresenterSlot.objects.get(id=self.day2.id).photo_data))

    def test_sync_rows_carry_the_flag(self):
        rows = self.client.get(reverse('planner:mic_tracker_sync')).json()['slots']
        by_slot = {r['slot_id']: r for r in rows}
        self.assertTrue(by_slot[self.day1.id]['mic_label'])
        self.assertFalse(by_slot[self.slot_a.id]['mic_label'])
        page = self.client.get(reverse('planner:mic_tracker')).content.decode()
        self.assertIn('data-mic-label="1"', page)

    def test_pdf_shows_session_photos_but_no_headshot_for_a_label(self):
        PresenterPhoto.objects.all().delete()
        PresenterSlot.objects.filter(assignment__session__day__project=self.project_a).update(photo_data='')
        PresenterPhoto.store(self.hh13, GREEN)
        resp = self.client.get(reverse('planner:export_mic_tracker_pdf'))
        self.assertEqual(200, resp.status_code)
        self.assertNotIn(b'/Subtype /Image', resp.content)
        PresenterSlot.objects.filter(id=self.day1.id).update(photo_data=_data_url(GOLD))
        resp = self.client.get(reverse('planner:export_mic_tracker_pdf'))
        self.assertIn(b'/Subtype /Image', resp.content)

    def test_viewer_cannot_upload_either_scope(self):
        for scope in ('all', 'session'):
            with self.subTest(scope):
                resp = self.upload(self.day1, GREEN, scope=scope, client=self.viewer)
                self.assertEqual(403, resp.status_code)
        self.day1.refresh_from_db()
        self.assertEqual(_data_url(GOLD), self.day1.photo_data)

    def test_other_tenant_cannot_upload_either_scope(self):
        """Project B's own slot, from A's session: 404 whatever the scope."""
        for scope in ('all', 'session'):
            with self.subTest(scope):
                resp = self.upload(self.slot_b, GREEN, scope=scope)
                self.assertEqual(404, resp.status_code)
        self.slot_b.refresh_from_db()
        self.assertEqual(_data_url(BLUE), self.slot_b.photo_data)


# ---------------------------------------------------------------------------
# 5. Which presenters start as mic labels
# ---------------------------------------------------------------------------

class MicLabelPatternTests(SimpleTestCase):

    def test_labels(self):
        for name in ('HH13', 'HH 01', 'hh1', 'H.H 10', 'HH B/U 12 (w/Bobby)', 'HH OSM',
                     'HH Present 2', 'Q&A 1', 'Q&A HH01', 'Q & A Mic 2', 'QA1', 'QA - 2',
                     'Pod Q&A HL', 'Stand Q&A HR', 'A2 OS', 'A1', 'BSM OS', 'Stage RF OS',
                     'RF OSM', 'OSM 1', 'OS SPARE HH', 'SPARE HH', 'Spare', 'LAV 3', 'BP2',
                     'Podium', 'Lectern', 'HL -1', 'HR - 2', 'Chair # 2', 'Panelist 3',
                     'Talent 1', 'Drummer 2', 'CONSULTANT 1', '  hh   14  '):
            with self.subTest(name):
                self.assertTrue(looks_like_mic_label(name))

    def test_people(self):
        for name in ('Jane Doe', 'Rob', 'Oscar', 'Osman Ali', 'Hsu Li', 'Raj', 'Bob',
                     'Franco HH', 'Steven Paulson DPA', 'Marnie Sprenger SL', 'ASM - Jane',
                     'HL ASM - Sam', 'SM', 'VP 58 BU', 'Abott BU', 'JOHN MADDISON',
                     'Liz Miller', 'Chair of the Board', 'Hannah', 'Lavinia', 'Rfaan', ''):
            with self.subTest(name):
                self.assertFalse(looks_like_mic_label(name))


class MicLabelCreationTests(HeadshotBase):

    def test_resolve_flags_a_new_label_but_not_a_person(self):
        self.assertTrue(Presenter.resolve('HH 7', self.project_a.id).is_mic_label)
        self.assertFalse(Presenter.resolve('Jane Doe', self.project_a.id).is_mic_label)

    def test_resolve_never_reflags_an_existing_presenter(self):
        p = Presenter.objects.create(project=self.project_a, name='HH 8', is_mic_label=False)
        self.assertFalse(Presenter.resolve('hh 8', self.project_a.id).is_mic_label)
        self.assertEqual(p.id, Presenter.resolve('hh 8', self.project_a.id).id)

    def test_typing_a_label_on_a_card_creates_a_flagged_presenter(self):
        slot = self.second_session_slot(None)
        resp = self.client.post(
            reverse('planner:update_mic_assignment'),
            data=json.dumps({'assignment_id': slot.assignment_id,
                             'field': 'presenter_name', 'value': 'Q&A 2'}),
            content_type='application/json')
        self.assertTrue(resp.json()['presenter_is_mic_label'])
        self.assertTrue(Presenter.objects.get(project=self.project_a, name='Q&A 2').is_mic_label)

    def test_duplicate_keeps_the_flag(self):
        Presenter.objects.create(project=self.project_a, name='Lectern', is_mic_label=True)
        Presenter.objects.create(project=self.project_a, name='HH 9', is_mic_label=False)
        new_project = self.project_a.duplicate(new_name='Copy of A')
        flags = dict(Presenter.objects.filter(project=new_project).values_list('name', 'is_mic_label'))
        self.assertTrue(flags['Lectern'])
        self.assertFalse(flags['HH 9'], 'a presenter unflagged by hand was re-guessed')

    def test_admin_add_flags_a_label(self):
        resp = self.client.post(reverse('admin:planner_presenter_add'), {'name': 'HH 21', 'notes': ''})
        self.assertEqual(302, resp.status_code, resp.content[:500])
        self.assertTrue(Presenter.objects.get(name='HH 21', project=self.project_a).is_mic_label)

    def test_admin_edit_can_flip_the_flag(self):
        url = reverse('admin:planner_presenter_change', args=[self.presenter_a.id])
        self.assertContains(self.client.get(url), 'name="is_mic_label"')
        self.client.post(url, {'name': self.presenter_a.name, 'notes': '', 'is_mic_label': 'on'})
        self.presenter_a.refresh_from_db()
        self.assertTrue(self.presenter_a.is_mic_label)
        self.client.post(url, {'name': self.presenter_a.name, 'notes': ''})
        self.presenter_a.refresh_from_db()
        self.assertFalse(self.presenter_a.is_mic_label)

    def test_admin_refuses_a_headshot_for_a_label(self):
        url = reverse('admin:planner_presenter_change', args=[self.presenter_a.id])
        resp = self.client.post(url, {
            'name': self.presenter_a.name, 'notes': '', 'is_mic_label': 'on',
            'headshot_upload': SimpleUploadedFile('h.png', GREEN, content_type='image/png'),
        })
        self.assertEqual(200, resp.status_code)
        self.assertFalse(PresenterPhoto.objects.filter(presenter=self.presenter_a).exists())


# ---------------------------------------------------------------------------
# 6. Duplication, PDF export, admin
# ---------------------------------------------------------------------------

class HeadshotElsewhereTests(HeadshotBase):

    def test_project_duplicate_copies_headshots_into_the_new_tenant(self):
        PresenterPhoto.store(self.presenter_a, GREEN)
        new_project = self.project_a.duplicate(new_name='Copy of A')
        new_presenter = Presenter.objects.get(project=new_project, name=self.presenter_a.name)
        copy = PresenterPhoto.objects.get(presenter=new_presenter)
        original = PresenterPhoto.objects.get(presenter=self.presenter_a)
        self.assertEqual(bytes(original.content), bytes(copy.content))

        PresenterPhoto.store(new_presenter, BLUE)
        original.refresh_from_db()
        self.assertNotEqual(original.sha256,
                            PresenterPhoto.objects.get(presenter=new_presenter).sha256)

    def test_pdf_export_has_own_photos_and_not_the_other_tenants(self):
        # A: no headshot, no session photo; B: both. A's PDF has no image.
        self.slot_a.photo_data = ''
        self.slot_a.save(update_fields=['photo_data'])
        resp = self.client.get(reverse('planner:export_mic_tracker_pdf'))
        self.assertEqual(200, resp.status_code)
        self.assertNotIn(b'/Subtype /Image', resp.content)

        PresenterPhoto.store(self.presenter_a, GREEN)
        resp = self.client.get(reverse('planner:export_mic_tracker_pdf'))
        self.assertIn(b'/Subtype /Image', resp.content)

    def test_admin_upload_and_clear(self):
        url = reverse('admin:planner_presenter_change', args=[self.presenter_a.id])
        page = self.client.get(url)
        self.assertEqual(200, page.status_code)
        self.assertNotContains(page, 'name="photo"')
        resp = self.client.post(url, {
            'name': self.presenter_a.name, 'notes': '',
            'headshot_upload': SimpleUploadedFile('h.png', GREEN, content_type='image/png'),
        })
        self.assertEqual(302, resp.status_code, resp.content[:500])
        self.assertTrue(PresenterPhoto.objects.filter(presenter=self.presenter_a).exists())

        self.client.post(url, {'name': self.presenter_a.name, 'notes': '', 'clear_headshot': 'on'})
        self.assertFalse(PresenterPhoto.objects.filter(presenter=self.presenter_a).exists())

    def test_admin_rejects_non_images(self):
        url = reverse('admin:planner_presenter_change', args=[self.presenter_a.id])
        resp = self.client.post(url, {
            'name': self.presenter_a.name, 'notes': '',
            'headshot_upload': SimpleUploadedFile('h.png', b'<svg/>', content_type='image/png'),
        })
        self.assertEqual(200, resp.status_code)
        self.assertFalse(PresenterPhoto.objects.filter(presenter=self.presenter_a).exists())

    def test_admin_cannot_reach_another_tenants_presenter(self):
        url = reverse('admin:planner_presenter_change', args=[self.presenter_b.id])
        before = self.headshot_b.sha256
        self.client.post(url, {
            'name': 'PWNED', 'notes': '', 'is_mic_label': 'on',
            'headshot_upload': SimpleUploadedFile('h.png', GREEN, content_type='image/png'),
        })
        self.headshot_b.refresh_from_db()
        self.assertEqual(before, self.headshot_b.sha256)
        self.presenter_b.refresh_from_db()
        self.assertNotEqual('PWNED', self.presenter_b.name)
        self.assertFalse(self.presenter_b.is_mic_label)


# ---------------------------------------------------------------------------
# 7. Fingerprints
# ---------------------------------------------------------------------------

class FingerprintTests(SimpleTestCase):

    def test_reuploads_are_near_identical_and_different_pictures_are_not(self):
        for raw in (RED, GREEN, BLUE):
            self.assertLessEqual(fingerprint_distance(
                photo_fingerprint(raw), photo_fingerprint(_resaved(raw))), NEAR_IDENTICAL_BITS)
            self.assertLessEqual(fingerprint_distance(
                photo_fingerprint(raw), photo_fingerprint(normalize_headshot(raw)[0])), 2)
        pics = (RED, GREEN, BLUE, GOLD, GREY)
        for i, a in enumerate(pics):
            for b in pics[i + 1:]:
                self.assertGreater(fingerprint_distance(
                    photo_fingerprint(a), photo_fingerprint(b)), NEAR_IDENTICAL_BITS)


# ---------------------------------------------------------------------------
# 8. migrate_slot_photos_to_presenters
# ---------------------------------------------------------------------------

class MigrateSlotPhotosTests(HeadshotBase):

    def setUp(self):
        super().setUp()
        PresenterPhoto.objects.all().delete()
        self.show = MicSession.objects.create(day=self.show_day_a, name='Main')

    def slot(self, presenter, raw, rf, session=None):
        a = (session or self.show).mic_assignments.get(rf_number=rf)
        s = a.presenter_slots.order_by('order').first() or \
            PresenterSlot.objects.create(assignment=a, order=0)
        s.presenter = presenter
        s.photo_data = _data_url(raw) if raw is not None else ''
        s.save()
        return s

    def person(self, name='Pat Person'):
        return Presenter.objects.create(project=self.project_a, name=name)

    def run_cmd(self, *args):
        out = StringIO()
        call_command('migrate_slot_photos_to_presenters', *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def headshot(self, presenter):
        p = PresenterPhoto.objects.filter(presenter=presenter).first()
        return bytes(p.content) if p else None

    def assertHeadshot(self, presenter, raw):
        got = self.headshot(presenter)
        self.assertIsNotNone(got, f'{presenter} got no headshot')
        self.assertSamePicture(raw, got)

    def flag(self, presenter):
        presenter.refresh_from_db()
        return presenter.is_mic_label

    def all_slot_photos(self):
        return dict(PresenterSlot.objects.exclude(photo_data='').exclude(
            photo_data__isnull=True).values_list('id', 'photo_data'))

    def test_dry_run_writes_nothing(self):
        Presenter.objects.create(project=self.project_a, name='HH 3')
        out = self.run_cmd()
        self.assertIn('DRY RUN', out)
        self.assertFalse(PresenterPhoto.objects.exists())
        self.assertFalse(Presenter.objects.filter(is_mic_label=True).exists())

    def test_person_with_one_photo_gets_a_headshot_and_keeps_the_slot_photo(self):
        before = self.all_slot_photos()
        self.run_cmd('--apply')
        self.assertHeadshot(self.presenter_a, RED)
        self.assertFalse(self.flag(self.presenter_a))
        self.assertEqual(before, self.all_slot_photos(), 'a slot photo was changed')

    def test_reuploads_of_one_photo_make_a_person(self):
        """Sutter's case: the same headshot uploaded in two sessions."""
        self.slot(self.presenter_a, _resaved(RED), 2)
        self.slot(self.presenter_a, _resaved(RED, (70, 70)), 3)
        out = self.run_cmd('--apply')
        self.assertIn('re-uploads of one photo', out)
        self.assertFalse(self.flag(self.presenter_a))
        self.assertHeadshot(self.presenter_a, RED)

    def test_different_photos_make_a_mic_label_and_keep_every_photo(self):
        """HH13's case: a different speaker in each session."""
        self.slot(self.presenter_a, GREEN, 2)
        before = self.all_slot_photos()
        out = self.run_cmd('--apply')
        self.assertIn('label: different photos', out)
        self.assertTrue(self.flag(self.presenter_a))
        self.assertIsNone(self.headshot(self.presenter_a))
        self.assertEqual(before, self.all_slot_photos())

    def test_label_name_wins_even_with_one_photo(self):
        hh = Presenter.objects.create(project=self.project_a, name='HH13')
        self.slot(hh, GREEN, 2)
        self.run_cmd('--apply')
        self.assertTrue(self.flag(hh))
        self.assertIsNone(self.headshot(hh))

    def test_label_name_without_a_photo_is_flagged(self):
        qa = Presenter.objects.create(project=self.project_a, name='Q&A 2')
        self.run_cmd('--apply')
        self.assertTrue(self.flag(qa))

    def test_already_flagged_stays_a_label(self):
        Presenter.objects.filter(id=self.presenter_a.id).update(is_mic_label=True)
        out = self.run_cmd('--apply')
        self.assertIn('label: already flagged', out)
        self.assertTrue(self.flag(self.presenter_a))
        self.assertIsNone(self.headshot(self.presenter_a))

    def test_person_override_takes_the_most_used_photo(self):
        self.slot(self.presenter_a, GREEN, 2)
        self.slot(self.presenter_a, GREEN, 3)   # GREEN on 2 slots beats RED on 1
        self.run_cmd('--apply', '--person', str(self.presenter_a.id))
        self.assertFalse(self.flag(self.presenter_a))
        self.assertHeadshot(self.presenter_a, GREEN)

    def test_person_override_tie_goes_to_newest_slot(self):
        self.slot(self.presenter_a, GREEN, 2)   # newer than slot_a, one each
        self.run_cmd('--apply', '--person', str(self.presenter_a.id))
        self.assertHeadshot(self.presenter_a, GREEN)

    def test_person_override_unflags_a_label(self):
        hh = Presenter.objects.create(project=self.project_a, name='HH 5', is_mic_label=True)
        self.slot(hh, GREEN, 2)
        self.run_cmd('--apply', '--person', str(hh.id))
        self.assertFalse(self.flag(hh))
        self.assertHeadshot(hh, GREEN)

    def test_choose_picks_the_photo(self):
        self.slot(self.presenter_a, GREEN, 2)
        self.run_cmd('--apply', '--choose', f'{self.presenter_a.id}={self.slot_a.id}')
        self.assertFalse(self.flag(self.presenter_a))
        self.assertHeadshot(self.presenter_a, RED)

    def test_label_override(self):
        self.run_cmd('--apply', '--label', str(self.presenter_a.id))
        self.assertTrue(self.flag(self.presenter_a))
        self.assertIsNone(self.headshot(self.presenter_a))

    def test_skip_touches_nothing(self):
        hh = Presenter.objects.create(project=self.project_a, name='HH 6')
        self.run_cmd('--apply', '--skip', f'{hh.id},{self.presenter_a.id}')
        self.assertFalse(self.flag(hh))
        self.assertIsNone(self.headshot(self.presenter_a))

    def test_bad_overrides_stop_the_run(self):
        pid = self.presenter_a.id
        for args in (['--choose', f'{pid}={self.slot_b.id}'],   # not their photo
                     ['--choose', 'nonsense'],
                     ['--person', '999999'],                     # no such presenter
                     ['--label', str(pid), '--person', str(pid)],
                     ['--skip', str(pid), '--choose', f'{pid}={self.slot_a.id}'],
                     ['--label', 'abc']):
            with self.subTest(args):
                with self.assertRaises(CommandError):
                    self.run_cmd('--apply', *args)
        self.assertFalse(PresenterPhoto.objects.exists())
        self.assertFalse(Presenter.objects.filter(is_mic_label=True).exists())

    def test_override_for_another_project_is_refused_with_project_filter(self):
        with self.assertRaises(CommandError):
            self.run_cmd('--project', str(self.project_a.id), '--label', str(self.presenter_b.id))

    def test_existing_headshot_is_kept_unless_chosen_or_overwrite(self):
        PresenterPhoto.store(self.presenter_a, GREEN)
        self.run_cmd('--apply')
        self.assertHeadshot(self.presenter_a, GREEN)
        self.run_cmd('--apply', '--overwrite')
        self.assertHeadshot(self.presenter_a, RED)

    def test_report_lists_every_presenter_with_a_way_to_flip_it(self):
        hh = Presenter.objects.create(project=self.project_a, name='HH 4')
        nobody = self.person('Nobody Photo')
        out = self.run_cmd()
        self.assertIn(f'--label {self.presenter_a.id}', out)
        self.assertIn(f'--person {hh.id}', out)
        self.assertNotIn('Nobody Photo', out)
        self.assertIn('Nobody Photo', self.run_cmd('--verbose'))
        self.assertTrue(nobody.pk)

    def test_orphan_slot_is_reported_and_kept(self):
        orphan = self.slot(None, GREEN, 2)
        out = self.run_cmd('--apply')
        self.assertIn(f'slot {orphan.id}', out)
        orphan.refresh_from_db()
        self.assertEqual(_data_url(GREEN), orphan.photo_data)

    def test_never_crosses_projects(self):
        """A slot in A naming B's presenter: B's presenter gets nothing from it."""
        cross = self.slot(self.presenter_b, GREEN, 2)
        self.slot_b.photo_data = ''
        self.slot_b.save(update_fields=['photo_data'])
        out = self.run_cmd('--apply')
        self.assertIn(f'slot {cross.id}', out)
        self.assertIsNone(self.headshot(self.presenter_b))

    def test_project_filter(self):
        Presenter.objects.create(project=self.project_b, name='HH 1 ZZTENANTB')
        self.run_cmd('--apply', '--project', str(self.project_a.id))
        self.assertIsNotNone(self.headshot(self.presenter_a))
        self.assertIsNone(self.headshot(self.presenter_b))
        self.assertFalse(Presenter.objects.filter(project=self.project_b, is_mic_label=True).exists())

    def test_unreadable_photo_is_reported(self):
        self.slot_a.photo_data = _data_url(b'<html>', mime='image/png')
        self.slot_a.save(update_fields=['photo_data'])
        out = self.run_cmd('--apply')
        self.assertIn('UNREADABLE', out)
        self.assertIsNone(self.headshot(self.presenter_a))

    def test_same_name_presenters_are_not_merged(self):
        twin = Presenter.objects.create(project=self.project_a, name=self.presenter_a.name)
        self.slot(twin, GREEN, 2)
        out = self.run_cmd('--apply')
        self.assertIn('SAME-NAME', out)
        self.assertHeadshot(self.presenter_a, RED)
        self.assertHeadshot(twin, GREEN)

    def test_classify_is_pure(self):
        """The plan for a data set can be worked out without a database --
        what the read-only prod preview relies on."""
        from planner.utils import slot_photo_migration as spm
        people = [spm.PresenterInfo(1, 'HH13', 7, 'P'), spm.PresenterInfo(2, 'Jo', 7, 'P'),
                  spm.PresenterInfo(3, 'Al', 7, 'P')]
        fp = photo_fingerprint
        rows = [spm.PhotoRow(10, 1, 7, 7, 'D1', 'a', 'image/png', 1, fp(RED)),
                spm.PhotoRow(11, 2, 7, 7, 'D1', 'b', 'image/png', 1, fp(GREEN)),
                spm.PhotoRow(12, 2, 7, 7, 'D2', 'c', 'image/png', 1, fp(_resaved(GREEN))),
                spm.PhotoRow(13, 3, 7, 7, 'D1', 'd', 'image/png', 1, fp(BLUE)),
                spm.PhotoRow(14, 3, 7, 7, 'D2', 'e', 'image/png', 1, fp(GOLD))]
        kinds = {d.presenter.id: d.kind for d in spm.classify(people, rows).decisions}
        self.assertEqual({1: spm.LABEL_NAME, 2: spm.PERSON_NEAR, 3: spm.LABEL_PHOTOS}, kinds)
