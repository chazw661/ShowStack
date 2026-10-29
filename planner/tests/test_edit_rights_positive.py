"""The other side of test_write_endpoint_guard: every endpoint #147 put an
edit-rights (or project) check on still works for the people it should --
the project's owner and an editor -- with a real request, not just one that
gets past the check.

A case succeeds when the response is the endpoint's success (2xx, or the
redirect it sends after saving), carries no error, and the request wrote to
the database; the read-only endpoints (a PDF, the next beltpack number) must
answer instead. Each request is rolled back, so the owner and the editor
both start from the same data.

Run with::

    python manage.py test planner.tests.test_edit_rights_positive \\
        --settings=audiopatch.test_settings
"""

import json
from io import BytesIO
import re
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from planner.admin_site import showstack_admin_site
from planner.models import (
    Amp, AmpDivider, AmpLocation, AmpModel, AudioChecklist, AudioChecklistTask,
    AudioChecklistTemplate, AudioChecklistTemplateTask, CommBeltPack, CommBeltPackChannel, CommChannel,
    Console, Location, MicAssignment, MicGroup, MicSession, MultitrackSession, Presenter,
    DiscoveredDevice, PresenterSlot, Project, ProjectMember, ShowDay,
    SystemProcessor,
)
from planner.tests.test_write_endpoint_guard import NOT_A_WRITE, WriteGuardBase


def png():
    buffer = BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buffer, 'PNG')
    return SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')


def csv_file(text, name='import.csv'):
    return SimpleUploadedFile(name, text.encode(), content_type='text/csv')


class Case:
    """One endpoint: ``build(test)`` returns (url, post kwargs)."""

    def __init__(self, route, build, *, reads=False, ok=(200, 302)):
        self.route, self.build, self.reads, self.ok = route, build, reads, ok


def js(url, payload):
    return url, {'data': json.dumps(payload), 'content_type': 'application/json'}


CASES = [
    # -- Amp rack ----------------------------------------------------------
    Case('audiopatch/api/amp/reorder/', lambda t: js('/audiopatch/api/amp/reorder/', {
        'amp_id': t.amps[1].pk, 'direction': 'up'})),
    Case('audiopatch/api/amp/divider/add/', lambda t: ('/audiopatch/api/amp/divider/add/', {
        'data': {'location_id': t.amp_location.pk, 'label': 'Top', 'after': 0}})),
    Case('audiopatch/api/amp/divider/sync/', lambda t: ('/audiopatch/api/amp/divider/sync/', {
        'data': {'location_id': t.amp_location.pk,
                 'dividers': json.dumps([{'label': 'New', 'after': 0}])}})),
    Case('audiopatch/api/amp/divider/<int:divider_id>/update/', lambda t: (
        f'/audiopatch/api/amp/divider/{t.divider.pk}/update/', {'data': {'label': 'Renamed'}})),
    Case('audiopatch/api/amp/divider/<int:divider_id>/delete/', lambda t: (
        f'/audiopatch/api/amp/divider/{t.divider.pk}/delete/', {})),
    Case('audiopatch/api/amp/divider/<int:divider_id>/reorder/', lambda t: (
        f'/audiopatch/api/amp/divider/{t.divider.pk}/reorder/', {'data': {'direction': 'down'}})),
    Case('audiopatch/api/amp/inline-create/', lambda t: ('/audiopatch/api/amp/inline-create/', {
        'data': {'location_id': t.amp_location.pk, 'amp_model_id': t.amp_model.pk,
                 'name': 'Amp new'}})),

    # -- Mic tracker -------------------------------------------------------
    Case('audiopatch/api/mic/add-shared-presenter/', lambda t: js(
        '/audiopatch/api/mic/add-shared-presenter/',
        {'assignment_id': t.mic.pk, 'presenter_name': 'Second Guest'})),
    Case('audiopatch/api/mic/remove-shared-presenter/', lambda t: js(
        '/audiopatch/api/mic/remove-shared-presenter/',
        {'assignment_id': t.shared_mic().pk, 'presenter_name': 'Shared Guest'})),
    Case('audiopatch/api/mic/dmic-and-rotate/', lambda t: js(
        '/audiopatch/api/mic/dmic-and-rotate/', {'assignment_id': t.mic.pk})),
    Case('audiopatch/api/mic/reset-rotation/', lambda t: js(
        '/audiopatch/api/mic/reset-rotation/', {'assignment_id': t.mic.pk})),
    Case('audiopatch/api/mic/update/', lambda t: js('/audiopatch/api/mic/update/', {
        'assignment_id': t.mic.pk, 'field': 'is_micd', 'value': True})),
    Case('audiopatch/api/mic/bulk-update/', lambda t: js('/audiopatch/api/mic/bulk-update/', {
        'session_id': t.session.pk, 'action': 'check_all_micd'})),
    Case('audiopatch/api/session/duplicate/', lambda t: js('/audiopatch/api/session/duplicate/', {
        'source_session_id': t.session.pk, 'target_session_name': 'Copy'})),
    Case('audiopatch/api/mic/delete-session/', lambda t: js(
        '/audiopatch/api/mic/delete-session/', {'session_id': t.session.pk})),
    Case('audiopatch/api/presenters/create/', lambda t: js(
        '/audiopatch/api/presenters/create/', {'name': 'New Presenter'})),
    Case('audiopatch/api/mic/slot/next/', lambda t: js(
        '/audiopatch/api/mic/slot/next/', {'assignment_id': t.slotted_mic().pk})),
    Case('audiopatch/api/mic/slot/prev/', lambda t: js(
        '/audiopatch/api/mic/slot/prev/', {'assignment_id': t.slotted_mic().pk})),
    Case('audiopatch/api/mic/slot/add/', lambda t: js(
        '/audiopatch/api/mic/slot/add/', {'assignment_id': t.mic.pk})),
    Case('audiopatch/api/mic/slot/remove/', lambda t: js('/audiopatch/api/mic/slot/remove/', {
        'assignment_id': t.slotted_mic().pk, 'slot_id': t.slots[1].pk})),
    Case('audiopatch/api/mic/slot/activate/', lambda t: js('/audiopatch/api/mic/slot/activate/', {
        'assignment_id': t.slotted_mic().pk, 'slot_id': t.slots[1].pk})),
    Case('audiopatch/api/mic/slot/upload-photo/', lambda t: (
        '/audiopatch/api/mic/slot/upload-photo/',
        {'data': {'slot_id': t.slotted_mic() and t.slots[0].pk, 'photo': png()}})),
    Case('audiopatch/api/mic/slot/upload-photo-from-url/', lambda t: t.photo_from_url()),
    Case('audiopatch/api/mic/slot/update/', lambda t: js('/audiopatch/api/mic/slot/update/', {
        'slot_id': t.slotted_mic() and t.slots[0].pk, 'field': 'notes', 'value': 'Lav left'})),
    Case('audiopatch/api/mic/slot/assign-group/', lambda t: js(
        '/audiopatch/api/mic/slot/assign-group/',
        {'slot_id': t.slotted_mic() and t.slots[0].pk, 'group_ids': [t.group.pk]})),
    Case('audiopatch/api/mic/slot/assign-a2-group/', lambda t: js(
        '/audiopatch/api/mic/slot/assign-a2-group/',
        {'slot_id': t.slotted_mic() and t.slots[0].pk, 'group_ids': [t.group.pk]})),
    Case('audiopatch/api/mic/slot/toggle-micd/', lambda t: js(
        '/audiopatch/api/mic/slot/toggle-micd/',
        {'slot_id': t.slotted_mic() and t.slots[0].pk, 'is_micd': True})),
    Case('audiopatch/api/day/create/', lambda t: js(
        '/audiopatch/api/day/create/', {'date': '2027-03-01', 'name': 'Load in'})),
    Case('audiopatch/api/session/create/', lambda t: js('/audiopatch/api/session/create/', {
        'day_id': t.day.pk, 'name': 'Keynote', 'num_mics': 4})),
    Case('audiopatch/api/mic-assignment/reorder/', lambda t: js(
        '/audiopatch/api/mic-assignment/reorder/', {
            'action': 'move', 'source_id': t.mics[2].pk, 'target_id': t.mics[0].pk,
            'position': 'above'})),
    Case('audiopatch/api/presenters/import/', lambda t: ('/audiopatch/api/presenters/import/', {
        'data': {'csv_file': csv_file('name,role\nAlex Guest,Speaker\n')}})),
    Case('audiopatch/api/mic-groups/<int:session_id>/', lambda t: js(
        f'/audiopatch/api/mic-groups/{t.session.pk}/',
        {'action': 'create', 'name': 'Panel', 'color': '#ff0000'})),
    Case('audiopatch/api/mic-groups/assign/', lambda t: js('/audiopatch/api/mic-groups/assign/', {
        'assignment_id': t.mic.pk, 'group_ids': [t.group.pk]})),

    # -- Audio checklist ---------------------------------------------------
    Case('audiopatch/audiochecklist/update-task/', lambda t: js(
        '/audiopatch/audiochecklist/update-task/',
        {'task_id': t.task().pk, 'field': 'task', 'value': 'Ring out'})),
    Case('audiopatch/audiochecklist/update-status/', lambda t: js(
        '/audiopatch/audiochecklist/update-status/',
        {'task_id': t.task().pk, 'day': 'day1', 'status': 'complete'})),
    Case('audiopatch/audiochecklist/add-task/', lambda t: js(
        '/audiopatch/audiochecklist/add-task/',
        {'checklist_name': t.task().checklist.name, 'task_type': 'setup', 'task': 'Line check'})),
    Case('audiopatch/audiochecklist/delete-task/', lambda t: js(
        '/audiopatch/audiochecklist/delete-task/', {'task_id': t.task().pk})),
    Case('audiopatch/audiochecklist/move-task/', lambda t: js(
        '/audiopatch/audiochecklist/move-task/', {'task_id': t.task(second=True).pk,
                                                 'direction': 'up'})),
    Case('audiopatch/audiochecklist/set-days/', lambda t: js(
        '/audiopatch/audiochecklist/set-days/',
        {'checklist_name': t.task().checklist.name, 'num_days': 3})),
    Case('audiopatch/audiochecklist/reset/', lambda t: js('/audiopatch/audiochecklist/reset/', {})),
    Case('audiopatch/audiochecklist/template/load/', lambda t: js(
        '/audiopatch/audiochecklist/template/load/', {'template_id': t.checklist_template().pk})),

    # -- COMM --------------------------------------------------------------
    Case('admin/planner/commbeltpack/assign-channel/', lambda t: js(
        '/admin/planner/commbeltpack/assign-channel/',
        {'beltpack_channel_id': t.bp_channel.pk, 'channel_id': t.comm_channel.pk})),
    Case('audiopatch/admin/planner/commposition/import/', lambda t: (
        '/audiopatch/admin/planner/commposition/import/', {'data': {'positions': 'FOH\nMON'}})),
    Case('audiopatch/admin/planner/commcrewname/import/', lambda t: (
        '/audiopatch/admin/planner/commcrewname/import/', {'data': {'names': 'Sam\nJo'}})),
    Case('audiopatch/comm-crew-names/import-csv/', lambda t: (
        '/audiopatch/comm-crew-names/import-csv/',
        {'data': {'csv_file': csv_file('name\nSam\nJo\n')}})),
    Case('admin/planner/commcrewname/import-csv/', lambda t: (
        '/admin/planner/commcrewname/import-csv/', {}), reads=True),
    Case('m/api/comm/toggle-checkout/<int:bp_id>/', lambda t: (
        f'/m/api/comm/toggle-checkout/{t.beltpack.pk}/', {})),
    Case('m/api/mic/toggle-micd/<int:assignment_id>/', lambda t: (
        f'/m/api/mic/toggle-micd/{t.mic.pk}/', {})),

    # -- Network monitor ---------------------------------------------------
    Case('audiopatch/network-monitor/devices/<int:device_id>/remove/', lambda t: (
        f'/audiopatch/network-monitor/devices/{t.device.pk}/remove/', {})),
    Case('audiopatch/network-monitor/devices/<int:device_id>/reassign/', lambda t: js(
        f'/audiopatch/network-monitor/devices/{t.device.pk}/reassign/', {'domain': 'dante'})),
    Case('audiopatch/network-monitor/request-scan/', lambda t: js(
        '/audiopatch/network-monitor/request-scan/', {})),
    Case('audiopatch/network-monitor/snmp-settings/', lambda t: js(
        '/audiopatch/network-monitor/snmp-settings/', {'community_string': 'showstack'})),
    Case('audiopatch/network-monitor/add-switch/', lambda t: js(
        '/audiopatch/network-monitor/add-switch/', {'ip': '10.9.9.9', 'label': 'Core'})),
    Case('audiopatch/network-monitor/show-mode/', lambda t: js(
        '/audiopatch/network-monitor/show-mode/', {'mode': 'setup'})),

    # -- Multitrack --------------------------------------------------------
    Case('audiopatch/multitrack/new/', lambda t: ('/audiopatch/multitrack/new/', {
        'data': t.multitrack_form('Recording')})),
    Case('audiopatch/multitrack/<int:session_id>/edit/', lambda t: (
        f'/audiopatch/multitrack/{t.multitrack().pk}/edit/', {
            'data': t.multitrack_form('Renamed')})),

    # -- Single endpoints --------------------------------------------------
    Case('audiopatch/pa-cables/import-csv/', lambda t: ('/audiopatch/pa-cables/import-csv/', {
        'data': {'csv_file': csv_file(
            'label,destination,cable,count,length\nSL,Hang,NL4,1,25\n')}})),
    Case('audiopatch/predictions/upload/', lambda t: t.prediction_upload()),
    Case('audiopatch/ip-addresses/save/', lambda t: js('/audiopatch/ip-addresses/save/', {
        'model_name': 'console', 'object_id': t.console.pk, 'field_name': 'primary_ip_address',
        'ip_value': '10.0.0.10'})),
    Case('audiopatch/power-distribution/generate/', lambda t: (
        '/audiopatch/power-distribution/generate/', {})),
    Case('admin/planner/systemprocessor/<int:pk>/configure/', lambda t: (
        f'/admin/planner/systemprocessor/{t.processor.pk}/configure/', {})),

    # -- Project-scoped reads ----------------------------------------------
    Case('audiopatch/location/<int:location_id>/pdf/', lambda t: (
        f'/audiopatch/location/{t.location.pk}/pdf/', {}), reads=True),
    Case('audiopatch/admin/planner/commbeltpack/get_next_bp_number/', lambda t: (
        '/audiopatch/admin/planner/commbeltpack/get_next_bp_number/?system_type=WIRELESS', {}),
        reads=True),
]


class EditRightsPositiveBase(WriteGuardBase):

    def setUp(self):
        super().setUp()
        self.editor = self.outsider
        ProjectMember.objects.create(project=self.project, user=self.editor, role='editor',
                                     invited_by=self.owner)
        f = self.factory
        self.amp_location = AmpLocation.objects.create(project=self.project, name='Rack')
        self.amp_model = f.get(AmpModel)
        amp = f.get(Amp)
        self.amps = []
        for n in range(2):
            amp.pk, amp.id = None, None
            amp.name, amp.location = f'Rack amp {n}', self.amp_location
            amp.save()
            self.amps.append(type(amp).objects.get(pk=amp.pk))
        self.divider = AmpDivider.objects.create(project=self.project, location=self.amp_location,
                                                 label='Mid', sort_order=1)
        self.day = ShowDay.objects.create(project=self.project, date='2027-02-01')
        self.session = MicSession.objects.create(day=self.day, name='Main', num_mics=4)
        self.mics = list(MicAssignment.objects.filter(session=self.session).order_by('pk'))
        self.mic = self.mics[0]
        self.group = MicGroup.objects.create(session=self.session, name='Panel', color='#00f')
        self.slots = []
        self.location = Location.objects.create(project=self.project, name='Stage')
        self.console = Console.objects.create(project=self.project, name='FOH desk')
        self.processor = SystemProcessor.objects.create(
            project=self.project, location=self.location, name='P1 rack', device_type='P1')
        self.beltpack = f.get(CommBeltPack)
        self.bp_channel = f.get(CommBeltPackChannel)
        self.comm_channel = f.get(CommChannel)
        self.device = f.get(DiscoveredDevice)

    # Built on demand, inside the case's rolled-back request.

    def slotted_mic(self):
        mic = self.mics[1]
        if not self.slots:
            for n, name in enumerate(('First', 'Second')):
                presenter = Presenter.objects.create(project=self.project, name=name)
                self.slots.append(PresenterSlot.objects.create(
                    assignment=mic, presenter=presenter, order=n, is_active=n == 0))
        return mic

    def shared_mic(self):
        guest = Presenter.objects.create(project=self.project, name='Shared Guest')
        self.mic.shared_presenters.add(guest)
        return self.mic

    def task(self, second=False):
        checklist = AudioChecklist.objects.filter(project=self.project).first() or \
            AudioChecklist.objects.create(project=self.project, name='Show Check List')
        tasks = list(checklist.tasks.filter(task_type='setup').order_by('sort_order'))
        while len(tasks) < 2:
            tasks.append(AudioChecklistTask.objects.create(
                checklist=checklist, task=f'Task {len(tasks)}', task_type='setup',
                sort_order=len(tasks) + 1))
        return tasks[1] if second else tasks[0]

    def checklist_template(self):
        template = AudioChecklistTemplate.objects.create(name='Mine', created_by=self.client_user)
        AudioChecklistTemplateTask.objects.create(template=template, task='Walk the rig')
        return template

    def multitrack(self):
        return self.factory.get(MultitrackSession)

    def multitrack_form(self, name):
        form = {'name': name, 'console': self.console.pk, 'notes': ''}
        for field in ('target_daw', 'feed_source', 'track_order_mode'):
            form[field] = MultitrackSession._meta.get_field(field).choices[0][0]
        form['recorder_capacity'] = 64
        return form

    def prediction_upload(self):
        # The upload, not Soundvision's PDF parser, is what's under test.
        patcher = mock.patch('planner.views.import_soundvision_prediction')
        patcher.start()
        self.addCleanup(patcher.stop)
        return '/audiopatch/predictions/upload/', {'data': {
            'show_day': self.day.pk,
            'pdf_file': SimpleUploadedFile('p.pdf', b'%PDF-1.4\n%%EOF\n',
                                           content_type='application/pdf')}}

    def photo_from_url(self):
        # No network in tests: the fetch answers with a real image.
        patcher = mock.patch('planner.utils.safe_fetch.fetch_public',
                             return_value=(png().read(), {}))
        patcher.start()
        self.addCleanup(patcher.stop)
        return js('/audiopatch/api/mic/slot/upload-photo-from-url/', {
            'slot_id': self.slotted_mic() and self.slots[0].pk,
            'url': 'https://example.com/p.png'})

    def run_case(self, case, user):
        """(status, body, writes) for ``case`` as ``user``, rolled back."""
        self.login(user, self.project)
        self.client_user = user
        with CaptureQueriesContext(connection) as queries, transaction.atomic():
            try:
                url, kwargs = case.build(self)
                start = len(queries.captured_queries)
                resp = self.client.get(url) if case.route.endswith('get_next_bp_number/') \
                    else self.client.post(url, **kwargs)
            except Exception as exc:  # noqa: BLE001 - an outcome like any other
                transaction.set_rollback(True)
                return f'raised {type(exc).__name__}: {exc}', b'', []
            finally:
                self.slots = []
            body = b''.join(resp.streaming_content) if resp.streaming else resp.content
            transaction.set_rollback(True)
        writes = [q['sql'] for q in queries.captured_queries[start:]
                  if re.match(r'\s*(INSERT|UPDATE|DELETE)\b', q['sql'], re.I)
                  and not NOT_A_WRITE.match(q['sql'])]
        return resp.status_code, body, writes

    @staticmethod
    def failure(case, status, body, writes):
        if status not in case.ok:
            return f'got {status}: {body[:200]!r}'
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if isinstance(data, dict) and (data.get('success') is False or data.get('ok') is False
                                       or 'error' in data):
            return f'refused in the body: {data}'
        if not case.reads and not writes:
            return 'answered but wrote nothing'
        return None


class EndpointPositiveTests(EditRightsPositiveBase):

    def test_owner_and_editor_succeed_on_every_checked_endpoint(self):
        failures = {}
        for case in CASES:
            for who, user in (('owner', self.owner), ('editor', self.editor)):
                problem = self.failure(case, *self.run_case(case, user))
                if problem:
                    failures[f'{case.route} as {who}'] = problem
        self.assertEqual({}, failures, '\n'.join(f'{k}: {v}' for k, v in failures.items()))

    def test_cases_name_real_routes(self):
        from planner.tests.test_write_endpoint_guard import patterns
        routes = {route for route, _, _ in patterns()}
        self.assertEqual(set(), {c.route for c in CASES} - routes)


class AdminActionPositiveTests(EditRightsPositiveBase):
    """The actions a viewer is no longer offered: an editor is offered every
    one the owner is, and running it as either does its work."""

    def offered(self, user):
        from django.test import RequestFactory
        request = RequestFactory().get('/admin/')
        request.user, request.current_project, request.session = user, self.project, {}
        return {(model._meta.label, name)
                for model, model_admin in showstack_admin_site._registry.items()
                for name in model_admin.get_actions(request)}

    def test_editor_is_offered_what_the_owner_is(self):
        # Deleting a project, its members or its invitations is the owner's
        # alone (ProjectAdmin, ProjectMemberAdmin, InvitationAdmin), not #147's.
        owner_only = {('planner.Project', 'delete_selected'),
                      ('planner.ProjectMember', 'delete_selected'),
                      ('planner.Invitation', 'delete_selected')}
        self.assertEqual(self.offered(self.owner) - owner_only,
                         self.offered(self.editor) - owner_only)

    def test_owner_and_editor_run_each_action_a_viewer_lost(self):
        failures = {}
        for label, name in WRITE_ACTIONS:
            model = next(m for m in showstack_admin_site._registry if m._meta.label == label)
            url = f'/admin/{model._meta.app_label}/{model._meta.model_name}/'
            for who, user in (('owner', self.owner), ('editor', self.editor)):
                if (label, name) not in self.offered(user):
                    failures[f'{name} as {who}'] = 'not offered'
                    continue
                self.login(user, self.project)
                status, _, writes = self.request('post', url, {
                    'action': name, '_selected_action': [self.factory.get(model).pk],
                    'index': 0, 'post': 'yes'})
                if status != 302 or not writes:
                    failures[f'{name} as {who}'] = f'{status}, {len(writes)} writes'
        self.assertEqual({}, failures)

    def test_duplicate_project_owner_and_editor_yes_viewer_no(self):
        data = {'action': 'duplicate_project_action', '_selected_action': [self.project.pk],
                'confirm_duplicate': '1', 'new_name': 'Copy of guard'}
        for who, user in (('owner', self.owner), ('editor', self.editor)):
            self.login(user, self.project)
            status, location, writes = self.request('post', '/admin/planner/project/', data)
            self.assertEqual(302, status, who)
            self.assertRegex(location, r'^/admin/planner/project/\d+/change/$', who)
            self.assertTrue(writes, who)
        self.login(self.viewer, self.project)
        status, _, writes = self.request('post', '/admin/planner/project/', data)
        self.assertEqual([], writes)
        self.assertNotIn(('planner.Project', 'duplicate_project_action'),
                         self.offered(self.viewer))
        self.assertFalse(Project.objects.filter(name='Copy of guard').exists())


# The admin actions the guard found writing for a viewer on main; a viewer is
# no longer offered them (BaseEquipmentAdmin.get_actions, CommPositionAdmin).
WRITE_ACTIONS = [
    ('planner.CommBeltPack', 'check_in_beltpacks'),
    ('planner.CommBeltPack', 'check_out_beltpacks'),
    ('planner.CommBeltPack', 'clear_all_beltpacks'),
    ('planner.CommBeltPack', 'duplicate_beltpacks'),
    ('planner.CommBeltPack', 'create_5_wireless_beltpacks'),
    ('planner.CommBeltPack', 'create_10_wireless_beltpacks'),
    ('planner.CommBeltPack', 'create_20_wireless_beltpacks'),
    ('planner.CommBeltPack', 'create_50_wireless_beltpacks'),
    ('planner.CommBeltPack', 'create_5_hardwired_beltpacks'),
    ('planner.CommBeltPack', 'create_10_hardwired_beltpacks'),
    ('planner.CommBeltPack', 'create_20_hardwired_beltpacks'),
    ('planner.CommBeltPack', 'create_50_hardwired_beltpacks'),
    ('planner.CommChannel', 'populate_default_channels'),
    ('planner.CommPosition', 'populate_common_positions'),
    ('planner.PACableSchedule', 'duplicate_cable_runs'),
]
