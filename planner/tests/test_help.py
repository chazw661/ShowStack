"""In-app help: the registry stays wired to real pages, and never leaks a tenant.

Four promises, one class each:

1. **Every topic is real.** Its template exists, renders with nothing in the
   context, carries no template logic, and fits the 200-word budget.
2. **Every topic's pages exist.** A page key that no longer resolves -- a view
   renamed or removed -- fails here, naming the topic, instead of quietly
   dropping that topic out of the page's Help.
3. **Every page with a Help link leads somewhere.** The crawl GETs every page
   it can build a URL for, as a superuser with a full project, and any page
   that renders a Help link must map to at least one topic. Pages that
   deliberately have none are listed in ``UNHELPED`` with the reason.
4. **Help is tenant-safe and login-only.** The views touch no database at all,
   and a project's names never appear on any help page.

Run with::

    python manage.py test planner.tests.test_help --settings=audiopatch.test_settings
"""

import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.db import connection
from django.template import TemplateDoesNotExist
from django.template.loader import get_template, render_to_string
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver, resolve, reverse
from django.urls.resolvers import URLPattern, URLResolver
from django.utils.html import strip_tags

from planner.help import views as help_views
from planner.help.context import page_key, topics_for
from planner.help.topics import SECTIONS, TOPICS, TOPICS_BY_SLUG
from planner.models import (
    CommConfig, Console, Crew, Device, Location, MicSession, MultitrackSession,
    PowerDistributionPlan, Project, ShowDay, SignalFlowDiagram,
    SoundvisionPrediction, UserProfile,
)

WORD_LIMIT = 200


def iter_view_names():
    """Every routed view name, namespaced (``admin:planner_console_changelist``),
    with its full path pattern."""
    def walk(resolver, prefix='', namespace=''):
        for pattern in resolver.url_patterns:
            if isinstance(pattern, URLResolver):
                # Application namespace, as page_key() uses: the admin is
                # instance "showstack_admin" of app "admin".
                own = pattern.app_name or pattern.namespace
                ns = namespace
                if own:
                    ns = '{}:{}'.format(namespace, own) if namespace else own
                yield from walk(pattern, prefix + str(pattern.pattern), ns)
            elif isinstance(pattern, URLPattern) and pattern.name:
                name = '{}:{}'.format(namespace, pattern.name) if namespace else pattern.name
                yield name, '/' + prefix + str(pattern.pattern)
    yield from walk(get_resolver())


def visible_words(html):
    text = strip_tags(html).replace('[CHECK]', ' ')
    return re.findall(r"[\w'’.-]+", text)


# ---------------------------------------------------------------------------
# 1. Topics
# ---------------------------------------------------------------------------

class HelpTopicRegistryTests(TestCase):

    def test_registry_is_not_empty(self):
        self.assertGreaterEqual(len(TOPICS), 50)

    def test_slugs_are_unique(self):
        slugs = [t.slug for t in TOPICS]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertEqual(len(TOPICS_BY_SLUG), len(TOPICS))

    def test_every_topic_is_in_a_known_section(self):
        for t in TOPICS:
            self.assertIn(t.section, SECTIONS, t.slug)

    def test_every_section_has_topics(self):
        used = {t.section for t in TOPICS}
        self.assertEqual(set(SECTIONS), used)

    def test_every_topic_names_at_least_one_page(self):
        for t in TOPICS:
            self.assertTrue(t.pages, '{} is tied to no page'.format(t.slug))
            self.assertIsInstance(t.pages, tuple, t.slug)

    def test_every_topic_template_exists_and_is_plain_html(self):
        for t in TOPICS:
            try:
                tpl = get_template(t.template)
            except TemplateDoesNotExist:
                self.fail('{} has no template {}'.format(t.slug, t.template))
            source = tpl.template.source
            # Fragments are rendered with an empty context; template logic in
            # one is either dead or a way to pull request data into help.
            self.assertNotIn('{%', source, t.slug)
            self.assertNotIn('{{', source, t.slug)
            self.assertNotIn('<script', source.lower(), t.slug)
            self.assertNotIn('style=', source.lower(), t.slug)

    def test_every_topic_has_a_lede_and_steps(self):
        for t in TOPICS:
            html = render_to_string(t.template)
            self.assertIn('class="help-lede"', html, t.slug)
            self.assertIn('<ol>', html, t.slug)

    def test_every_topic_fits_the_word_budget(self):
        over = []
        for t in TOPICS:
            n = len(visible_words(render_to_string(t.template)))
            if n > WORD_LIMIT:
                over.append('{} ({} words)'.format(t.slug, n))
        self.assertEqual(over, [], 'Topics over {} words: {}'.format(WORD_LIMIT, over))

    def test_no_topic_ships_with_a_check_marker(self):
        # [CHECK] marks a claim nobody has verified yet. Resolve it (delete the
        # marker if the claim is right, fix the text if not) before merging.
        marked = []
        for t in TOPICS:
            source = get_template(t.template).template.source
            n = max(len(re.findall(r'\[CHECK\]', source, re.IGNORECASE)),
                    source.count('help-check'))
            if n:
                marked.append('{} ({})'.format(t.slug, n))
        self.assertEqual(marked, [], 'Unresolved [CHECK] markers: {}'.format(marked))


# ---------------------------------------------------------------------------
# 2. Page keys resolve
# ---------------------------------------------------------------------------

class HelpTopicPagesExistTests(TestCase):

    def test_every_topic_page_key_is_a_routed_view(self):
        routed = {name for name, _ in iter_view_names()}
        missing = [
            '{} -> {}'.format(t.slug, key)
            for t in TOPICS for key in t.pages if key not in routed
        ]
        self.assertEqual(
            missing, [],
            'Help topics point at pages that no longer exist (renamed or '
            'removed?): {}'.format(missing),
        )

    def test_the_walk_sees_namespaced_names(self):
        # Guard against a vacuous pass: the walk must see all three namespaces.
        routed = {name for name, _ in iter_view_names()}
        self.assertIn('admin:planner_console_changelist', routed)
        self.assertIn('planner:mic_tracker', routed)
        self.assertIn('mobile:dashboard', routed)
        self.assertIn('help:index', routed)


class PageKeyTests(TestCase):
    """Admin add/change/delete pages share their changelist's topics."""

    def setUp(self):
        self.factory = RequestFactory()

    def key_for(self, path):
        request = self.factory.get(path)
        request.resolver_match = resolve(path)
        return page_key(request)

    def test_admin_model_pages_collapse_to_the_changelist(self):
        for path in (
            '/admin/planner/console/',
            '/admin/planner/console/add/',
            '/admin/planner/console/7/change/',
            '/admin/planner/console/7/delete/',
            '/admin/planner/console/7/history/',
        ):
            self.assertEqual(self.key_for(path), 'admin:planner_console_changelist', path)

    def test_custom_admin_views_keep_their_own_name(self):
        path = reverse('admin:console_template_library')
        self.assertEqual(self.key_for(path), 'admin:console_template_library')

    def test_plain_views_use_their_view_name(self):
        self.assertEqual(self.key_for(reverse('planner:mic_tracker')), 'planner:mic_tracker')
        self.assertEqual(self.key_for(reverse('mobile:dashboard')), 'mobile:dashboard')

    def test_no_resolver_match_is_no_key(self):
        self.assertEqual(page_key(self.factory.get('/')), '')

    def test_unknown_key_has_no_topics(self):
        self.assertEqual(topics_for('nope:nothing'), [])
        self.assertEqual(topics_for(''), [])


# ---------------------------------------------------------------------------
# 3. Every page with a Help link maps to a topic
# ---------------------------------------------------------------------------

class _HelpLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get('class') or ''
        if tag == 'a' and ('data-help-link' in attrs or 'mobile-help-link' in cls):
            self.hrefs.append(attrs.get('href', ''))


class EveryHelpLinkLeadsToATopicTests(TestCase):
    """Crawl every page we can build a URL for and follow its Help link."""

    # Pages that render a Help link but deliberately have no topic of their
    # own: help opens on the full index. Each entry says why.
    UNHELPED = {
        # Django / superuser plumbing, not crew workflows.
        'admin:auth_user_changelist': 'superuser account admin',
        'admin:auth_group_changelist': 'superuser permission groups',
        'admin:password_change': 'Django change-password form',
        'admin:password_change_done': 'Django change-password form',
        'admin:app_list': 'admin app index',
        'admin:planner_userprofile_changelist': 'superuser account admin',
        'admin:planner_projectmember_changelist': 'superuser view of memberships; crew use Project page',
        'admin:planner_invitation_changelist': 'superuser view; crew use Manage Invitations',
        'admin:planner_crew_changelist': 'superuser view; crew use My Crew',
        'planner:populate_amp_models': 'superuser maintenance',
        # Hidden from the sidebar (admin_ordering.always_hidden) or scrapped.
        'admin:planner_ampmodel_changelist': 'hidden: amp model catalogue',
        'admin:planner_micgroup_changelist': 'hidden: managed inside Mic Tracker',
        'admin:planner_monitorsession_changelist': 'Network Monitor (scrapped)',
        'admin:planner_discovereddevice_changelist': 'Network Monitor (scrapped)',
        'admin:planner_pollresult_changelist': 'Network Monitor (scrapped)',
        'admin:planner_deviceevent_changelist': 'Network Monitor (scrapped)',
        'admin:planner_projectsnmpconfig_changelist': 'Network Monitor (scrapped)',
        'admin:planner_switchportsnapshot_changelist': 'Network Monitor (scrapped)',
        'planner:network_monitor': 'Network Monitor (scrapped)',
        'admin:planner_consoleimport_changelist': 'hidden: import audit history (#6)',
        'admin:planner_multitracktemplate_changelist': 'hidden: managed inside Multitrack (#17)',
        'planner:debug_device_ordering': 'developer debug page',
        # The help pages themselves carry no Help link, but listed for clarity.
        'help:index': 'help itself',
    }

    # URLs never fetched: they change state on GET, end the session, or are
    # machine endpoints rather than pages.
    SKIP_PATH = re.compile(
        r'(^/api/|/api/|export|pdf|csv|\.png|\.rpp|\.nlpr|rtracktemplate|logout|'
        r'switch-project|set-project|delete|leave-project|populate|toggle|'
        r'autocomplete|/state/|/save/|/update/|/add/$|/create/$|/remove/|'
        r'/reorder/|/rename/|/duplicate/|/capacity/|/chips/|/assign|/import/$|'
        r'jsi18n|password-reset|/reset/|/r/<|request-scan|snmp|show-mode|'
        r'^/audiopatch/admin/|accept/<|/request/<|get_next_bp_number|'
        r'/matrix/|/summary/|/speakers/|/photo/|session-photo|legacy-photo|'
        r'/media/|/static/)'
    )

    # Pages the crawl must reach, so it can't pass by crawling nothing.
    MUST_REACH = ('admin:planner_console_changelist', 'planner:mic_tracker',
                  'mobile:dashboard', 'dashboard', 'crew_index',
                  'planner:power_distribution_calculator')

    def make_user(self):
        return User.objects.create_superuser('help_su', 'su@example.com', 'pw')

    def setUp(self):
        self.user = self.make_user()
        UserProfile.objects.update_or_create(user=self.user, defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='Crawl Project', owner=self.user)
        location = Location.objects.create(project=self.project, name='FOH')
        console = Console.objects.create(project=self.project, name='PM7', location=location)
        Device.objects.create(project=self.project, name='Rio 1', location=location)
        day = ShowDay.objects.create(project=self.project, date=date(2026, 10, 8),
                                     name='Day 1', order=0)
        session = MicSession.objects.create(day=day, name='General', num_mics=2, order=0)
        prediction = SoundvisionPrediction.objects.create(project=self.project,
                                                          file_name='main.pdf')
        comm = CommConfig.objects.create(project=self.project, name='Arcadia')
        mt = MultitrackSession.objects.create(
            project=self.project, console=console, name='Record',
            target_daw='reaper', feed_source='console_dante', track_order_mode='console',
        )
        flow = SignalFlowDiagram.objects.create(project=self.project, name='Flow')
        crew = Crew.objects.create(owner=self.user, name='House crew')
        plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='Hall',
                                                    created_by=self.user)
        self.kwargs = {
            'project_id': self.project.pk, 'console_id': console.pk,
            'day_id': day.pk, 'session_id': session.pk,
            'prediction_id': prediction.pk, 'pk': prediction.pk,
            'config_id': comm.pk, 'diagram_id': flow.pk, 'crew_id': crew.pk,
            'plan_id': plan.pk,
        }
        # Multitrack routes reuse ``session_id`` for their own session.
        self.multitrack_session_id = mt.pk

        self.client = Client()
        self.client.force_login(self.user)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()

    def build_url(self, name, path):
        params = re.findall(r'<(?:\w+:)?(\w+)>', path)
        kwargs = {}
        for p in params:
            if p == 'session_id' and name.startswith('planner:multitrack'):
                kwargs[p] = self.multitrack_session_id
            elif p in self.kwargs:
                kwargs[p] = self.kwargs[p]
            else:
                return None
        try:
            return reverse(name, kwargs=kwargs)
        except Exception:
            return None

    def test_every_page_with_a_help_link_maps_to_a_topic(self):
        checked, unmapped, errors = [], [], []
        seen = set()
        for name, path in iter_view_names():
            if name in seen or self.SKIP_PATH.search(path):
                continue
            seen.add(name)
            # Admin change/add/delete pages collapse to the changelist key,
            # which is checked on its own; only crawl the changelist.
            if name.startswith('admin:') and re.search(r'_(add|change|delete|history)$', name):
                continue
            url = self.build_url(name, path)
            if url is None:
                continue
            try:
                response = self.client.get(url)
            except Exception as exc:  # a broken page is not this test's subject
                errors.append('{} {}: {!r}'.format(name, url, exc)[:200])
                continue
            if response.status_code != 200 or 'html' not in response.get('Content-Type', ''):
                continue
            parser = _HelpLinkParser()
            parser.feed(response.content.decode('utf-8', 'replace'))
            if not parser.hrefs:
                continue
            for href in parser.hrefs:
                query = parse_qs(urlparse(href).query)
                key = (query.get('for') or [''])[0]
                checked.append(name)
                if key in self.UNHELPED or name in self.UNHELPED:
                    continue
                if not topics_for(key):
                    unmapped.append('{} ({}) -> for={!r}'.format(name, url, key))

        # Not vacuous: the crawl reached the admin, planner, accounts and mobile pages.
        self.assertGreaterEqual(len(set(checked)), 25, sorted(set(checked)))
        for must in self.MUST_REACH:
            self.assertIn(must, checked, 'crawl never reached {}'.format(must))
        self.assertEqual(
            sorted(set(unmapped)), [],
            'Pages with a Help link but no help topic (add a topic, or list the '
            'page in UNHELPED with a reason):\n' + '\n'.join(sorted(set(unmapped))),
        )

    def test_unhelped_entries_are_real_pages(self):
        routed = {name for name, _ in iter_view_names()}
        stale = [k for k in self.UNHELPED if k not in routed]
        self.assertEqual(stale, [], 'UNHELPED lists pages that no longer exist')

    def test_unhelped_pages_really_have_no_topic(self):
        both = [k for k in self.UNHELPED if topics_for(k)]
        self.assertEqual(both, [], 'These have topics now; drop them from UNHELPED')


class EveryHelpLinkLeadsToATopicAsOwnerTests(EveryHelpLinkLeadsToATopicTests):
    """The same crawl as a project owner who is not a superuser: the pages
    they see differ (the power plan admin list sends them to the calculator,
    whose no-plan state carries its own Help link)."""

    def make_user(self):
        return User.objects.create_user('help_owner', 'owner@example.com', 'pw', is_staff=True)

    def test_power_plan_admin_list_is_not_crawled_as_a_page(self):
        resp = self.client.get(reverse('admin:planner_powerdistributionplan_changelist'))
        self.assertRedirects(resp, reverse('planner:power_distribution_calculator'),
                             fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# 4. Tenant safety and login
# ---------------------------------------------------------------------------

class HelpTenantSafetyTests(TestCase):

    SECRET = 'ZZSECRETTOUR'

    def setUp(self):
        self.user = User.objects.create_user('help_user', 'u@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=self.user, defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='Project ' + self.SECRET, owner=self.user)
        location = Location.objects.create(project=self.project, name='Loc ' + self.SECRET)
        Console.objects.create(project=self.project, name='Desk ' + self.SECRET, location=location)
        self.client = Client()
        self.client.force_login(self.user)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()

    def help_urls(self):
        yield reverse('help:index')
        yield reverse('help:index') + '?for=admin:planner_console_changelist'
        for t in TOPICS:
            yield reverse('help:topic', args=[t.slug])

    def test_no_project_data_on_any_help_page(self):
        for url in self.help_urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotIn(self.SECRET, response.content.decode(), url)

    def test_help_views_never_touch_the_database(self):
        factory = RequestFactory()
        request = factory.get('/help/', {'for': 'admin:planner_console_changelist'})
        request.user = self.user
        with CaptureQueriesContext(connection) as ctx:
            help_views.help_index(request)
            help_views.help_topic(request, TOPICS[0].slug)
        self.assertEqual(len(ctx.captured_queries), 0,
                         [q['sql'] for q in ctx.captured_queries])

    def test_anonymous_is_sent_to_login(self):
        anon = Client()
        for url in (reverse('help:index'), reverse('help:topic', args=[TOPICS[0].slug])):
            response = anon.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn('login', response['Location'], url)

    def test_unknown_topic_is_404(self):
        self.assertEqual(self.client.get('/help/no-such-topic/').status_code, 404)

    def test_index_leads_with_the_topics_for_the_page(self):
        key = 'admin:planner_console_changelist'
        expected = topics_for(key)
        self.assertTrue(expected, 'no topics for the console list')
        html = self.client.get(reverse('help:index'), {'for': key}).content.decode()
        self.assertIn('On this page', html)
        here = html.split('id="help-here"', 1)[1].split('</section>', 1)[0]
        for t in expected:
            self.assertIn(t.title.replace("'", '&#x27;'), here)

    def test_index_lists_every_topic(self):
        html = self.client.get(reverse('help:index')).content.decode()
        for t in TOPICS:
            self.assertIn('id="{}"'.format(t.slug), html)
