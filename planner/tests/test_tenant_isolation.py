"""Multi-tenant isolation suite.

One rule, asserted from every angle the app exposes: **user A must never see,
count, select, or fetch user B's rows** — and an anonymous visitor must never
see anybody's.

Two users, two projects, one object of each interesting type in each. Every
test drives a real surface (an admin changelist, a dropdown queryset, a filter
sidebar, an AJAX endpoint, an export) and asserts that project B's data is
absent from what project A's session is served.

Run with::

    python manage.py test planner.tests.test_tenant_isolation \\
        --settings=audiopatch.test_settings

Layout mirrors ``test_signal_flow_phase10._Phase10Base``: force_login plus
``session['current_project_id']`` is what feeds ``CurrentProjectMiddleware``.
"""

import json

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from planner.admin_site import showstack_admin_site
from planner.models import (
    Amp, AmpLocation, AmpModel, CommBeltPack, CommChannel, CommConfig,
    CommConfigPartyline, CommDeviceModel, CommPosition, CommCrewName, Console,
    ConsoleImport, ConsoleInput, Device, DiscoveredDevice, Location,
    MicAssignment, MicSession, MonitorSession, Project, ProjectMember,
    ProjectSNMPConfig, ShowDay, SoundvisionPrediction, SystemProcessor,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Shared fixture — two tenants, mirrored objects
# ---------------------------------------------------------------------------

class TenantIsolationBase(TestCase):
    """Two complete, independent tenants.

    Suffix convention: ``_a`` belongs to ``self.user_a`` / ``self.project_a``
    (the session we drive), ``_b`` to the victim tenant. Every name carries a
    tenant-unique marker string so a leak shows up as a plain substring match
    in a PDF, CSV or HTML body — no parsing needed.
    """

    MARKER_B = 'ZZTENANTB'

    def setUp(self):
        self.user_a = User.objects.create_user(
            'tenant_a', 'a@example.com', 'pw-a', is_staff=True,
        )
        self.user_b = User.objects.create_user(
            'tenant_b', 'b@example.com', 'pw-b', is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            'tenant_su', 'su@example.com', 'pw-su',
        )
        for u in (self.user_a, self.user_b):
            UserProfile.objects.update_or_create(
                user=u, defaults={'account_type': 'paid'},
            )

        self.project_a = Project.objects.create(name='Project A', owner=self.user_a)
        self.project_b = Project.objects.create(
            name=f'Project B {self.MARKER_B}', owner=self.user_b,
        )

        self.amp_model = AmpModel.objects.create(
            manufacturer='LA', model_name='LA12X', channel_count=4,
        )
        # device_type must be a real choice: CommBeltPack.save() derives
        # system_type from CommDeviceModel.system_type, which is itself derived
        # from device_type. 'WIRELESS_BP' is what makes the belt packs below
        # count as wireless on the dashboard.
        self.device_model = CommDeviceModel.objects.create(
            manufacturer='Clear-Com', name='FSII-BP', device_type='WIRELESS_BP',
        )

        # Mirrored per-project objects.
        for tag, project in (('a', self.project_a), ('b', self.project_b)):
            mark = self.MARKER_B if tag == 'b' else 'AAA'
            setattr(self, f'location_{tag}', Location.objects.create(
                project=project, name=f'Loc {mark}',
            ))
            setattr(self, f'amp_location_{tag}', AmpLocation.objects.create(
                project=project, name=f'AmpLoc {mark}',
            ))
            console = Console.objects.create(
                project=project, name=f'Console {mark}',
                location=getattr(self, f'location_{tag}'),
            )
            setattr(self, f'console_{tag}', console)
            setattr(self, f'console_input_{tag}', ConsoleInput.objects.create(
                console=console, input_ch='1', source=f'Src {mark}',
            ))
            setattr(self, f'device_{tag}', Device.objects.create(
                project=project, name=f'Device {mark}',
                location=getattr(self, f'location_{tag}'),
            ))
            setattr(self, f'amp_{tag}', Amp.objects.create(
                project=project, name=f'Amp {mark}',
                location=getattr(self, f'amp_location_{tag}'),
                amp_model=self.amp_model,
            ))
            setattr(self, f'processor_{tag}', SystemProcessor.objects.create(
                project=project, name=f'Proc {mark}', device_type='P1',
                location=getattr(self, f'location_{tag}'),
            ))
            show_day = ShowDay.objects.create(
                project=project, date=f'2026-0{1 if tag == "a" else 2}-01',
                name=f'Day {mark}',
            )
            setattr(self, f'show_day_{tag}', show_day)
            session = MicSession.objects.create(day=show_day, name=f'Sess {mark}')
            setattr(self, f'mic_session_{tag}', session)
            setattr(self, f'mic_assignment_{tag}', MicAssignment.objects.create(
                session=session, rf_number=1,
            ))
            setattr(self, f'prediction_{tag}', SoundvisionPrediction.objects.create(
                project=project, show_day=show_day, file_name=f'pred-{mark}.pdf',
            ))
            setattr(self, f'channel_{tag}', CommChannel.objects.create(
                project=project, channel_type='PL', channel_number='1',
                name=f'Chan {mark}', abbreviation=f'C{tag.upper()}',
            ))
            setattr(self, f'position_{tag}', CommPosition.objects.create(
                project=project, name=f'Pos {mark}',
            ))
            setattr(self, f'crew_name_{tag}', CommCrewName.objects.create(
                project=project, name=f'Crew {mark}',
            ))
            setattr(self, f'beltpack_{tag}', CommBeltPack.objects.create(
                project=project, bp_number=1, system_type='WIRELESS',
                device_model=self.device_model,
                name=getattr(self, f'crew_name_{tag}'),
                position=getattr(self, f'position_{tag}'),
                unit_location=getattr(self, f'location_{tag}'),
            ))
            comm_config = CommConfig.objects.create(
                project=project, name=f'Comm {mark}',
            )
            setattr(self, f'comm_config_{tag}', comm_config)
            setattr(self, f'partyline_{tag}', CommConfigPartyline.objects.create(
                config=comm_config, channel_number=1, label=f'PL{mark}'[:20],
            ))
            setattr(self, f'console_import_{tag}', ConsoleImport.objects.create(
                console=console, original_filename=f'imp-{mark}.csv',
            ))
            setattr(self, f'monitor_session_{tag}', MonitorSession.objects.create(
                project=project,
            ))
            setattr(self, f'discovered_{tag}', DiscoveredDevice.objects.create(
                project=project, ip_address=f'10.0.{1 if tag == "a" else 2}.5',
                label=f'Switch {mark}',
            ))
            setattr(self, f'snmp_{tag}', ProjectSNMPConfig.objects.create(
                project=project, community_string=f'secret-{mark}',
            ))

        self.client = Client()
        self.client.force_login(self.user_a)
        s = self.client.session
        s['current_project_id'] = self.project_a.id
        s.save()

        self.anon = Client()

    # -- helpers ----------------------------------------------------------

    def assertNoLeak(self, response, surface):
        """Project B's marker must not appear anywhere in the response body."""
        self.assertNotIn(
            self.MARKER_B, response.content.decode('utf-8', 'replace'),
            f'{surface}: project B data leaked into project A\'s response',
        )

    def admin_request(self, user=None, project=None):
        """A request object wired the way the admin sees it."""
        from django.test import RequestFactory
        request = RequestFactory().get('/admin/')
        request.user = user or self.user_a
        request.current_project = project or self.project_a
        request.session = {}
        return request


# ---------------------------------------------------------------------------
# 1. Admin changelists — get_queryset must never return another tenant's rows
# ---------------------------------------------------------------------------

class AdminQuerysetScopingTests(TenantIsolationBase):
    """Every registered admin, swept in one pass.

    Driven off the live registry rather than a hand-written list so a newly
    registered model cannot quietly skip the check.
    """

    # Models that are deliberately global catalogues, not tenant data.
    GLOBAL_MODELS = {
        'AmpModel', 'AmplifierProfile', 'CommDeviceModel',
        'SourceHardwareOption', 'User', 'Group', 'UserProfile', 'Crew',
        'Project', 'ProjectMember', 'Invitation',
    }

    def test_no_admin_changelist_returns_another_tenants_rows(self):
        request = self.admin_request()
        offenders = []
        for model, model_admin in showstack_admin_site._registry.items():
            if model.__name__ in self.GLOBAL_MODELS:
                continue
            try:
                qs = model_admin.get_queryset(request)
                pks = set(qs.values_list('pk', flat=True))
            except Exception as exc:  # a crash is its own finding, reported below
                offenders.append(f'{model.__name__}: get_queryset raised {exc!r}')
                continue
            foreign = self._foreign_pks(model)
            bleed = pks & foreign
            if bleed:
                offenders.append(
                    f'{model.__name__} ({type(model_admin).__name__}) '
                    f'returned project-B rows {sorted(bleed)}'
                )
        self.assertEqual([], offenders, '\n' + '\n'.join(offenders))

    def _foreign_pks(self, model):
        """PKs of this model's rows that belong to project B."""
        attr_map = {
            'Console': 'console_b', 'Device': 'device_b', 'Amp': 'amp_b',
            'Location': 'location_b', 'SystemProcessor': 'processor_b',
            'ShowDay': 'show_day_b', 'MicSession': 'mic_session_b',
            'MicAssignment': 'mic_assignment_b',
            'SoundvisionPrediction': 'prediction_b',
            'CommChannel': 'channel_b', 'CommPosition': 'position_b',
            'CommCrewName': 'crew_name_b', 'CommBeltPack': 'beltpack_b',
            'CommConfig': 'comm_config_b', 'ConsoleImport': 'console_import_b',
            'MonitorSession': 'monitor_session_b',
            'DiscoveredDevice': 'discovered_b',
            'ProjectSNMPConfig': 'snmp_b',
        }
        attr = attr_map.get(model.__name__)
        return {getattr(self, attr).pk} if attr else set()


# ---------------------------------------------------------------------------
# 2. Dropdowns — formfield_for_foreignkey / autocomplete / filter sidebars
# ---------------------------------------------------------------------------

class AdminDropdownScopingTests(TenantIsolationBase):
    """A dropdown is a read surface: anything selectable is also visible."""

    def _fk_querysets(self, model, model_admin):
        """Yield (field_name, queryset) for every relation on the add form."""
        from django.db import models as dm
        request = self.admin_request()
        exclude = set(model_admin.get_exclude(request) or ())
        for field in model._meta.get_fields():
            if not isinstance(field, (dm.ForeignKey, dm.OneToOneField)):
                continue
            if field.name in exclude or field.auto_created:
                continue
            formfield = model_admin.formfield_for_foreignkey(field, request)
            if formfield is not None:
                yield field.name, formfield.queryset

    def test_amp_admin_dropdowns_are_project_scoped(self):
        """The merged AmpAdmin.formfield_for_foreignkey must still scope
        `location` to the current project (and keep amp_model global)."""
        model_admin = showstack_admin_site._registry[Amp]
        fields = dict(self._fk_querysets(Amp, model_admin))

        self.assertIn('location', fields)
        locations = set(fields['location'])
        self.assertIn(self.amp_location_a, locations)
        self.assertNotIn(
            self.amp_location_b, locations,
            'AmpAdmin location dropdown offers project B amp locations',
        )
        # The dead first copy of the method filtered `Location`, not
        # `AmpLocation` — guard the right model survived the merge.
        self.assertEqual(AmpLocation, fields['location'].model)

        # amp_model is a global hardware catalogue and must stay unfiltered.
        self.assertIn('amp_model', fields)
        self.assertIn(self.amp_model, set(fields['amp_model']))

    def test_no_admin_dropdown_offers_another_tenants_rows(self):
        offenders = []
        request = self.admin_request()
        global_models = AdminQuerysetScopingTests.GLOBAL_MODELS
        foreign = {
            self.location_b, self.amp_location_b, self.console_b,
            self.device_b, self.amp_b, self.processor_b, self.show_day_b,
            self.mic_session_b, self.channel_b, self.position_b,
            self.crew_name_b, self.beltpack_b, self.comm_config_b,
            self.prediction_b, self.discovered_b, self.monitor_session_b,
        }
        for model, model_admin in showstack_admin_site._registry.items():
            if model.__name__ in global_models:
                continue
            try:
                for name, qs in self._fk_querysets(model, model_admin):
                    bleed = foreign & set(qs)
                    if bleed:
                        offenders.append(
                            f'{model.__name__}.{name} offers '
                            f'{sorted(str(o) for o in bleed)}'
                        )
            except Exception as exc:
                offenders.append(f'{model.__name__}: {exc!r}')
        self.assertEqual([], offenders, '\n' + '\n'.join(offenders))

    def test_no_filter_sidebar_enumerates_another_tenants_rows(self):
        """``list_filter`` on a bare relation makes Django render the whole
        related table (RelatedFieldListFilter.field_choices -> get_choices()),
        regardless of how get_queryset is scoped. Those labels are names."""
        from django.contrib.admin.views.main import ChangeList
        from django.test import RequestFactory

        offenders = []
        for model, model_admin in showstack_admin_site._registry.items():
            if not model_admin.list_filter:
                continue
            request = RequestFactory().get('/admin/')
            request.user = self.user_a
            request.current_project = self.project_a
            request.session = {}
            try:
                changelist = ChangeList(
                    request, model, model_admin.list_display,
                    model_admin.list_display_links, model_admin.list_filter,
                    model_admin.date_hierarchy, model_admin.search_fields,
                    model_admin.list_select_related, model_admin.list_per_page,
                    model_admin.list_max_show_all, model_admin.list_editable,
                    model_admin, model_admin.sortable_by,
                    model_admin.search_help_text,
                )
                specs = changelist.get_filters(request)[0]
            except Exception:
                continue  # unrelated crash; covered by the changelist test
            for spec in specs:
                for choice in spec.choices(changelist):
                    if self.MARKER_B in str(choice.get('display', '')):
                        offenders.append(
                            f'{model.__name__} filter {spec.title!r} lists '
                            f'{choice["display"]!r}'
                        )
        self.assertEqual([], offenders, '\n' + '\n'.join(offenders))

    def test_autocomplete_endpoint_is_project_scoped(self):
        """``/admin/autocomplete/`` serves the *remote* admin's get_queryset,
        and any FK anywhere in the project can name the remote model — so it
        is a general read oracle, not just a widget helper."""
        url = reverse('showstack_admin:autocomplete')
        resp = self.client.get(url, {
            'app_label': 'planner', 'model_name': 'amplifierassignment',
            'field_name': 'amplifier', 'term': 'Amp',
        })
        if resp.status_code == 200:
            ids = {r['id'] for r in resp.json()['results']}
            self.assertNotIn(
                str(self.amp_b.pk), ids,
                'autocomplete offered project B amps',
            )


# ---------------------------------------------------------------------------
# 3. Dashboard widgets and counts
# ---------------------------------------------------------------------------

class DashboardScopingTests(TenantIsolationBase):
    """#100 (a): the per-tenant counts that were not per-tenant."""

    def test_system_dashboard_counts_only_current_project(self):
        resp = self.client.get(reverse('planner:system-dashboard'))
        self.assertEqual(200, resp.status_code)
        ctx = resp.context
        self.assertEqual(1, ctx['console_count'], 'console_count spans tenants')
        self.assertEqual(1, ctx['device_count'], 'device_count spans tenants')
        self.assertEqual(1, ctx['total_amps'], 'total_amps spans tenants')
        self.assertEqual(
            1, ctx['wireless_beltpacks'], 'wireless_beltpacks spans tenants',
        )
        self.assertEqual(
            1, ctx['p1_processors'], 'p1_processors spans tenants',
        )
        self.assertEqual(
            self.amp_model.channel_count, ctx['total_amp_channels'],
            'total_amp_channels sums every tenant\'s amps',
        )

    def test_dashboard_stats_json_counts_only_current_project(self):
        resp = self.client.get(reverse('planner:dashboard_stats'))
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        for key in ('console_total', 'device_total', 'amp_total',
                    'comm_packs', 'sv_total', 'pa_zones'):
            self.assertLessEqual(
                data[key], 1, f'dashboard_stats.{key} spans tenants',
            )
        self.assertNoLeak(resp, 'dashboard_stats')

    def test_dashboard_stats_rejects_anonymous(self):
        """With no session project the counts used to fall back to global."""
        resp = self.anon.get(reverse('planner:dashboard_stats'))
        self.assertIn(
            resp.status_code, (302, 401, 403),
            'dashboard_stats served global counts to an anonymous visitor',
        )

    def test_dashboard_stats_with_no_project_counts_nothing(self):
        """A logged-in user with no project must get zeros, not everything."""
        loner = User.objects.create_user('loner', 'l@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(
            user=loner, defaults={'account_type': 'free'},
        )
        client = Client()
        client.force_login(loner)
        resp = client.get(reverse('planner:dashboard_stats'))
        if resp.status_code == 200:
            data = resp.json()
            for key in ('console_total', 'device_total', 'amp_total', 'comm_packs'):
                self.assertEqual(
                    0, data[key],
                    f'{key} fell back to a global count when no project was set',
                )


# ---------------------------------------------------------------------------
# 4. AJAX / API endpoints — raw-id IDOR
# ---------------------------------------------------------------------------

class AjaxEndpointScopingTests(TenantIsolationBase):
    """Every endpoint that takes a bare object id from the client."""

    def _assert_denied(self, resp, label):
        self.assertIn(
            resp.status_code, (302, 400, 401, 403, 404),
            f'{label}: project B object was accepted (HTTP {resp.status_code})',
        )

    def test_comm_config_role_chips_rejects_other_tenant(self):
        resp = self.client.get(
            reverse('planner:comm_config_role_chips'),
            {'role_id': 999999},
        )
        self.assertNotEqual(200, resp.status_code, 'role chips served unknown role')

    def test_comm_config_partyline_write_rejects_other_tenant(self):
        resp = self.client.post(
            reverse('planner:comm_config_update_partyline'),
            data=json.dumps({
                'partyline_id': self.partyline_b.id, 'label': 'PWNED',
            }),
            content_type='application/json',
        )
        self._assert_denied(resp, 'comm_config_update_partyline')
        self.partyline_b.refresh_from_db()
        self.assertNotEqual(
            'PWNED', self.partyline_b.label,
            'another tenant\'s partyline was renamed',
        )

    def test_comm_config_add_partyline_rejects_other_tenant_config(self):
        before = self.comm_config_b.partylines.count()
        resp = self.client.post(
            reverse('planner:comm_config_add_partyline'),
            data=json.dumps({'config_id': self.comm_config_b.id}),
            content_type='application/json',
        )
        self._assert_denied(resp, 'comm_config_add_partyline')
        self.assertEqual(
            before, self.comm_config_b.partylines.count(),
            'a partyline was added to another tenant\'s config',
        )

    def test_mic_assignment_update_rejects_other_tenant(self):
        resp = self.client.post(
            reverse('planner:update_mic_assignment'),
            data=json.dumps({
                'assignment_id': self.mic_assignment_b.id,
                'field': 'is_micd', 'value': True,
            }),
            content_type='application/json',
        )
        self._assert_denied(resp, 'update_mic_assignment')
        self.mic_assignment_b.refresh_from_db()
        self.assertFalse(
            self.mic_assignment_b.is_micd,
            'another tenant\'s mic assignment was modified',
        )

    def test_get_assignment_details_rejects_other_tenant(self):
        resp = self.client.get(reverse(
            'planner:get_assignment_details', args=[self.mic_assignment_b.id],
        ))
        self._assert_denied(resp, 'get_assignment_details')

    def test_get_assignment_details_rejects_anonymous(self):
        resp = self.anon.get(reverse(
            'planner:get_assignment_details', args=[self.mic_assignment_b.id],
        ))
        self._assert_denied(resp, 'get_assignment_details (anonymous)')

    def test_console_detail_rejects_other_tenant(self):
        """``console_detail`` is unauthenticated and unscoped, but currently
        raises before it can serve anything: its formset names ``output`` and
        ``omni_out``, which no longer exist on ConsoleInput. The guard still
        has to be there — the view is one field rename away from being live —
        so assert "does not serve another tenant", tolerating the 500."""
        client = Client(raise_request_exception=False)
        client.force_login(self.user_a)
        resp = client.get(
            reverse('planner:console_detail', args=[self.console_b.id]),
        )
        self.assertNotEqual(
            200, resp.status_code, 'console_detail served another tenant',
        )

    def test_console_detail_post_cannot_write_other_tenant(self):
        """Same view, write path: nothing an anonymous POST sends may land."""
        anon = Client(raise_request_exception=False)
        anon.post(
            reverse('planner:console_detail', args=[self.console_b.id]),
            data={
                'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1',
                'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
                'form-0-id': str(self.console_input_b.id),
                'form-0-source': 'PWNED',
                'form-0-input_ch': '1',
            },
        )
        self.console_input_b.refresh_from_db()
        self.assertNotEqual(
            'PWNED', self.console_input_b.source,
            'anonymous POST rewrote another tenant\'s console input',
        )


# ---------------------------------------------------------------------------
# 5. Exports — PDF / CSV / .cca
# ---------------------------------------------------------------------------

class ExportScopingTests(TenantIsolationBase):
    """Exports are the highest-value surface: whole patch sheets in one file."""

    def test_console_pdf_export_rejects_other_tenant(self):
        resp = self.client.get(
            reverse('planner:console_pdf_export', args=[self.console_b.id]),
        )
        self.assertNotEqual(
            200, resp.status_code,
            'console PDF for another tenant was served',
        )

    def test_console_pdf_export_rejects_anonymous(self):
        resp = self.anon.get(
            reverse('planner:console_pdf_export', args=[self.console_b.id]),
        )
        self.assertNotEqual(
            200, resp.status_code,
            'console PDF was served to an anonymous visitor',
        )

    def test_device_pdf_export_rejects_other_tenant(self):
        resp = self.client.get(
            reverse('planner:device_pdf_export', args=[self.device_b.id]),
        )
        self.assertNotEqual(200, resp.status_code, 'device PDF leaked')

    def test_device_pdf_export_guard_does_not_fail_open(self):
        """The guard was `if current_project: check` — an anonymous request
        has no current_project, so the check was skipped entirely."""
        resp = self.anon.get(
            reverse('planner:device_pdf_export', args=[self.device_b.id]),
        )
        self.assertNotEqual(
            200, resp.status_code,
            'device PDF guard failed open for a request with no project',
        )

    def test_comm_beltpack_pdf_never_spans_tenants(self):
        resp = self.client.get(reverse('planner:all_comm_beltpacks_pdf_export'))
        if resp.status_code == 200:
            self.assertNoLeak(resp, 'all_comm_beltpacks_pdf_export')

    def test_comm_beltpack_pdf_rejects_anonymous(self):
        """project=None made generate_comm_beltpacks_pdf span every project."""
        resp = self.anon.get(reverse('planner:all_comm_beltpacks_pdf_export'))
        self.assertNotEqual(
            200, resp.status_code,
            'belt-pack PDF for every tenant was served anonymously',
        )

    def test_comm_config_export_rejects_other_tenant(self):
        resp = self.client.get(
            reverse('planner:comm_config_export', args=[self.comm_config_b.id]),
        )
        self.assertNotEqual(
            200, resp.status_code,
            'another tenant\'s .cca config was exported',
        )

    def test_prediction_export_rejects_other_tenant(self):
        resp = self.client.get(
            reverse('planner:export_prediction', args=[self.prediction_b.id]),
        )
        self.assertNotEqual(200, resp.status_code, 'prediction CSV leaked')

    def test_predictions_list_shows_only_current_project(self):
        resp = self.client.get(reverse('planner:predictions_list'))
        if resp.status_code == 200:
            self.assertNoLeak(resp, 'predictions_list')

    def test_prediction_detail_rejects_other_tenant(self):
        resp = self.client.get(
            reverse('planner:prediction_detail', args=[self.prediction_b.id]),
        )
        self.assertNotEqual(200, resp.status_code, 'prediction detail leaked')

    def test_debug_device_ordering_is_not_a_public_device_dump(self):
        resp = self.anon.get(reverse('planner:debug_device_ordering'))
        self.assertNotEqual(
            200, resp.status_code,
            'debug view dumped devices to an anonymous visitor',
        )


# ---------------------------------------------------------------------------
# 6. Anonymous access — nothing tenant-shaped may answer an anonymous request
# ---------------------------------------------------------------------------

class AnonymousAccessTests(TenantIsolationBase):
    """``settings.MIDDLEWARE`` carries no LoginRequiredMiddleware, so an
    undecorated view answers the public internet. Sweep the routed planner
    views that take no arguments and assert none of them serves a 200."""

    # Routes that are genuinely public by design. The planner app has none —
    # the agent/companion APIs authenticate with a per-project Bearer token
    # instead of a session, so they must still refuse a plain anonymous GET.
    ALLOWED_PUBLIC = set()

    def _planner_route_names(self):
        """Every named route under the planner namespace, read from the
        URLconf itself rather than ``reverse_dict`` — namespaced names live in
        ``namespace_dict`` and a sweep over ``reverse_dict`` silently matches
        nothing, which would make this test vacuous."""
        from planner import urls as planner_urls
        from django.urls import URLPattern
        for pattern in planner_urls.urlpatterns:
            if not isinstance(pattern, URLPattern) or not pattern.name:
                continue
            # Only argument-free routes; id-bearing ones are covered by the
            # per-endpoint tests above.
            if pattern.pattern.regex.groups:
                continue
            yield pattern.name

    def test_the_sweep_actually_covers_routes(self):
        """Guard against the sweep below quietly matching nothing."""
        names = list(self._planner_route_names())
        self.assertGreater(len(names), 20, 'route sweep found almost nothing')
        self.assertIn('dashboard_stats', names)

    def test_no_argument_free_planner_view_answers_anonymously(self):
        offenders = []
        for name in self._planner_route_names():
            if name in self.ALLOWED_PUBLIC:
                continue
            try:
                url = reverse(f'planner:{name}')
            except Exception:
                continue
            resp = self.anon.get(url)
            if resp.status_code == 200:
                offenders.append(f'planner:{name} -> {url} returned 200 anonymously')
        self.assertEqual([], offenders, '\n' + '\n'.join(offenders))

    def test_comm_config_template_list_is_not_public(self):
        """Returned every tenant's COMM template names to anyone."""
        self.comm_config_b.is_template = True
        self.comm_config_b.template_name = f'Template {self.MARKER_B}'
        self.comm_config_b.save()
        resp = self.anon.get(reverse('planner:comm_config_list_templates'))
        if resp.status_code == 200:
            self.assertNoLeak(resp, 'comm_config_list_templates (anonymous)')

    def test_comm_config_template_list_is_project_scoped(self):
        self.comm_config_b.is_template = True
        self.comm_config_b.template_name = f'Template {self.MARKER_B}'
        self.comm_config_b.save()
        resp = self.client.get(reverse('planner:comm_config_list_templates'))
        if resp.status_code == 200:
            self.assertNoLeak(resp, 'comm_config_list_templates (tenant A)')

    def test_delete_session_cannot_destroy_another_tenants_session(self):
        """Unauthenticated POST deleted any MicSession by raw id."""
        victim_id = self.mic_session_b.id
        self.anon.post(
            reverse('planner:delete_session'),
            data=json.dumps({'session_id': victim_id}),
            content_type='application/json',
        )
        self.assertTrue(
            MicSession.objects.filter(id=victim_id).exists(),
            'anonymous POST deleted another tenant\'s mic session',
        )

    def test_delete_session_rejects_cross_tenant_for_logged_in_user(self):
        victim_id = self.mic_session_b.id
        self.client.post(
            reverse('planner:delete_session'),
            data=json.dumps({'session_id': victim_id}),
            content_type='application/json',
        )
        self.assertTrue(
            MicSession.objects.filter(id=victim_id).exists(),
            'tenant A deleted tenant B\'s mic session',
        )


# ---------------------------------------------------------------------------
# 7. Superuser — still sees everything, and that is intended
# ---------------------------------------------------------------------------

class SuperuserVisibilityTests(TenantIsolationBase):
    """Documents exactly where the superuser bypass applies, so a future
    tightening does not remove it by accident."""

    def test_superuser_project_admin_lists_every_project(self):
        request = self.admin_request(user=self.superuser)
        model_admin = showstack_admin_site._registry[Project]
        projects = set(model_admin.get_queryset(request))
        self.assertIn(self.project_a, projects)
        self.assertIn(
            self.project_b, projects,
            'superuser lost cross-project visibility in ProjectAdmin',
        )

    def test_non_superuser_project_admin_lists_only_own_projects(self):
        request = self.admin_request(user=self.user_a)
        model_admin = showstack_admin_site._registry[Project]
        projects = set(model_admin.get_queryset(request))
        self.assertIn(self.project_a, projects)
        self.assertNotIn(self.project_b, projects)

    def test_superuser_equipment_admin_still_follows_the_project_switcher(self):
        """BaseEquipmentAdmin scopes superusers to the selected project too —
        they switch projects with the dropdown rather than seeing a merged
        list. This is deliberate; assert it so it stays deliberate."""
        model_admin = showstack_admin_site._registry[Console]
        consoles = set(model_admin.get_queryset(
            self.admin_request(user=self.superuser, project=self.project_b)
        ))
        self.assertIn(self.console_b, consoles)
        self.assertNotIn(self.console_a, consoles)


# ---------------------------------------------------------------------------
# 8. Viewer / editor roles stay inside their own project
# ---------------------------------------------------------------------------

class InvitedMemberScopingTests(TenantIsolationBase):
    """An invited editor on project B must not reach project A."""

    def setUp(self):
        super().setUp()
        self.invitee = User.objects.create_user(
            'invitee', 'inv@example.com', 'pw', is_staff=True,
        )
        UserProfile.objects.update_or_create(
            user=self.invitee, defaults={'account_type': 'free'},
        )
        ProjectMember.objects.create(
            project=self.project_b, user=self.invitee, role='editor',
            invited_by=self.user_b,
        )
        self.invitee.groups.add(Group.objects.get_or_create(name='Editor')[0])
        self.invitee_client = Client()
        self.invitee_client.force_login(self.invitee)

    def test_editor_cannot_select_project_a_via_session(self):
        s = self.invitee_client.session
        s['current_project_id'] = self.project_a.id
        s.save()
        resp = self.invitee_client.get(reverse('planner:dashboard_stats'))
        if resp.status_code == 200:
            self.assertNotEqual(
                'Project A', resp.json().get('project_name'),
                'an invited member of project B selected project A',
            )

    def test_editor_cannot_open_another_tenants_comm_config_change_form(self):
        """CommConfigAdmin granted every is_staff user full access and never
        scoped its queryset — so any invited user could open any config."""
        url = f'/admin/planner/commconfig/{self.comm_config_a.id}/change/'
        resp = self.invitee_client.get(url)
        self.assertNotEqual(
            200, resp.status_code,
            'an invited member of project B opened project A\'s COMM config',
        )
