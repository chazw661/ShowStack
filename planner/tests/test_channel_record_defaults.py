"""Regression tests for the channel default_record opt-in flag.

Issue #15 behaviour: the Default Record checkbox on each console channel
controls whether that channel appears in the multitrack picker at all.
When an engineer picker-adds a channel, the resulting MultitrackTrack
inherits `enabled=True` from default_record=True (the only state that
reaches the picker).

The endpoints under test are:
  - planner.views.multitrack_editor (renders the picker)
  - planner.views.multitrack_add_tracks (POST add-tracks endpoint)
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from planner.models import (
    Console,
    ConsoleInput,
    MultitrackSession,
    MultitrackTrack,
    Project,
)

User = get_user_model()


class ChannelRecordDefaultsSeedTests(TestCase):
    """default_record must control picker visibility and seed enabled."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pol-tester',
            email='pol-tester@example.com',
            password='test-password-123',
            is_staff=True,
        )
        cls.project = Project.objects.create(
            name='POL Test Show', owner=cls.user,
        )
        cls.console = Console.objects.create(
            project=cls.project, name='Test CL5',
        )
        cls.session = MultitrackSession.objects.create(
            project=cls.project, console=cls.console, name='POL Smoke',
            target_daw='reaper', feed_source='console_dante',
            track_order_mode='console',
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        # CurrentProjectMiddleware reads request.session['current_project_id'].
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def _add_input(self, input_ch, default_record=True):
        return ConsoleInput.objects.create(
            console=self.console,
            input_ch=input_ch,
            source=f'Ch {input_ch}',
            dante_number=input_ch,
            default_record=default_record,
        )

    def _picker_add(self, input_pk):
        url = reverse(
            'planner:multitrack_add_tracks', args=[self.session.id]
        )
        response = self.client.post(
            url,
            data=json.dumps({
                'selections': {'inputs': [input_pk]},
                'manuals': [],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_default_record_true_seeds_enabled_true(self):
        """default_record=True → track.enabled=True."""
        inp = self._add_input('1', default_record=True)
        self._picker_add(inp.pk)
        track = MultitrackTrack.objects.get(session=self.session, source_id=inp.pk)
        self.assertTrue(track.enabled)

    def test_default_record_false_hidden_from_picker(self):
        """default_record=False → channel does not appear in the picker.

        Issue #15: unchecking Default Record removes the channel from the
        multitrack picker entirely. The editor view embeds the picker data
        as JSON in the page; the channel id must not appear there.
        """
        kept = self._add_input('1', default_record=True)
        hidden = self._add_input('2', default_record=False)

        url = reverse('planner:multitrack_editor', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8', errors='replace')

        self.assertIn(f'"id": {kept.pk}', body)
        self.assertNotIn(f'"id": {hidden.pk}', body)
