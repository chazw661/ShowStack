"""Edit rights on every write endpoint, enforced by enumeration.

Every URL pattern in the project -- planner, accounts, marketing, mobile,
help, and both admin sites -- is requested by:

* a **viewer** of the project the URL's objects are in (it is their current
  project), with POST, PUT, PATCH and DELETE and an empty body;
* a **non-member**, whose current project is their own, on every URL that
  names an object in the viewer's project.

Rules:

1. Neither ever causes a database write (sessions and last_login aside).
2. A viewer's POST to a write endpoint is refused before the view reads its
   input: 403 (or 404, 405). So is PUT, PATCH or DELETE where the view takes
   that method rather than POST.
3. A non-member's POST to a URL naming another project's object is
   not-found: 404, or the module's own not-found redirect (NOT_FOUND).
4. Admin actions: a viewer is offered only actions marked viewer_ok, and
   running every action as a viewer on a real object writes nothing.

"Write endpoint" is any view whose name is a write verb, whose own source
calls the ORM to write, or that takes only POST (or DELETE) -- less the
READ_ONLY list, plus the OPEN list of endpoints anyone may write to. A URL
the fixture can't fill fails as unprobed unless listed in UNPROBED, so a new
URL is never skipped silently.

Limits: the requests carry no body, so what a view does with a body naming
another project's object is left to the tenancy tests
(test_tenant_isolation and friends); this guards the role, and rejects
before parsing.

Set WRITE_GUARD_REPORT=<path> to dump every outcome as JSON instead.

Run with::

    python manage.py test planner.tests.test_write_endpoint_guard \\
        --settings=audiopatch.test_settings
"""

import inspect
import json
import os
import re

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import URLResolver, get_resolver

from planner.admin import project_of
from planner.admin_site import showstack_admin_site
from planner.models import Project, ProjectMember, UserProfile
from planner.tests.write_guard_fixture import Factory

METHODS = ('post', 'put', 'patch', 'delete')
REFUSED = {401, 403, 404, 405}

# Writes a request may make without changing anything in a project: the
# session (current project), last_login, and django-admin-interface's theme
# row, created on the first admin page anyone loads.
NOT_A_WRITE = re.compile(r'^\s*(INSERT INTO|UPDATE|DELETE FROM)\s+"?(django_session|auth_user|'
                         r'admin_interface_theme)"?', re.I)

WRITE_VERB = re.compile(
    r'(^|_)(add|create|new|update|delete|remove|save|set|toggle|import|upload|reorder|sync|'
    r'assign|rename|duplicate|move|reset|load|activate|advance|previous|dmic|clear|populate|'
    r'invite|accept|leave|change|configure|generate|regenerate|bulk|edit|checkout|micd|'
    r'reassign|scan|autosave|register|waitlist|contact)(_|$)')
ORM_WRITE = re.compile(r'\.(save|delete|create|bulk_create|bulk_update|get_or_create|'
                       r'update_or_create)\(|\.update\(\w+=')
POST_ONLY = re.compile(r'@require_POST|@require_http_methods\(\[\s*["\'](POST|DELETE)["\']\s*\]\)')

# Endpoints a viewer (or anyone) may legitimately write to, by route.
OPEN = {
    # Signing in and out, registering, resetting a password: no project.
    'login/': 'sign-in',
    'logout/': 'sign-out',
    'register/': 'registration',
    'password-reset/': 'password reset request',
    'm/login/': 'mobile sign-in',
    'm/logout/': 'mobile sign-out',
    'admin/login/': 'admin sign-in',
    'admin/logout/': 'admin sign-out',
    'admin/password_change/': "the user's own password",
    'audiopatch/admin/login/': 'default admin sign-in',
    'audiopatch/admin/logout/': 'default admin sign-out',
    'audiopatch/admin/password_change/': "the user's own password",
    # Public marketing forms.
    '': "public home page's waitlist form",
    'contact/': 'public contact form',
    'api/waitlist/': 'public waitlist sign-up',
    # The user's own membership and session, not the project.
    'leave-project/<int:project_id>/': 'a member leaving a project removes their own membership',
    'set-project/<int:project_id>/': 'switches the current project in the session',
    'audiopatch/switch-project/<int:project_id>/': 'switches the current project in the session',
    # A new project of the user's own (their account type decides).
    'admin/planner/project/add/': "creates the user's own project",
    # The viewer's own things, outside the project.
    'audiopatch/audiochecklist/template/save/': "saves to the user's own template library",
    'audiopatch/audiochecklist/template/delete/': "deletes from the user's own template library",
    # Shared UI state, not project data. Pending a decision: it is stored on
    # the day, so a viewer collapsing a day collapses it for everyone.
    # Crews belong to a user, not a project: a project role has no bearing.
    'crew/new/': "creates the user's own crew",
    'crew/<int:crew_id>/': "the user's own crew",
    'crew/<int:crew_id>/delete/': "the user's own crew",
    'crew/<int:crew_id>/members/add/': "the user's own crew",
    'crew/<int:crew_id>/members/<int:member_id>/remove/': "the user's own crew",
}

# Views the write heuristic flags that write nothing.
READ_ONLY = {
    'admin/planner/ampmodel/<int:pk>/use-existing/': 'popup returning a catalogue row',
    'admin/planner/systemprocessor/<int:pk>/configure/':
        'opens an existing configuration; creating one needs edit rights '
        '(ConfigureViewTests)',
    'audiopatch/admin/planner/commbeltpack/get_next_bp_number/': 'next number, read-only',
    'audiopatch/comm-config/': 'page',
    'audiopatch/comm-config/<int:config_id>/export/': '.cca export',
    'audiopatch/comm-config/<int:config_id>/': 'page',
    'audiopatch/mic-tracker/': 'page',
    'audiopatch/network-monitor/api/health-check/': 'compares devices, read-only',
    'audiopatch/audiochecklist/': 'page (creates the default checklists on first view)',
    'crew/': 'page',
    'audiopatch/multitrack/<int:session_id>/capacity/': 'read-only check',
    'projects/<int:project_id>/requests/': 'page; approving needs ownership',
}

# Account pages that refuse a non-owner with a message and a redirect, as
# the accounts module does everywhere, rather than a 403. Rule 1 still holds:
# nothing is written.
REFUSED_BY_REDIRECT = {
    'projects/<int:project_id>/invite/': 'owner only',
    'delete-project/<int:project_id>/': 'owner only',
    'projects/<int:project_id>/members/<int:member_id>/role/': 'owner only',
    'projects/<int:project_id>/invite/add-crew/<int:crew_id>/': 'owner only',
}

# URLs the fixture cannot fill, and why that is fine.
UNPROBED = {
    'admin/^(?P<app_label>planner|auth)/$': 'admin app index, read-only',
    'admin/(?P<url>.*)$': "admin catch-all (404s)",
    'audiopatch/admin/^(?P<app_label>admin_interface|auth|marketing)/$': 'admin app index, read-only',
    'audiopatch/admin/(?P<url>.*)$': 'admin catch-all (404s)',
    'admin/r/<path:content_type_id>/<path:object_id>/': "view-on-site redirect, read-only",
    'audiopatch/admin/r/<path:content_type_id>/<path:object_id>/': 'view-on-site redirect, read-only',
    'admin/auth/user/<id>/password/': 'superuser-only (auth admin)',
    'audiopatch/admin/auth/user/<id>/password/': 'superuser-only (auth admin)',
    'reset/<uidb64>/<token>/': 'password reset link, token-authenticated',
    'invitations/accept/<uuid:token>/': 'invitation link, token-authenticated',
    'projects/request/<uuid:invite_token>/': 'access request link, token-authenticated',
    'help/<slug:slug>/': 'help page, read-only',
}

# A non-member's not-found, where a module redirects instead of 404ing:
# route prefix -> the page it sends them to.
NOT_FOUND = {
    'admin/': '/admin/',
    'audiopatch/admin/': '/admin/',
    'projects/': ('/dashboard/', '/projects/', '/audiopatch/mic-tracker/'),
    'set-project/': '/dashboard/',
    'delete-project/': '/dashboard/',
    'leave-project/': '/dashboard/',
    'crew/': '/crew/',
    'm/': '/m/',
    'audiopatch/multitrack/': '/audiopatch/multitrack/',
    'audiopatch/signal-flow/': '/audiopatch/signal-flow/',
    'audiopatch/comm-config/': '/audiopatch/comm-config/',
}

# Django's admin refuses a POST to a model the user may not change before it
# looks the object up, so its 403 says nothing about the object.
ADMIN_PREFIXES = ('admin/', 'audiopatch/admin/')

# URL kwarg -> the model it names. Where one name means several models,
# the first (route fragment, model) whose fragment is in the route wins.
KWARG_MODELS = {
    'project_id': [('', 'Project')],
    'session_id': [('multitrack', 'MultitrackSession'), ('', 'MicSession')],
    'pk': [('console-patch', 'ConsoleInput'), ('predictions', 'SoundvisionPrediction'),
           ('console/', 'Console'), ('ampmodel', 'AmpModel'),
           ('systemprocessor', 'SystemProcessor')],
    'assignment_id': [('power', 'AmplifierAssignment'), ('', 'MicAssignment')],
    'plan_id': [('', 'PowerDistributionPlan')],
    'diagram_id': [('', 'SignalFlowDiagram')],
    'crew_id': [('', 'Crew')],
    'config_id': [('', 'CommConfig')],
    'device_id': [('network-monitor', 'DiscoveredDevice'), ('', 'Device')],
    'divider_id': [('', 'AmpDivider')],
    'member_id': [('crew', 'CrewMember'), ('', 'ProjectMember')],
    'console_id': [('', 'Console')],
    'p1_processor_id': [('', 'P1Processor')],
    'galaxy_processor_id': [('', 'GalaxyProcessor')],
    'template_id': [('', 'MultitrackTemplate')],
    'slot_id': [('', 'PresenterSlot')],
    'channel_id': [('amp-channel', 'AmpChannel'), ('', 'CommBeltPackChannel')],
    'prediction_id': [('', 'SoundvisionPrediction')],
    'presenter_id': [('', 'Presenter')],
    'amp_id': [('', 'Amp')],
    'mic_id': [('', 'MicAssignment')],
    'array_id': [('', 'SpeakerArray')],
    'location_id': [('', 'Location')],
    'day_id': [('', 'ShowDay')],
    'bp_id': [('', 'CommBeltPack')],
}

# Admin actions a viewer is offered besides viewer_ok ones, and why.
VIEWER_ACTIONS = {
    ('planner.ShowTemplate', 'delete_selected'): "the user's own templates",
    ('planner.Console', 'save_as_template'): "writes to the user's own template library",
}


def patterns():
    """(route, callback, admin model or None) for every URL pattern."""
    def walk(items, prefix, admin_model):
        for item in items:
            if isinstance(item, URLResolver):
                yield from walk(item.url_patterns, prefix + str(item.pattern),
                                _admin_model(item) or admin_model)
            else:
                yield prefix + str(item.pattern), item.callback, admin_model
    yield from walk(get_resolver().url_patterns, '', None)


def _admin_model(resolver):
    """The model of a ModelAdmin's URL include (Django tags its views)."""
    for p in resolver.url_patterns:
        model_admin = getattr(getattr(p, 'callback', None), 'model_admin', None)
        if model_admin is not None:
            return model_admin.model
    return None


def unwrap(callback):
    view = getattr(callback, 'view_class', None) or callback
    while hasattr(view, '__wrapped__'):
        view = view.__wrapped__
    return view


def is_write(route, callback):
    """Whether the view behind ``route`` can change data (see module doc)."""
    if route in OPEN or route in READ_ONLY:
        return False
    view = unwrap(callback)
    name = getattr(view, '__name__', '')
    if name in ('changelist_view', 'history_view', 'index', 'autocomplete_view',
                'app_index', 'catch_all_view', 'view_on_site', 'i18n_javascript'):
        return False  # the admin's own: actions are tested on their own
    if name in ('add_view', 'change_view', 'delete_view'):
        return True
    try:
        source = inspect.getsource(view)
    except (OSError, TypeError):
        source = ''
    return bool(WRITE_VERB.search(name) or ORM_WRITE.search(source)
                or POST_ONLY.search(source.split('\ndef ')[0]))


class WriteGuardBase(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('guard_owner', password='pw', is_staff=True)
        self.viewer = User.objects.create_user('guard_viewer', password='pw', is_staff=True)
        self.outsider = User.objects.create_user('guard_outsider', password='pw', is_staff=True)
        for user in (self.owner, self.viewer, self.outsider):
            UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='Guard project', owner=self.owner)
        self.theirs = Project.objects.create(name='Outsider project', owner=self.outsider)
        ProjectMember.objects.create(project=self.project, user=self.viewer, role='viewer',
                                     invited_by=self.owner)
        self.factory = Factory(self.project, self.owner)
        # Built now, outside the rolled-back requests.
        for model in list(apps.get_app_config('planner').get_models()) + \
                list(showstack_admin_site._registry):
            self.factory.get(model)

    def login(self, user, project):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = project.pk
        session.save()

    def request(self, method, url, data=None):
        """(status, Location, writes) -- a view that raises is an outcome too.
        Rolled back, so no request changes what the next one sees (a viewer
        posting to leave-project would otherwise stop being a viewer)."""
        with CaptureQueriesContext(connection) as queries, transaction.atomic():
            try:
                resp = getattr(self.client, method)(url, data or {})
                status, location = resp.status_code, resp.get('Location', '')
            except Exception as exc:  # noqa: BLE001
                status, location = f'raised {type(exc).__name__}', ''
            transaction.set_rollback(True)
        writes = [q['sql'][:160] for q in queries.captured_queries
                  if re.match(r'\s*(INSERT|UPDATE|DELETE)\b', q['sql'], re.I)
                  and not NOT_A_WRITE.match(q['sql'])]
        return status, location, writes

    def fill(self, route, admin_model):
        """(url, objects named) with each kwarg an object in the fixture's
        project, or (None, reason)."""
        named = []
        url = route
        for match in re.finditer(r'<(?:(\w+):)?(\w+)>', route):
            kwarg = match.group(2)
            if kwarg == 'kind':
                url = url.replace(match.group(0), 'input', 1)
                continue
            if kwarg == 'object_id' and admin_model is not None:
                obj = self.factory.get(admin_model)
            else:
                obj = next((self.factory.get(apps.get_model('planner', label))
                            for fragment, label in KWARG_MODELS.get(kwarg, ())
                            if fragment in route), None)
            if obj is None:
                return None, f'no object for <{kwarg}>'
            named.append(obj)
            url = url.replace(match.group(0), str(obj.pk), 1)
        if re.search(r'[\^$()\\]', url):
            return None, 'regex route'
        return '/' + url, named


class WriteEndpointGuardTests(WriteGuardBase):

    def probe(self):
        results = []
        for route, callback, admin_model in patterns():
            entry = {'route': route, 'view': f'{unwrap(callback).__module__}.'
                                             f'{getattr(unwrap(callback), "__qualname__", "")}',
                     'write': is_write(route, callback)}
            url, named = self.fill(route, admin_model)
            if url is None:
                entry['unprobed'] = named
                results.append(entry)
                continue
            entry['url'] = url
            entry['in_project'] = False
            self.login(self.viewer, self.project)
            for method in METHODS:
                entry[f'viewer:{method}'] = self.request(method, url)
            # Only an object in the project has a non-member to keep out:
            # catalogue rows, users and personal templates are in none.
            entry['in_project'] = any(project_of(obj) == self.project for obj in named)
            if entry['in_project']:
                self.login(self.outsider, self.theirs)
                for method in METHODS:
                    entry[f'outsider:{method}'] = self.request(method, url)
            results.append(entry)
        return results

    def problems(self, entry):
        route = entry['route']
        if 'unprobed' in entry:
            return [] if route in UNPROBED else [f"unprobed: {entry['unprobed']}"]
        found = []
        for who in ('viewer', 'outsider'):
            for method in METHODS:
                outcome = entry.get(f'{who}:{method}')
                if outcome and outcome[2]:
                    found.append(f'{who} {method.upper()} wrote: {outcome[2][0]}')
        post, location, _ = entry['viewer:post']
        if entry['write'] and route not in REFUSED_BY_REDIRECT:
            # Naming something outside the project (another user's template)
            # is the module's not-found, as for a non-member.
            if post == 302 and not entry['in_project'] and self.not_found(route, location):
                pass
            elif post not in REFUSED:
                found.append(f'viewer POST got {post}, not 403')
            elif post == 405:
                for method in METHODS[1:]:
                    status = entry[f'viewer:{method}'][0]
                    if status not in REFUSED:
                        found.append(f'viewer {method.upper()} got {status}, not 403')
        outsider = entry.get('outsider:post')
        if outsider and route not in OPEN:
            status, location, _ = outsider
            if status not in (404, 405) and not (status == 302 and self.not_found(route, location)) \
                    and not (status == 403 and route.startswith(ADMIN_PREFIXES)):
                found.append(f'non-member POST got {status} {location}, not not-found')
        return found

    @staticmethod
    def not_found(route, location):
        """Whether ``location`` is the not-found page of ``route``'s module."""
        targets = next((t for prefix, t in NOT_FOUND.items() if route.startswith(prefix)), ())
        return bool(location) and location.startswith(
            (targets,) if isinstance(targets, str) else targets or ('\0',))

    def test_every_endpoint(self):
        results = self.probe()
        report = os.environ.get('WRITE_GUARD_REPORT')
        if report:
            with open(report, 'w') as f:
                json.dump({'results': results, 'factory_failed': {
                    m.__name__: e for m, e in self.factory.failed.items()}}, f, indent=1, default=str)
        self.assertEqual({}, {m.__name__: e for m, e in self.factory.failed.items()})
        failures = {}
        for entry in results:
            found = self.problems(entry)
            if found:
                failures.setdefault(entry['route'], []).extend(found)
        self.assertEqual({}, failures, '\n'.join(f'{r}: {f}' for r, f in failures.items()))

    def test_allowlists_name_real_routes(self):
        routes = {route for route, _, _ in patterns()}
        for listed in (OPEN, READ_ONLY, UNPROBED):
            self.assertEqual(set(), set(listed) - routes)


class AdminActionGuardTests(WriteGuardBase):

    def viewer_request(self):
        request = RequestFactory().get('/admin/')
        request.user, request.current_project, request.session = self.viewer, self.project, {}
        return request

    def test_viewer_is_offered_only_viewer_ok_actions(self):
        offered = {}
        for model, model_admin in showstack_admin_site._registry.items():
            for name, (func, _, _) in model_admin.get_actions(self.viewer_request()).items():
                key = (model._meta.label, name)
                if not getattr(func, 'viewer_ok', False) and key not in VIEWER_ACTIONS:
                    offered[key] = func
        self.assertEqual({}, offered)

    def test_no_action_writes_for_a_viewer(self):
        owner_request = RequestFactory().get('/admin/')
        owner_request.user, owner_request.current_project, owner_request.session = \
            self.owner, self.project, {}
        self.login(self.viewer, self.project)
        wrote = {}
        for model, model_admin in showstack_admin_site._registry.items():
            obj = self.factory.get(model)
            if obj is None:
                continue
            url = f'/admin/{model._meta.app_label}/{model._meta.model_name}/'
            for name in model_admin.get_actions(owner_request):
                if (model._meta.label, name) in VIEWER_ACTIONS:
                    continue
                status, _, writes = self.request('post', url, {
                    'action': name, '_selected_action': [obj.pk], 'index': 0, 'post': 'yes'})
                if writes:
                    wrote[(model._meta.label, name)] = writes[0]
        self.assertEqual({}, wrote)


class ConfigureViewTests(WriteGuardBase):
    """The processor configure link: a viewer opens an existing configuration;
    one that doesn't exist yet would be created, which needs edit rights."""

    def processor(self):
        from planner.models import Location, SystemProcessor
        location = Location.objects.create(project=self.project, name='FOH')
        return SystemProcessor.objects.create(project=self.project, location=location,
                                              name='P1 rack', device_type='P1')

    def test_viewer_cannot_create_but_can_open(self):
        from planner.models import P1Processor
        processor = self.processor()
        url = f'/admin/planner/systemprocessor/{processor.pk}/configure/'
        self.login(self.viewer, self.project)
        self.assertEqual(403, self.client.get(url).status_code)
        self.assertFalse(P1Processor.objects.filter(system_processor=processor).exists())
        self.login(self.owner, self.project)
        self.assertEqual(302, self.client.get(url).status_code)
        self.login(self.viewer, self.project)
        self.assertEqual(302, self.client.get(url).status_code)

    def test_other_project_is_404(self):
        processor = self.processor()
        self.login(self.outsider, self.theirs)
        self.assertEqual(404, self.client.get(
            f'/admin/planner/systemprocessor/{processor.pk}/configure/').status_code)
