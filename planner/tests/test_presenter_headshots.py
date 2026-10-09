"""Presenter headshots: the photo follows the presenter, and never leaves the
project.

Isolation tests are in the #101 shape (``TenantIsolationBase``): project A is
the session we drive, project B is the victim, and B's photo bytes must never
appear in anything A is served. The rest pin the behaviour the feature exists
for -- one upload shows on every card that presenter is on -- and the
slot-to-presenter migration's rule.

Run with::

    python manage.py test planner.tests.test_presenter_headshots \\
        --settings=audiopatch.test_settings
"""

import base64
import json
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse
from PIL import Image

from planner.models import (
    MicSession, Presenter, PresenterPhoto, PresenterSlot, Project, UserProfile,
)
from planner.tests.test_presenter_photo_hardening import PhotoTenantBase
from planner.utils.presenter_photos import headshot_url, legacy_slot_photo_url


def _png(color, size=(8, 8)):
    buf = BytesIO()
    Image.new('RGB', size, color).save(buf, format='PNG')
    return buf.getvalue()


def _data_url(raw, mime='image/png'):
    return f'data:{mime};base64,{base64.b64encode(raw).decode()}'


RED, GREEN, BLUE = _png((255, 0, 0)), _png((0, 255, 0)), _png((0, 0, 255))


class HeadshotBase(PhotoTenantBase):
    """PhotoTenantBase's slots, but holding real images, plus a headshot for B."""

    def setUp(self):
        super().setUp()
        for tag, raw in (('a', RED), ('b', BLUE)):
            slot = getattr(self, f'slot_{tag}')
            slot.photo_data = _data_url(raw)
            slot.save(update_fields=['photo_data'])
        self.headshot_b = PresenterPhoto.store(self.presenter_b, _png((1, 2, 3)))

    def loner(self):
        """Logged in, but a member of nothing."""
        user = User.objects.create_user('loner', 'l@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'free'})
        c = Client()
        c.force_login(user)
        return c

    def second_session_slot(self, presenter):
        """``presenter`` on RF 1 of a second session in project A."""
        session = MicSession.objects.create(day=self.show_day_a, name='Second AAA')
        assignment = session.mic_assignments.get(rf_number=1)
        slot = assignment.presenter_slots.order_by('order').first() or \
            PresenterSlot.objects.create(assignment=assignment, order=0)
        slot.presenter = presenter
        slot.is_active = True
        slot.save()
        return slot


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
# 2. The transitional legacy endpoint
# ---------------------------------------------------------------------------

class LegacySlotPhotoTests(HeadshotBase):

    def get(self, client, slot):
        return client.get(reverse('planner:legacy_slot_photo', args=[slot.id]))

    def test_other_tenants_slot_is_404(self):
        resp = self.get(self.client, self.slot_b)
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

    def test_never_serves_non_image_bytes(self):
        """The old upload trusted the browser's Content-Type, so a stored
        'image/png' can hold HTML. It must not come back out."""
        self.slot_a.photo_data = _data_url(b'<script>alert(1)</script>', mime='image/png')
        self.slot_a.save(update_fields=['photo_data'])
        self.assertEqual(404, self.get(self.client, self.slot_a).status_code)


# ---------------------------------------------------------------------------
# 3. The photo follows the presenter
# ---------------------------------------------------------------------------

class FollowsPresenterTests(HeadshotBase):

    def upload(self, slot, raw=GREEN):
        return self.client.post(reverse('planner:upload_slot_photo'), {
            'slot_id': slot.id,
            'photo': SimpleUploadedFile('p.png', raw, content_type='image/png'),
        })

    def test_upload_in_one_session_shows_in_another(self):
        """The feature: a photo attached in one session appears wherever that
        presenter is put."""
        other = self.second_session_slot(self.presenter_a)
        resp = self.upload(self.slot_a)
        self.assertEqual(200, resp.status_code, resp.content)
        url = resp.json()['photo_url']
        self.assertTrue(url.startswith(reverse('planner:presenter_photo',
                                               args=[self.presenter_a.id])))

        page = self.client.get(reverse('planner:mic_tracker')).content.decode()
        self.assertIn(f'data-photo="{url}"', page)
        self.assertGreaterEqual(page.count(f'data-photo="{url}"'), 2,
                                'the headshot is not on both sessions\' rows')

        rows = self.client.get(reverse('planner:mic_tracker_sync')).json()['slots']
        by_slot = {r['slot_id']: r for r in rows}
        self.assertEqual(url, by_slot[self.slot_a.id]['photo'])
        self.assertEqual(url, by_slot[other.id]['photo'])

    def test_headshot_beats_the_slots_legacy_photo(self):
        PresenterPhoto.store(self.presenter_a, GREEN)
        rows = self.client.get(reverse('planner:mic_tracker_sync')).json()['slots']
        row = next(r for r in rows if r['slot_id'] == self.slot_a.id)
        self.assertTrue(row['photo'].startswith(
            reverse('planner:presenter_photo', args=[self.presenter_a.id])))

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

    def test_presenter_change_drops_the_previous_persons_legacy_photo(self):
        """Without this, the fallback would put the old presenter's face on
        the new one."""
        newcomer = Presenter.objects.create(project=self.project_a, name='Newcomer')
        resp = self.client.post(
            reverse('planner:update_mic_assignment'),
            data=json.dumps({'assignment_id': self.mic_assignment_a.id,
                             'field': 'presenter_id', 'value': str(newcomer.id)}),
            content_type='application/json')
        self.assertEqual('', resp.json()['photo_url'])
        self.slot_a.refresh_from_db()
        self.assertEqual('', self.slot_a.photo_data)

    def test_upload_without_a_presenter_is_refused(self):
        self.slot_a.presenter = None
        self.slot_a.save(update_fields=['presenter'])
        resp = self.upload(self.slot_a)
        self.assertEqual(400, resp.status_code)
        self.assertIn('presenter', resp.json()['error'])
        self.assertFalse(PresenterPhoto.objects.filter(
            presenter__project=self.project_a).exists())

    @mock.patch('planner.utils.safe_fetch.fetch_public')
    def test_url_upload_without_a_presenter_fetches_nothing(self, fetch):
        self.slot_a.presenter = None
        self.slot_a.save(update_fields=['presenter'])
        resp = self.client.post(
            reverse('planner:upload_slot_photo_from_url'),
            data=json.dumps({'slot_id': self.slot_a.id, 'url': 'https://img.example.com/a.png'}),
            content_type='application/json')
        self.assertEqual(400, resp.status_code)
        fetch.assert_not_called()

    def test_slot_pointing_at_another_tenants_presenter_cannot_write_it(self):
        """Corrupt data (a slot in A naming B's presenter) must not become a
        way to replace B's headshot."""
        self.slot_a.presenter = self.presenter_b
        self.slot_a.save(update_fields=['presenter'])
        before = self.headshot_b.sha256
        resp = self.upload(self.slot_a)
        self.assertEqual(404, resp.status_code)
        self.headshot_b.refresh_from_db()
        self.assertEqual(before, self.headshot_b.sha256)

    def test_swap_carries_legacy_photos_with_their_presenters(self):
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
                self.assertNotIn(legacy_slot_photo_url(self.slot_b.id), body)
                self.assertNotIn(self.MARKER_B, body)

    def test_typing_orphan_with_a_headshot_is_kept(self):
        dan = Presenter.objects.create(project=self.project_a, name='Dan')
        PresenterPhoto.store(dan, GREEN)
        self.assertFalse(dan.retire_if_typing_orphan('Dana'))
        self.assertTrue(Presenter.objects.filter(id=dan.id).exists())


# ---------------------------------------------------------------------------
# 4. Duplication, PDF export, admin
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
        self.assertEqual(0, PresenterPhoto.objects.filter(
            presenter__project=new_project).exclude(presenter__project=new_project).count())

    def test_pdf_export_has_own_photos_and_not_the_other_tenants(self):
        # A: no headshot, no legacy photo; B: a headshot. A's PDF has no image.
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
            'name': 'PWNED', 'notes': '',
            'headshot_upload': SimpleUploadedFile('h.png', GREEN, content_type='image/png'),
        })
        self.headshot_b.refresh_from_db()
        self.assertEqual(before, self.headshot_b.sha256)
        self.presenter_b.refresh_from_db()
        self.assertNotEqual('PWNED', self.presenter_b.name)


# ---------------------------------------------------------------------------
# 5. migrate_slot_photos_to_presenters
# ---------------------------------------------------------------------------

class MigrateSlotPhotosTests(HeadshotBase):

    def setUp(self):
        super().setUp()
        PresenterPhoto.objects.all().delete()
        self.show = MicSession.objects.create(day=self.show_day_a, name='Main')

    def slot(self, presenter, raw, rf):
        a = self.show.mic_assignments.get(rf_number=rf)
        s = a.presenter_slots.order_by('order').first() or \
            PresenterSlot.objects.create(assignment=a, order=0)
        s.presenter = presenter
        s.photo_data = _data_url(raw) if raw is not None else ''
        s.save()
        return s

    def run_cmd(self, *args):
        out = StringIO()
        call_command('migrate_slot_photos_to_presenters', *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def stored(self, presenter):
        p = PresenterPhoto.objects.filter(presenter=presenter).first()
        if p is None:
            return None
        return Image.open(BytesIO(bytes(p.content))).convert('RGB').getpixel((0, 0))

    def assertColor(self, presenter, rgb):
        got = self.stored(presenter)
        self.assertIsNotNone(got, f'{presenter} got no headshot')
        self.assertTrue(all(abs(a - b) < 12 for a, b in zip(got, rgb)), (got, rgb))

    def test_dry_run_writes_nothing(self):
        out = self.run_cmd()
        self.assertIn('DRY RUN', out)
        self.assertFalse(PresenterPhoto.objects.exists())

    def test_single_photo_moves_up_and_slot_keeps_it(self):
        self.run_cmd('--apply')
        self.assertColor(self.presenter_a, (255, 0, 0))
        self.slot_a.refresh_from_db()
        self.assertEqual(_data_url(RED), self.slot_a.photo_data, 'rollback copy was cleared')

    def test_conflict_most_used_wins(self):
        self.slot(self.presenter_a, GREEN, 2)
        self.slot(self.presenter_a, GREEN, 3)   # GREEN x2 beats RED x1, though RED's slot is older
        out = self.run_cmd('--apply', '--project', str(self.project_a.id))
        self.assertIn('CONFLICTS', out)
        self.assertColor(self.presenter_a, (0, 255, 0))

    def test_conflict_tie_goes_to_newest_slot(self):
        self.slot(self.presenter_a, GREEN, 2)   # newer than slot_a, one each
        self.run_cmd('--apply')
        self.assertColor(self.presenter_a, (0, 255, 0))

    def test_choose_overrides_the_rule(self):
        self.slot(self.presenter_a, GREEN, 2)
        self.run_cmd('--apply', '--choose', f'{self.presenter_a.id}={self.slot_a.id}')
        self.assertColor(self.presenter_a, (255, 0, 0))

    def test_choose_must_name_that_presenters_photo(self):
        with self.assertRaises(CommandError):
            self.run_cmd('--choose', f'{self.presenter_a.id}={self.slot_b.id}')
        with self.assertRaises(CommandError):
            self.run_cmd('--choose', 'nonsense')
        self.assertFalse(PresenterPhoto.objects.exists())

    def test_existing_headshot_is_kept_unless_chosen_or_overwrite(self):
        PresenterPhoto.store(self.presenter_a, GREEN)
        self.run_cmd('--apply')
        self.assertColor(self.presenter_a, (0, 255, 0))
        self.run_cmd('--apply', '--overwrite')
        self.assertColor(self.presenter_a, (255, 0, 0))

    def test_rerunning_choose_after_apply_replaces_the_pick(self):
        """The runbook: --apply with the rule, read the conflicts, then fix
        the ones that are wrong."""
        green = self.slot(self.presenter_a, GREEN, 2)
        self.run_cmd('--apply')
        self.assertColor(self.presenter_a, (0, 255, 0))
        self.run_cmd('--apply', '--choose', f'{self.presenter_a.id}={self.slot_a.id}')
        self.assertColor(self.presenter_a, (255, 0, 0))
        self.assertTrue(green.pk)

    def test_orphan_slot_is_reported_not_moved(self):
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
        self.assertIsNone(self.stored(self.presenter_b))

    def test_project_filter(self):
        self.run_cmd('--apply', '--project', str(self.project_a.id))
        self.assertIsNotNone(self.stored(self.presenter_a))
        self.assertIsNone(self.stored(self.presenter_b))

    def test_unreadable_photo_is_reported(self):
        self.slot_a.photo_data = _data_url(b'<html>', mime='image/png')
        self.slot_a.save(update_fields=['photo_data'])
        out = self.run_cmd('--apply')
        self.assertIn('UNREADABLE', out)
        self.assertIsNone(self.stored(self.presenter_a))

    def test_same_name_presenters_are_not_merged(self):
        twin = Presenter.objects.create(project=self.project_a, name=self.presenter_a.name)
        self.slot(twin, GREEN, 2)
        out = self.run_cmd('--apply')
        self.assertIn('SAME-NAME', out)
        self.assertColor(self.presenter_a, (255, 0, 0))
        self.assertColor(twin, (0, 255, 0))
        self.assertTrue(Presenter.objects.filter(id=twin.id).exists())
