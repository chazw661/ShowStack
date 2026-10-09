"""The public surface of the site, pinned.

``LoginRequiredMiddleware`` (added in the tenant-isolation audit) default-denies
every anonymous request. That is the right default, but it means the handful of
pages that *must* answer a logged-out visitor now do so only because something
explicitly opted them out -- ``@login_not_required`` in our code, or
``@method_decorator(login_not_required, name='dispatch')`` inside Django for the
built-in auth views.

Two failure modes, so two kinds of test here:

1. **The site goes dark.** A page that has to work logged out (login, password
   reset, an invite link, the marketing pages) ends up behind the login wall,
   and nobody notices until a user cannot sign in.
   -> ``AnonymousReachabilityTests`` drives each one as an anonymous client.

2. **The wall quietly grows a hole.** Someone adds ``@login_not_required`` to a
   view that handles tenant data, and no test objects.
   -> ``ExemptRouteInventoryTests`` freezes the exempt set. Any addition or
   removal fails with a diff, forcing a deliberate decision.

Run with::

    python manage.py test planner.tests.test_login_exemptions \
        --settings=audiopatch.test_settings
"""

import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLPattern, URLResolver
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from planner.models import Invitation, Project


def iter_routes():
    """Every routed ``URLPattern`` in the project, as
    ``(path, dotted_view_name, is_exempt)``.

    Walks the resolver tree rather than ``reverse_dict`` -- namespaced names
    live in ``namespace_dict``, and a sweep over ``reverse_dict`` alone matches
    nothing and would make the whole test vacuous.
    """
    def walk(resolver, prefix=''):
        for pattern in resolver.url_patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                view = pattern.callback
                # ``login_not_required`` sets ``login_required = False``; the
                # middleware reads it with a default of True. For class-based
                # views ``as_view()`` copies ``dispatch.__dict__`` onto the view
                # function, so the attribute survives.
                exempt = getattr(view, 'login_required', True) is False
                dotted = '{}.{}'.format(
                    getattr(view, '__module__', '?'),
                    getattr(view, '__qualname__', getattr(view, '__name__', '?')),
                )
                yield '/' + prefix + str(pattern.pattern), dotted, exempt

    yield from walk(get_resolver())


# ---------------------------------------------------------------------------
# 1. The exempt set, frozen
# ---------------------------------------------------------------------------

class ExemptRouteInventoryTests(TestCase):
    """Every route the middleware lets through anonymously, enumerated.

    Keep this list honest: a new entry means a new slice of the app answers the
    public internet. Add one only after deciding the view carries its own
    authentication (a token, a signed link) or genuinely serves public content.
    """

    # (url pattern, view) -- the url is included because two different views
    # can answer the same path (marketing wins /login/ and /register/ because
    # marketing.urls is included first in audiopatch/urls.py).
    EXPECTED = {
        # -- Marketing: public by design -----------------------------------
        ('/', 'marketing.views.home'),
        ('/about/', 'marketing.views.about'),
        ('/contact/', 'marketing.views.contact'),
        ('/features/', 'marketing.views.features'),
        ('/pricing/', 'marketing.views.pricing'),
        ('/privacy/', 'marketing.views.privacy'),
        ('/terms/', 'marketing.views.terms'),
        ('/pending/', 'marketing.views.pending'),
        ('/api/waitlist/', 'marketing.views.waitlist_ajax'),

        # -- Sign-in / sign-up ---------------------------------------------
        # Both /login/ and /register/ are declared twice; marketing's copy is
        # the one that actually resolves. Both are exempt, so resolution order
        # cannot strand a visitor either way.
        ('/login/', 'marketing.views.user_login'),
        ('/login/', 'accounts.views.View.as_view.<locals>.view'),
        ('/logout/', 'marketing.views.user_logout'),
        ('/register/', 'marketing.views.register'),
        ('/register/', 'accounts.views.register'),
        ('/m/login/', 'planner.mobile_views.mobile_login'),

        # -- Django admin login (exempt inside django.contrib.admin) --------
        # Mounted twice: showstack_admin_site at /admin/, and the default
        # admin.site at /audiopatch/admin/ (planner/urls.py).
        ('/admin/login/', 'django.contrib.admin.sites.AdminSite.login'),
        ('/audiopatch/admin/login/', 'django.contrib.admin.sites.AdminSite.login'),

        # -- Password reset: all four steps, exempt inside django.contrib.auth
        ('/password-reset/', 'django.contrib.auth.views.View.as_view.<locals>.view'),
        ('/password-reset/done/', 'django.contrib.auth.views.View.as_view.<locals>.view'),
        ('/reset/<uidb64>/<token>/', 'django.contrib.auth.views.View.as_view.<locals>.view'),
        ('/reset/done/', 'django.contrib.auth.views.View.as_view.<locals>.view'),

        # -- Invite link: renders a preview before the visitor has an account
        ('/invitations/accept/<uuid:token>/', 'accounts.views.accept_invitation'),

        # -- Companion / agent APIs: no session, authenticate by token ------
        # These MUST stay exempt or the companion can never reach its own
        # token check. Each one is responsible for its own 401/403.
        ('/audiopatch/api/listen/session/', 'planner.views_listen.listen_session'),
        ('/audiopatch/api/listen/heartbeat/', 'planner.views_listen.listen_heartbeat'),
        ('/audiopatch/network-monitor/api/heartbeat/', 'planner.views_monitor.agent_heartbeat'),
        ('/audiopatch/network-monitor/api/stop/', 'planner.views_monitor.agent_stop'),
        ('/audiopatch/network-monitor/api/scan-results/', 'planner.views_monitor.agent_scan_results'),
        ('/audiopatch/network-monitor/api/poll-results/', 'planner.views_monitor.agent_poll_results'),
        ('/audiopatch/network-monitor/api/remove-device/', 'planner.views_monitor.agent_remove_device'),
        ('/audiopatch/network-monitor/api/devices/', 'planner.views_monitor.agent_device_list'),
        ('/audiopatch/network-monitor/api/snmp-settings/', 'planner.views_monitor.agent_snmp_settings'),
        ('/audiopatch/network-monitor/api/snmp-results/', 'planner.views_monitor.agent_snmp_results'),
        ('/audiopatch/network-monitor/api/dante-results/', 'planner.views_monitor.agent_dante_results'),
    }

    def test_middleware_is_actually_installed(self):
        """Without this, every assertion below passes for the wrong reason."""
        self.assertIn(
            'django.contrib.auth.middleware.LoginRequiredMiddleware',
            settings.MIDDLEWARE,
            'LoginRequiredMiddleware is gone -- undecorated views are public again',
        )

    def test_middleware_sits_after_authentication_middleware(self):
        """It reads ``request.user``, which AuthenticationMiddleware sets."""
        order = list(settings.MIDDLEWARE)
        self.assertLess(
            order.index('django.contrib.auth.middleware.AuthenticationMiddleware'),
            order.index('django.contrib.auth.middleware.LoginRequiredMiddleware'),
        )

    def test_the_sweep_actually_finds_routes(self):
        """Guard against iter_routes() quietly matching nothing."""
        routes = list(iter_routes())
        self.assertGreater(len(routes), 300, 'route sweep found almost nothing')

    def test_exempt_routes_are_exactly_the_audited_set(self):
        found = {(url, view) for url, view, exempt in iter_routes() if exempt}

        added = sorted(found - self.EXPECTED)
        removed = sorted(self.EXPECTED - found)

        msg = []
        if added:
            msg.append(
                'NEW public routes -- these now answer the public internet.\n'
                'Confirm each carries its own authentication, then add it to '
                'EXPECTED:\n  ' + '\n  '.join(f'{u}  ->  {v}' for u, v in added)
            )
        if removed:
            msg.append(
                'Routes that LOST their exemption -- a logged-out visitor is '
                'now redirected to login here, which may have taken part of '
                'the site down:\n  '
                + '\n  '.join(f'{u}  ->  {v}' for u, v in removed)
            )
        self.assertEqual([], msg, '\n\n'.join(msg))

    def test_nothing_under_planner_is_public_except_the_token_apis(self):
        """A second, coarser net: no planner view may be exempt unless it is
        one of the companion/agent token APIs or the mobile login page."""
        offenders = [
            (url, view) for url, view, exempt in iter_routes()
            if exempt
            and view.startswith('planner.')
            and not view.startswith(('planner.views_monitor.agent_',
                                     'planner.views_listen.listen_',
                                     'planner.mobile_views.mobile_login'))
        ]
        self.assertEqual([], offenders, f'planner views made public: {offenders}')


# ---------------------------------------------------------------------------
# 2. Each public page, driven logged out
# ---------------------------------------------------------------------------

class AnonymousReachabilityTests(TestCase):
    """Every page on the must-work-logged-out list, actually fetched.

    A 302 to ``/login/`` is the failure signature these tests exist to catch,
    so assertions are on the status code rather than on page content.
    """

    def setUp(self):
        self.anon = Client()

    def assertNotRedirectedToLogin(self, resp, label):
        login_url = reverse('login')
        if resp.status_code in (301, 302):
            target = resp.headers.get('Location', '')
            self.assertFalse(
                target.startswith(login_url),
                f'{label} redirects a logged-out visitor to {target}',
            )

    # -- marketing / landing ------------------------------------------------

    def test_marketing_pages_are_public(self):
        blocked = []
        for name in ('marketing:home', 'marketing:features', 'marketing:pricing',
                     'marketing:contact', 'marketing:about', 'marketing:privacy',
                     'marketing:terms', 'marketing:pending'):
            resp = self.anon.get(reverse(name))
            if resp.status_code != 200:
                blocked.append(f'{name} -> {resp.status_code}')
        self.assertEqual([], blocked, '\n'.join(blocked))

    def test_waitlist_endpoint_accepts_an_anonymous_post(self):
        resp = self.anon.post(
            reverse('marketing:waitlist_ajax'), {'email': 'nobody@example.com'},
        )
        self.assertEqual(200, resp.status_code)
        # Reaching its own form validation (rather than the login wall) is the
        # point; whether the address is accepted is the view's business.
        self.assertIn('success', resp.json())

    # -- login / logout / signup -------------------------------------------

    def test_login_page_is_reachable(self):
        resp = self.anon.get(reverse('login'))
        self.assertEqual(200, resp.status_code)

    def test_login_actually_authenticates(self):
        """The page rendering is not enough -- the POST must work too."""
        User.objects.create_user('exempt_user', 'e@example.com', 'pw-exempt-123')
        resp = self.anon.post(
            reverse('login'),
            {'username': 'exempt_user', 'password': 'pw-exempt-123'},
        )
        self.assertIn(resp.status_code, (200, 302))
        self.assertIn(
            '_auth_user_id', self.anon.session,
            'a logged-out visitor could not sign in',
        )

    def test_logout_does_not_require_a_session(self):
        """Hitting /logout/ with no session must not bounce to login (which,
        with ``?next=/logout/``, is a loop a user cannot escape)."""
        resp = self.anon.get(reverse('logout'))
        self.assertNotRedirectedToLogin(resp, 'logout')
        self.assertIn(resp.status_code, (200, 302))

    def test_register_page_is_reachable(self):
        resp = self.anon.get(reverse('register'))
        self.assertEqual(200, resp.status_code)

    def test_mobile_login_is_reachable(self):
        resp = self.anon.get(reverse('mobile:login'))
        self.assertEqual(200, resp.status_code)

    def test_admin_login_is_reachable(self):
        """The custom ShowStackAdminSite must not override away the exemption
        Django puts on ``AdminSite.login``."""
        resp = self.anon.get('/admin/login/')
        self.assertEqual(200, resp.status_code)

    def test_admin_index_bounces_anonymous_to_the_admin_login(self):
        resp = self.anon.get('/admin/')
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn('login', resp.headers.get('Location', ''))

    # -- password reset, all four steps ------------------------------------

    def test_password_reset_form_is_reachable(self):
        resp = self.anon.get(reverse('password_reset'))
        self.assertEqual(200, resp.status_code)

    def test_password_reset_post_sends_the_email(self):
        User.objects.create_user('reset_user', 'reset@example.com', 'pw-reset-123')
        resp = self.anon.post(
            reverse('password_reset'), {'email': 'reset@example.com'},
        )
        self.assertEqual(302, resp.status_code)
        self.assertTrue(
            resp.headers['Location'].startswith(reverse('password_reset_done')),
            'password reset did not reach its success_url',
        )

    def test_password_reset_done_is_reachable(self):
        resp = self.anon.get(reverse('password_reset_done'))
        self.assertEqual(200, resp.status_code)

    def test_password_reset_confirm_accepts_a_real_token(self):
        user = User.objects.create_user('confirm_user', 'c@example.com', 'pw-old-123')
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        url = reverse('password_reset_confirm',
                      kwargs={'uidb64': uidb64, 'token': token})
        # Django's confirm view redirects the token URL to a set-password URL
        # that carries the token in the session.
        resp = self.anon.get(url, follow=True)
        self.assertEqual(200, resp.status_code)
        self.assertNotIn(
            reverse('login'), [r[0] for r in resp.redirect_chain],
            'password reset confirm was intercepted by the login wall',
        )

    def test_password_reset_complete_is_reachable(self):
        resp = self.anon.get(reverse('password_reset_complete'))
        self.assertEqual(200, resp.status_code)

    # -- invite accept ------------------------------------------------------

    def test_invite_link_renders_a_preview_for_a_visitor_with_no_account(self):
        owner = User.objects.create_user('inviter', 'owner@example.com', 'pw-own-123')
        project = Project.objects.create(name='Invite Show', owner=owner)
        invitation = Invitation.objects.create(
            project=project, email='guest@example.com',
            role='viewer', invited_by=owner,
        )
        resp = self.anon.get(
            reverse('accept_invitation', kwargs={'token': invitation.token}),
        )
        self.assertEqual(
            200, resp.status_code,
            'an invited user cannot see the invitation before signing up',
        )

    # -- companion / agent token APIs --------------------------------------

    def test_agent_api_reaches_its_own_token_check(self):
        """401 from the view, not 302 from the middleware."""
        resp = self.anon.get(reverse('planner:agent_device_list'))
        self.assertEqual(
            401, resp.status_code,
            'the agent API no longer reaches its own Bearer-token check',
        )

    def test_listen_api_reaches_its_own_token_check(self):
        """401 "Missing listen token" from the view, not 302 from the
        middleware -- the companion has no session to redirect."""
        resp = self.anon.get(reverse('planner:listen_session'))
        self.assertEqual(
            401, resp.status_code,
            'the Listen API no longer reaches its own listen-token check',
        )

    def test_listen_api_rejects_a_bogus_token(self):
        """A token that is present but wrong is 403, not 401 -- so this and the
        test above together prove the view, not the wall, is answering."""
        resp = self.anon.get(
            reverse('planner:listen_session'), {'token': 'not-a-uuid'},
        )
        self.assertEqual(403, resp.status_code)

    # -- static assets ------------------------------------------------------

    def test_static_assets_are_served_above_the_login_wall(self):
        """WhiteNoise sits above LoginRequiredMiddleware in MIDDLEWARE, so
        static files never reach the auth check. If the two are ever reordered,
        a logged-out login page loses its CSS."""
        order = list(settings.MIDDLEWARE)
        self.assertLess(
            order.index('whitenoise.middleware.WhiteNoiseMiddleware'),
            order.index('django.contrib.auth.middleware.LoginRequiredMiddleware'),
            'WhiteNoise moved below the login wall -- static files now 302',
        )

    def test_media_route_if_registered_must_be_exempt(self):
        """``django.views.static.serve`` carries no exemption, so the DEBUG-only
        media route would 302 an anonymous visitor to login. Under DEBUG=False
        the route is not registered at all (``conf.urls.static`` no-ops), which
        is why this does not bite in production."""
        media_routes = [
            (url, view, exempt) for url, view, exempt in iter_routes()
            if view == 'django.views.static.serve'
        ]
        if not media_routes:
            self.skipTest('no media route registered (DEBUG=False)')
        for url, view, exempt in media_routes:
            self.assertTrue(
                exempt,
                f'{url} serves user uploads but is behind the login wall',
            )


# ---------------------------------------------------------------------------
# 3. Negative controls -- the wall is actually standing
# ---------------------------------------------------------------------------

class PrivateRoutesStayPrivateTests(TestCase):
    """If these started passing anonymously, the exemption tests above would
    still pass, so assert the other direction too."""

    def setUp(self):
        self.anon = Client()

    def test_dashboard_is_not_public(self):
        resp = self.anon.get('/dashboard/')
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn('login', resp.headers.get('Location', ''))

    def test_planner_views_are_not_public(self):
        for name in ('planner:dashboard_stats', 'planner:comm_config_list_templates'):
            resp = self.anon.get(reverse(name))
            self.assertNotEqual(
                200, resp.status_code, f'{name} answered anonymously',
            )

    def test_listen_status_view_is_session_only(self):
        """``listen_app_status`` is the web UI's own view, not the companion's,
        so unlike its two siblings it must stay behind the wall."""
        resp = self.anon.get(reverse('planner:listen_app_status'))
        self.assertNotEqual(200, resp.status_code)


# ---------------------------------------------------------------------------
# 4. Deploy config -- nothing public is expected that does not exist
# ---------------------------------------------------------------------------

class DeployConfigTests(TestCase):
    """There is no Stripe/webhook endpoint and no HTTP health-check path in
    this project. Both are the kind of thing that gets added later and silently
    breaks: a webhook would 302 the provider to a login page, and a Railway
    ``healthcheckPath`` would fail every deploy. Fail here if one appears
    without an exemption."""

    def test_no_webhook_route_exists_without_an_exemption(self):
        unexempt_webhooks = [
            (url, view) for url, view, exempt in iter_routes()
            if ('webhook' in url.lower() or 'webhook' in view.lower()) and not exempt
        ]
        self.assertEqual(
            [], unexempt_webhooks,
            'a webhook endpoint exists behind the login wall -- the provider '
            'will receive a 302 to /login/ instead of delivering the event',
        )

    def test_railway_healthcheck_path_if_set_must_be_exempt(self):
        config = Path(settings.BASE_DIR) / 'railway.json'
        if not config.exists():
            self.skipTest('railway.json not present')
        deploy = json.loads(config.read_text()).get('deploy', {})
        path = deploy.get('healthcheckPath')
        if not path:
            return  # current state: Railway uses a TCP check, nothing to exempt
        exempt_paths = {url for url, _, exempt in iter_routes() if exempt}
        self.assertIn(
            path, exempt_paths,
            f'railway.json healthcheckPath {path} is behind the login wall -- '
            'every deploy will fail its health check',
        )
