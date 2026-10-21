"""The project's shareable access-request link never uses the Railway host.

It was hard-coded to https://showstack-production.up.railway.app, so every
link an owner copied and sent to crew carried the Railway address. It now
follows the host the owner is on, except a *.railway.app host, which is
swapped for settings.SITE_URL (https://showstack.io).

Run with::

    python manage.py test planner.tests.test_share_link \\
        --settings=audiopatch.test_settings
"""

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from planner.models import Project
from planner.utils.public_url import public_url


class ShareLinkTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('own', 'own@example.com', 'pw')
        self.project = Project.objects.create(name='Show', owner=self.user)
        self.client.force_login(self.user)
        self.path = f'/projects/request/{self.project.invite_token}/'

    def page(self, host):
        return self.client.get(
            reverse('admin:planner_project_change', args=[self.project.pk]),
            HTTP_HOST=host, secure=True).content.decode()

    def test_on_showstack_io_the_link_is_showstack_io(self):
        html = self.page('showstack.io')
        self.assertIn(f'value="https://showstack.io{self.path}"', html)
        self.assertNotIn('railway.app', html.split('Shareable Access Request Link')[1][:2000])

    def test_reached_through_railway_the_link_is_still_showstack_io(self):
        html = self.page('showstack-production.up.railway.app')
        self.assertIn(f'value="https://showstack.io{self.path}"', html)
        self.assertNotIn(f'railway.app{self.path}', html)

    @override_settings(SITE_URL='https://staging.example.com')
    def test_railway_host_falls_back_to_the_configured_site_url(self):
        html = self.page('showstack-production.up.railway.app')
        self.assertIn(f'value="https://staging.example.com{self.path}"', html)

    def test_local_dev_keeps_its_own_host(self):
        request = RequestFactory().get('/', HTTP_HOST='localhost:8000')
        self.assertEqual(public_url('/x/', request), 'http://localhost:8000/x/')

    def test_without_a_request_it_is_the_site_url(self):
        self.assertEqual(public_url('/x/'), 'https://showstack.io/x/')
