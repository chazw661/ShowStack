"""Mic Tracker Overview: the Notes column.

Overview notes write PresenterSlot.notes through update_slot_field, the same
field and endpoint as the A1 and A2 notes. The Overview save also sends
``expected`` (the note it last saw); if the note has changed since, the save is
refused with the current note so the page can show both. The A1/A2 tabs send
no ``expected`` and save exactly as before.
"""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.models import MicSession, PresenterSlot, Project, ProjectMember, ShowDay, UserProfile


class OverviewNotesTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('notes_owner', password='pw', is_staff=True)
        self.viewer = User.objects.create_user('notes_viewer', password='pw', is_staff=True)
        for user in (self.owner, self.viewer):
            UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='Notes show', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.viewer, role='viewer',
                                     invited_by=self.owner)
        day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 1))
        session = MicSession.objects.create(day=day, name='Keynote', num_mics=1, order=0)
        assignment = session.mic_assignments.first()
        self.slot = (assignment.presenter_slots.order_by('order').first()
                     or PresenterSlot.objects.create(assignment=assignment, order=0))
        self.slot.notes = 'battery swap at break'
        self.slot.is_active = True
        self.slot.save()
        self.login(self.owner)

    def login(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()

    def save(self, **body):
        body = {'slot_id': self.slot.id, 'field': 'notes', **body}
        return self.client.post(reverse('planner:update_slot_field'), json.dumps(body),
                                content_type='application/json')

    def note(self):
        self.slot.refresh_from_db()
        return self.slot.notes

    # -- the endpoint --------------------------------------------------------

    def test_save_with_matching_expected(self):
        resp = self.save(value='new note', expected='battery swap at break')
        self.assertIs(True, resp.json()['success'])
        self.assertEqual('new note', self.note())

    def test_stale_expected_is_a_conflict_and_saves_nothing(self):
        resp = self.save(value='mine', expected='what I loaded earlier')
        data = resp.json()
        self.assertEqual((False, True, 'battery swap at break'),
                         (data['success'], data['conflict'], data['current']))
        self.assertEqual('battery swap at break', self.note())

    def test_line_endings_and_edge_whitespace_are_not_a_conflict(self):
        # An admin form stores CRLF; a textarea reports LF and drops a leading newline.
        self.slot.notes = '\nline one\r\nline two'
        self.slot.save(update_fields=['notes'])
        resp = self.save(value='replaced', expected='line one\nline two')
        self.assertTrue(resp.json()['success'])
        self.assertEqual('replaced', self.note())

    def test_empty_expected_against_a_blank_note(self):
        self.slot.notes = ''
        self.slot.save(update_fields=['notes'])
        self.assertTrue(self.save(value='first', expected='').json()['success'])
        self.assertEqual('first', self.note())

    def test_callers_without_expected_are_unchanged(self):
        # The A1/A2 tabs: no expected, saves whatever the note currently is.
        resp = self.save(value='from A2')
        self.assertIs(True, resp.json()['success'])
        self.assertEqual('from A2', self.note())
        # expected: null is the same as absent.
        self.assertTrue(self.save(value='again', expected=None).json()['success'])
        self.assertEqual('again', self.note())

    def test_expected_is_ignored_for_other_fields(self):
        resp = self.save(field='mic_type', value='LAV', expected='anything')
        self.assertIs(True, resp.json()['success'])
        self.slot.refresh_from_db()
        self.assertEqual('LAV', self.slot.mic_type)

    def test_viewer_is_refused(self):
        self.login(self.viewer)
        for body in ({'value': 'x'}, {'value': 'x', 'expected': 'battery swap at break'}):
            with self.subTest(body=body):
                resp = self.save(**body)
                self.assertEqual(403, resp.status_code)
        self.assertEqual('battery swap at break', self.note())

    # -- the page ------------------------------------------------------------

    def overview(self):
        resp = self.client.get(reverse('planner:mic_tracker_overview'))
        self.assertEqual(200, resp.status_code)
        return resp.content.decode()

    def test_editor_gets_a_notes_box_bound_to_the_slot(self):
        html = self.overview()
        self.assertIn('<th class="mto-th-notes mto-col-notes">Notes</th>', html)
        self.assertIn("mtoSaveSlotField({}, 'notes', this.value, this)".format(self.slot.id), html)
        self.assertIn('>battery swap at break</textarea>', html)

    def test_viewer_gets_text_not_a_box(self):
        self.login(self.viewer)
        html = self.overview()
        self.assertNotIn('class="mto-notes-input"', html)
        self.assertIn('<span class="mto-notes-text" tabindex="0">battery swap at break</span>', html)

    def test_note_is_escaped_for_both(self):
        self.slot.notes = '</textarea><img src=x onerror=alert(1)>'
        self.slot.save(update_fields=['notes'])
        for user in (self.owner, self.viewer):
            with self.subTest(user=user.username):
                self.login(user)
                html = self.overview()
                self.assertNotIn('<img src=x', html)
                self.assertIn('&lt;/textarea&gt;&lt;img src=x onerror=alert(1)&gt;', html)

    def test_empty_session_row_spans_every_column(self):
        day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        MicSession.objects.create(day=day, name='Empty', num_mics=0, order=0)
        html = self.overview()
        self.assertIn('<tr><td colspan="7"', html)
        self.assertNotIn('colspan="6"', html)
