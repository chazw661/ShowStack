"""Regression test for multitrack_reorder (TRK-05 / WR-04).

Discovered in production 2026-05-14: dragging a track in the editor
moved the row visually but the AJAX `/multitrack/<id>/reorder/` POST
returned 500. Root cause was a single-pass bulk_update against
`unique_together = [('session', 'track_number')]` — any swap-style
reorder produces an intermediate state where two tracks share the
same track_number, and PostgreSQL rolls the statement back.

Fix in `planner/views.py:multitrack_reorder` does the renumber in two
phases inside a transaction (negate all tracks first, then assign
1..N). This test exercises that path: a 3-track session swaps the
first and last tracks via the AJAX endpoint and asserts the new
ordering persists in the database.
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from planner.models import (
    Console,
    ConsoleInput,
    MultitrackSession,
    MultitrackTrack,
    Project,
)

User = get_user_model()


class MultitrackReorderRegressionTests(TestCase):
    """The AJAX reorder endpoint must persist swap-style reorders."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='reorder-tester',
            email='reorder-tester@example.com',
            password='test-password-123',
        )
        cls.project = Project.objects.create(
            name='Reorder Test Show', owner=cls.user,
        )
        cls.console = Console.objects.create(
            project=cls.project, name='Test CL5',
        )
        cls.session = MultitrackSession.objects.create(
            project=cls.project, console=cls.console, name='Reorder Smoke',
            target_daw='reaper', feed_source='console_dante',
            track_order_mode='console',
        )
        cls.inputs = [
            ConsoleInput.objects.create(
                console=cls.console, input_ch=str(n),
                source=f'Ch {n}', dante_number=str(n),
            )
            for n in range(1, 4)
        ]
        cls.tracks = [
            MultitrackTrack.objects.create(
                session=cls.session, track_number=n,
                source_type='input', source_id=inp.pk,
                enabled=True,
            )
            for n, inp in enumerate(cls.inputs, start=1)
        ]

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def test_swap_first_and_last_tracks_persists(self):
        """Drag track 3 to position 1 (and bubble 1 → 2, 2 → 3).

        Posted ordered_ids = [track3.id, track1.id, track2.id].

        Pre-fix this hits an IntegrityError on `unique_together`
        because bulk_update transitions through a state where two
        rows share the same (session, track_number). After the fix,
        the two-phase update completes and the new order persists.
        """
        t1, t2, t3 = self.tracks
        new_order = [t3.id, t1.id, t2.id]

        response = self.client.post(
            f'/audiopatch/multitrack/{self.session.id}/reorder/',
            data=json.dumps({'ordered_ids': new_order}),
            content_type='application/json',
        )

        self.assertEqual(
            response.status_code, 200,
            f'Expected 200, got {response.status_code}: {response.content!r}',
        )
        self.assertEqual(response.json(), {'ok': True})

        # Reload from DB and confirm the new numbering.
        t1.refresh_from_db()
        t2.refresh_from_db()
        t3.refresh_from_db()
        self.assertEqual(t3.track_number, 1)
        self.assertEqual(t1.track_number, 2)
        self.assertEqual(t2.track_number, 3)

        # Session ordering query reflects the new order.
        ids_in_order = list(
            self.session.tracks.order_by('track_number').values_list('id', flat=True)
        )
        self.assertEqual(ids_in_order, new_order)

    def test_full_reverse_persists(self):
        """Reverse the full track list. Stress-tests the two-phase
        update across N rows (not just a pairwise swap).
        """
        t1, t2, t3 = self.tracks
        new_order = [t3.id, t2.id, t1.id]

        response = self.client.post(
            f'/audiopatch/multitrack/{self.session.id}/reorder/',
            data=json.dumps({'ordered_ids': new_order}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        ids_in_order = list(
            self.session.tracks.order_by('track_number').values_list('id', flat=True)
        )
        self.assertEqual(ids_in_order, new_order)
