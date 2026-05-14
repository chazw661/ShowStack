"""Regression tests for POL-01 (default_record) and POL-02 (default_record_color).

Phase 5 seed-field behaviour: when an engineer picker-adds channels to a
multitrack session, each new MultitrackTrack inherits:
  - `enabled`        from channel.default_record         (POL-01)
  - `color_override` from channel.default_record_color   (POL-02, hex-validated)

Defence-in-depth: malformed hex in the DB does not crash the picker —
bad values silently drop to ''.

End-to-end: a seeded color survives the full chain into the Reaper RPP
export (PEAKCOL field), proving POL-02 is wired all the way through to
the DAW file engineers actually open.

The endpoint under test is planner.views.multitrack_add_tracks
(POST /audiopatch/multitrack/<session_id>/add-tracks/) and the Reaper
exporter at planner.views.multitrack_export_rpp.
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
from planner.utils.reaper_export import hex_to_peakcol

User = get_user_model()


class ChannelRecordDefaultsSeedTests(TestCase):
    """multitrack_add_tracks must seed enabled + color_override from the channel."""

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

    def _add_input(self, input_ch, default_record=True, default_record_color=''):
        return ConsoleInput.objects.create(
            console=self.console,
            input_ch=input_ch,
            source=f'Ch {input_ch}',
            dante_number=input_ch,
            default_record=default_record,
            default_record_color=default_record_color,
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
        """POL-01 happy path: default_record=True → track.enabled=True."""
        inp = self._add_input('1', default_record=True, default_record_color='')
        self._picker_add(inp.pk)
        track = MultitrackTrack.objects.get(session=self.session, source_id=inp.pk)
        self.assertTrue(track.enabled)
        self.assertEqual(track.color_override, '')

    def test_default_record_false_seeds_enabled_false(self):
        """POL-01 opt-out: default_record=False → track.enabled=False."""
        inp = self._add_input('2', default_record=False, default_record_color='')
        self._picker_add(inp.pk)
        track = MultitrackTrack.objects.get(session=self.session, source_id=inp.pk)
        self.assertFalse(track.enabled)

    def test_default_record_color_seeds_color_override(self):
        """POL-02 happy path: default_record_color='#FF8800' → track.color_override='#FF8800'."""
        inp = self._add_input('3', default_record=True, default_record_color='#FF8800')
        self._picker_add(inp.pk)
        track = MultitrackTrack.objects.get(session=self.session, source_id=inp.pk)
        self.assertEqual(track.color_override, '#FF8800')
        self.assertTrue(track.enabled)

    def test_malformed_default_record_color_drops_silently(self):
        """Defence-in-depth: bad hex in DB → track.color_override='', no crash."""
        inp = self._add_input('4', default_record=True, default_record_color='')
        # Bypass form validator by writing the bad value directly.
        ConsoleInput.objects.filter(pk=inp.pk).update(
            default_record_color='not-a-hex'
        )
        # Endpoint must return 200 and silently drop the bad hex.
        self._picker_add(inp.pk)
        track = MultitrackTrack.objects.get(session=self.session, source_id=inp.pk)
        self.assertEqual(track.color_override, '')
        self.assertTrue(track.enabled)  # POL-01 unaffected by hex corruption

    def test_seeded_color_appears_in_reaper_export(self):
        """End-to-end: seeded color flows into the Reaper RPP PEAKCOL field.

        Proves the full POL-02 chain works:
          channel.default_record_color
            → multitrack_add_tracks (seed)
            → MultitrackTrack.color_override (DB)
            → multitrack_export_rpp (Reaper RPP body, PEAKCOL line)

        Uses hex_to_peakcol() to compute the expected packed-RGB integer
        so the test is robust to packing-formula changes in the exporter.
        """
        seed_hex = '#FF8800'
        inp = self._add_input('5', default_record=True, default_record_color=seed_hex)
        self._picker_add(inp.pk)

        # Compute the expected Reaper-packed value the same way the
        # exporter does. Hard-coding a magic int here would couple the
        # test to the packing formula and break on legitimate refactors.
        expected_peakcol = hex_to_peakcol(seed_hex)
        expected_token = str(expected_peakcol)

        export_url = reverse(
            'planner:multitrack_export_rpp', args=[self.session.id]
        )
        response = self.client.get(export_url)
        self.assertEqual(response.status_code, 200, response.content[:500])

        body = response.content.decode('utf-8', errors='replace')
        self.assertIn(
            expected_token,
            body,
            msg=(
                f"Expected Reaper-packed value {expected_token!r} for "
                f"seed hex {seed_hex!r} not found in RPP export body. "
                "POL-02 end-to-end chain is broken between "
                "MultitrackTrack.color_override and the exporter."
            ),
        )
