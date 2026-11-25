# planner/admin_ordering.py
"""The admin sidebar: which rows, in which sections, for whom.

Django builds one sidebar block per app. ShowStack shows sections that follow
the job instead (Project, System, Comms, ...), so `ordered_get_app_list`
takes whatever the admin site says this user may see and deals it into
`SECTIONS`, in the order written there.

The sidebar only ever narrows: a row appears when it is in a section AND the
model admin already lets this user see it. Hiding a row here changes no
permission -- the page still opens at its URL, and pickers that read the
model still work.

Adding an admin-registered model? Put its name in a section or in
`NOT_IN_SIDEBAR`. `planner.tests.test_sidebar` fails until it is in one.
"""
from django.urls import reverse

from planner.admin_site import showstack_admin_site
from planner.tenancy import can_access_project, can_edit_project

# Store the original get_app_list from showstack_admin_site
original_get_app_list = showstack_admin_site.get_app_list

# (key, heading, rows in order). Names are lower-cased model class names,
# plus the pages in `_pages`. The key becomes the block's `app-<key>` class.
SECTIONS = [
    ('project', 'Project', [
        'project', 'location', 'projectmember', 'invitation', 'crew',
    ]),
    ('system', 'System', [
        'console', 'device', 'ipaddressmanager', 'systemprocessor',
        'soundvisionprediction', 'speakerarray', 'speakercabinet',
        'amp', 'pacableschedule',
        'powerdistributionplan', 'amplifierassignment',
        'wiringdiagram',
    ]),
    ('comms', 'Comms', ['commbeltpack', 'commconfig']),
    ('mics', 'Mics', ['showflowimport', 'showday']),
    ('show', 'Show', ['audiochecklist', 'multitracksession']),
    ('libraries', 'Libraries', [
        'sourcehardwareoption', 'cabinetmodel', 'amplifierprofile',
        'commdevicemodel',
    ]),
    ('admin', 'Admin', ['user', 'group', 'userprofile']),
]

# Rows that fold under a parent row (the arrow in the sidebar). Each child
# row carries its parent's name as `sidebar_parent`; templates/admin/
# app_list.html writes it out and the script in base_site.html reads it. So
# the grouping follows the model, never the wording of a link.
GROUPS = {
    'soundvisionprediction': ['speakerarray', 'speakercabinet'],
    'powerdistributionplan': ['amplifierassignment'],
}
PARENT_OF = {child: parent for parent, children in GROUPS.items() for child in children}

# Sidebar rows for superusers only. The catalogues are shared by every
# account and only a superuser can edit them; everyone else meets their
# figures where they are used (the cabinet pickers, the power plan's per-amp
# current). View permission is untouched: the lists still open at their URLs.
SUPERUSER_ONLY = {
    'cabinetmodel', 'amplifierprofile', 'commdevicemodel',
    'user', 'group', 'userprofile',
}

# Child rows a viewer of the current project has no use for.
HIDDEN_FROM_VIEWERS = {'speakerarray', 'speakercabinet', 'amplifierassignment'}

# Registered in the admin, deliberately not in the sidebar: reached from a
# parent page or a button, or retired.
NOT_IN_SIDEBAR = {
    # Reached from their parent's page.
    'ampmodel', 'pazone', 'p1processor', 'galaxyprocessor',
    'commposition', 'commcrewname', 'commchannel',
    'micsession', 'micassignment', 'micgroup', 'presenter', 'micshowinfo',
    # "Manage templates" on the Consoles list and the Load template page.
    'showtemplate',
    # Managed inside the Multitrack module (issue #17).
    'multitracktemplate',
    # Audit rows written by the console CSV import (issue #6).
    'consoleimport',
    # Network Health Monitor, scrapped: the URLs still open.
    'monitorsession', 'discovereddevice', 'pollresult', 'deviceevent',
    'projectsnmpconfig', 'switchportsnapshot',
}


def _pages():
    """Sidebar rows that are pages of the current project, not models."""
    return [
        {'name': 'IP Address Manager', 'object_name': 'IPAddressManager',
         'admin_url': reverse('planner:ip_address_report'), 'add_url': None,
         'view_only': True, 'perms': {'view': True}},
        {'name': 'Wiring Diagram', 'object_name': 'WiringDiagram',
         'admin_url': reverse('planner:wiring_diagram'), 'add_url': None,
         'view_only': True, 'perms': {'view': True}},
    ]


def ordered_get_app_list(request, app_label=None):
    app_list = original_get_app_list(request, app_label)

    # A viewer on the CURRENT project: they can open it but not change it.
    # The role is per project; being a viewer somewhere else, or an editor
    # somewhere else, says nothing about the project in hand.
    project = getattr(request, 'current_project', None)
    is_viewer = (
        can_access_project(request.user, project)
        and not can_edit_project(request.user, project)
    )
    is_superuser = request.user.is_superuser

    rows = {}
    for app in app_list:
        for model in app['models']:
            rows[model['object_name'].lower()] = model
    if any(app['app_label'] == 'planner' for app in app_list):
        # The pages are for every role that can open the project.
        for page in _pages():
            rows[page['object_name'].lower()] = page

    plan = rows.get('powerdistributionplan')
    if plan:
        # The sidebar opens the project's power plan page (the one with
        # Regenerate), not the admin list; superusers reach the list at its
        # URL.
        plan['admin_url'] = reverse('planner:power_distribution_calculator')
        plan['add_url'] = None
    mic_planner = rows.get('showflowimport')
    if mic_planner:
        # "Mic Planner" opens the import + review page; the admin list itself
        # only redirects there. Named here, not by verbose_name_plural, so
        # the model keeps its name.
        mic_planner['name'] = 'Mic Planner'
        mic_planner['admin_url'] = reverse('planner:mic_plan')
        mic_planner['add_url'] = None

    def shown(name):
        return (
            name in rows
            and (is_superuser or name not in SUPERUSER_ONLY)
            and not (is_viewer and name in HIDDEN_FROM_VIEWERS)
        )

    sections = []
    for key, heading, names in SECTIONS:
        models = []
        for name in names:
            if not shown(name):
                continue
            row = rows[name]
            parent = PARENT_OF.get(name)
            # A child folds only under a parent that is itself listed.
            row['sidebar_parent'] = parent if parent and shown(parent) else ''
            models.append(row)
        if models:
            sections.append({
                'name': heading,
                'app_label': key,
                # A section has no page of its own; its heading is plain
                # text (templates/admin/app_list.html).
                'app_url': '',
                'has_module_perms': True,
                'models': models,
            })
    return sections


# Apply the monkey patch
showstack_admin_site.get_app_list = ordered_get_app_list
