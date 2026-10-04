"""The Mic Tracker header strip reports what is known, not what is not.

Show / Venue / Room / Dates used to render as four labels over four em-dashes
whenever MicShowInfo was blank -- which is every brand new project, so it was
the first thing most people saw, and on an iPad it cost a line of a screen
that is mostly table. The strip is now rendered only when at least one of the
four is filled, and only the filled ones appear inside it.

That is template logic rather than CSS, so it is testable, and this is the
only behavioural change in the iPad touch/layout pass -- everything else in
that pass is sizing. Follows the Client + force_login shape used by
planner/tests/test_crew_rosters.py.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from planner.models import MicShowInfo, Project

User = get_user_model()


class MicTrackerHeaderStripTests(TestCase):
    """The four meta fields, and the strip that holds them."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='a1-owner',
            email='a1@example.com',
            password='test-pw-123',
            is_staff=True,
            is_superuser=True,
        )
        cls.project = Project.objects.create(name='Test Show', owner=cls.owner)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.owner)
        # The view resolves the project from the session, the way every other
        # planner view does (CurrentProjectMiddleware).
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def _get(self):
        return self.client.get(reverse('planner:mic_tracker'))

    def _show_info(self, **fields):
        """The view get_or_creates this row, so update rather than create."""
        info, _ = MicShowInfo.objects.get_or_create(project=self.project)
        for name, value in fields.items():
            setattr(info, name, value)
        info.save()
        return info

    def test_strip_is_absent_when_nothing_is_filled_in(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('class="mtt-show-meta"', html)
        # And specifically none of the four labels that used to sit over a dash.
        for label in ('>Show<', '>Venue<', '>Room<', '>Dates<'):
            self.assertNotIn(label, html)

    def test_only_the_filled_field_is_shown(self):
        self._show_info(venue_name='Moscone West')
        html = self._get().content.decode()
        self.assertIn('class="mtt-show-meta"', html)
        self.assertIn('Moscone West', html)
        self.assertIn('>Venue<', html)
        # The three empty ones are gone entirely -- not rendered as dashes.
        self.assertNotIn('>Show<', html)
        self.assertNotIn('>Room<', html)
        self.assertNotIn('>Dates<', html)

    def test_all_four_filled_shows_all_four(self):
        import datetime

        self._show_info(
            show_name='Annual Kickoff',
            venue_name='Moscone West',
            ballroom_name='Hall D',
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 3, 5),
        )
        html = self._get().content.decode()
        for label in ('>Show<', '>Venue<', '>Room<', '>Dates<'):
            self.assertIn(label, html)
        self.assertIn('Annual Kickoff', html)
        self.assertIn('Hall D', html)
        self.assertIn('03/02-03/05', html)

    def test_dates_alone_is_enough_to_render_the_strip(self):
        """duration_display is a property, not a field -- it has to count too."""
        import datetime

        self._show_info(
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 3, 5),
        )
        html = self._get().content.decode()
        self.assertIn('class="mtt-show-meta"', html)
        self.assertIn('>Dates<', html)
        self.assertNotIn('>Venue<', html)
