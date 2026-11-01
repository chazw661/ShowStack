"""The help topic registry.

Each topic is one task, written for the crew, with its body in
``templates/help/topics/<slug>.html``. ``pages`` are the page keys (see
``context.page_key``) where Help should lead with this topic; the tests fail if
any of them stops existing, so renaming or removing a page means updating its
topics too.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    slug: str
    title: str
    section: str
    summary: str
    pages: tuple
    keywords: tuple = ()

    @property
    def template(self):
        return 'help/topics/{}.html'.format(self.slug)


SECTIONS = (
    'Getting started',
    'Show day',
    'Consoles & I/O',
    'Amps & PA',
    'Comms',
    'Documentation & recording',
    'Mobile',
)

TOPICS = (
    # -- Getting started ---------------------------------------------
    Topic(
        slug='project-create-switch',
        title='Create a project and switch between projects',
        section='Getting started',
        summary='Start a new show project, open it, and switch between projects.',
        pages=(
            'dashboard',
            'admin:index',
            'admin:planner_project_changelist',
        ),
        keywords=('project', 'new project', 'create', 'switch', 'open project', 'dropdown', 'show', 'beta', 'paid',),
    ),
    Topic(
        slug='project-roles',
        title='Owner, editor, viewer: who can change what',
        section='Getting started',
        summary='What owners, editors and viewers can do; change roles, leave or delete.',
        pages=(
            'project_detail',
            'dashboard',
            'project_invitations',
        ),
        keywords=('role', 'owner', 'editor', 'viewer', 'read-only', 'permissions', 'manage team', 'leave project', 'delete project',),
    ),
    Topic(
        slug='project-invite-email',
        title='Invite someone to a project by email',
        section='Getting started',
        summary='Email an invite so someone joins your project as editor or viewer.',
        pages=(
            'project_invitations',
            'invite_user',
            'dashboard',
            'accept_invitation',
        ),
        keywords=('invite', 'email', 'invitation', 'accept', 'editor', 'viewer', 'crew', 'share', 'expire',),
    ),
    Topic(
        slug='project-invite-link',
        title='Share an invite link and approve access requests',
        section='Getting started',
        summary='Share one link; approve each access request as editor or viewer.',
        pages=(
            'access_requests',
            'request_access',
            'admin:planner_project_changelist',
            'project_detail',
        ),
        keywords=('invite link', 'share link', 'access request', 'approve', 'deny', 'request access', 'copy link',),
    ),
    Topic(
        slug='crew-rosters',
        title='Build a crew and add it to a project',
        section='Getting started',
        summary='Save a crew roster once, then add everyone to a project together.',
        pages=(
            'crew_index',
            'crew_detail',
            'invite_user',
        ),
        keywords=('crew', 'roster', 'my crew', 'team', 'bulk add', 'pending signup', 'default role',),
    ),
    Topic(
        slug='locations',
        title='Add equipment locations and print location sheets',
        section='Getting started',
        summary='Create locations like FOH or Stage and print what lives there.',
        pages=(
            'admin:planner_location_changelist',
        ),
        keywords=('location', 'equip locations', 'FOH', 'monitor world', 'inventory', 'pdf', 'location sheet', 'print',),
    ),

    # -- Show day ----------------------------------------------------
    Topic(
        slug='mic-days-sessions',
        title='Add show days and sessions',
        section='Show day',
        summary='Create show days, add sessions with RF mics, duplicate or delete a session.',
        pages=(
            'planner:mic_tracker',
            'admin:planner_showday_changelist',
            'admin:planner_micsession_changelist',
            'admin:planner_micshowinfo_changelist',
        ),
        keywords=('show day', 'session', 'add day', 'add session', 'duplicate', 'copy session', 'delete session', 'number of mics', 'schedule',),
    ),
    Topic(
        slug='mic-assign-presenters',
        title='Assign presenters to RF mics',
        section='Show day',
        summary='Type or pick a presenter on each A2 card and set mic details.',
        pages=(
            'planner:mic_tracker',
            'admin:planner_presenter_changelist',
            'admin:planner_micassignment_changelist',
        ),
        keywords=('presenter', 'assign', 'rf', 'a2 card', 'talent', 'name', 'drag', 'swap', 'placement', 'headset color',),
    ),
    Topic(
        slug='mic-shared-rotation',
        title='Share one mic between presenters',
        section='Show day',
        summary='Add several presenters to one RF and step through them with PREV/NEXT.',
        pages=(
            'planner:mic_tracker',
        ),
        keywords=('shared mic', 'multiple presenters', 'rotation', 'next', 'prev', 'add presenter', 'handoff', 'slot', 'd-mic',),
    ),
    Topic(
        slug='mic-micd-views',
        title="Mark mics MIC'D and use the A1 and A2 views",
        section='Show day',
        summary="Toggle MIC'D, switch A1/A2 views, colour-code mics, scan the Overview.",
        pages=(
            'planner:mic_tracker',
            'planner:mic_tracker_overview',
        ),
        keywords=("mic'd", 'micd', 'a1', 'a2', 'overview', 'groups', 'colour', 'grp', 'status', 'd-mic',),
    ),
    Topic(
        slug='mic-photos',
        title='Add presenter photos',
        section='Show day',
        summary='Add a photo to a card for one session or every session.',
        pages=(
            'planner:mic_tracker',
            'admin:planner_presenter_changelist',
        ),
        keywords=('photo', 'headshot', 'picture', 'drag', 'image', 'mic position', 'session photo',),
    ),
    Topic(
        slug='mic-import-export',
        title='Import presenters from CSV and export the mic sheet',
        section='Show day',
        summary='Load presenter names from a CSV; export the mic sheet as CSV or PDF.',
        pages=(
            'planner:mic_tracker',
            'admin:planner_presenter_changelist',
            'planner:import_presenters_csv',
        ),
        keywords=('csv', 'import', 'export', 'pdf', 'spreadsheet', 'mic sheet', 'print', 'presenter list',),
    ),
    Topic(
        slug='mic-labels',
        title='Print beltpack labels',
        section='Show day',
        summary='Print presenter labels for the front of each bodypack: one name per label, or the running order per pack.',
        pages=(
            'planner:mic_tracker',
            'planner:mic_tracker_print',
        ),
        keywords=('label', 'labels', 'beltpack', 'bodypack', 'pack', 'sticker', 'print', 'running order', 'OL3016LP', 'alignment', 'calibration',),
    ),
    Topic(
        slug='label-branding',
        title='Brand the beltpack labels',
        section='Show day',
        summary="Print the labels in the client's colours, with their logo.",
        pages=(
            'planner:project_branding',
            'planner:mic_tracker_print',
        ),
        keywords=('branding', 'brand', 'logo', 'client', 'colour', 'color', 'accent', 'toner', 'label', 'labels',),
    ),
    Topic(
        slug='mic-updates-banner',
        title='Keep several screens in sync ("Updates available")',
        section='Show day',
        summary="How the tracker picks up other screens' changes, and when to refresh.",
        pages=(
            'planner:mic_tracker',
            'planner:mic_tracker_overview',
            'admin:planner_micsession_changelist',
        ),
        keywords=('updates available', 'refresh', 'sync', 'live', 'multiple screens', 'saved', 'save failed', 'banner',),
    ),
    Topic(
        slug='listen-install',
        title='Install ShowStack Listen on the FOH Mac',
        section='Show day',
        summary='Install the Listen Mac app at the rack and start it for the show.',
        pages=(
            'planner:mic_tracker',
        ),
        keywords=('listen', 'companion', 'mac app', 'dante virtual soundcard', 'dvs', 'install', 'rack', 'menu bar', 'audio input',),
    ),
    Topic(
        slug='listen-a2-setup',
        title='Let an A2 listen to a beltpack on their phone',
        section='Show day',
        summary='Set up a phone once, then listen to any pack.',
        pages=(
            'planner:mic_tracker',
        ),
        keywords=('listen', 'a2', 'phone', 'beltpack', 'qr code', 'certificate', 'audio ch', 'channel', 'monitor', 'rub',),
    ),
    Topic(
        slug='checklist-work',
        title='Work through the FOH, A2 and Prep checklists',
        section='Show day',
        summary='Set task status and stage on each list; changes save instantly for everyone.',
        pages=(
            'admin:planner_audiochecklist_changelist',
            'planner:audio_checklist',
        ),
        keywords=('checklist', 'audio checklist', 'foh', 'a2', 'prep', 'status', 'line check', 'daily tasks', 'setup tasks', 'print', 'csv',),
    ),
    Topic(
        slug='checklist-edit-tasks',
        title='Add, move and delete checklist tasks',
        section='Show day',
        summary='Add setup or daily tasks, rename them, reorder with arrows, delete.',
        pages=(
            'admin:planner_audiochecklist_changelist',
            'planner:audio_checklist',
        ),
        keywords=('checklist', 'add task', 'delete task', 'reorder', 'move task', 'rename task', 'setup task', 'daily task',),
    ),
    Topic(
        slug='checklist-days-reset',
        title='Set show days and reset for the next show',
        section='Show day',
        summary='Add or remove day columns, rename days, and reset all lists to defaults.',
        pages=(
            'admin:planner_audiochecklist_changelist',
            'planner:audio_checklist',
        ),
        keywords=('checklist', 'days', 'add day', 'show days', 'rename day', 'reset', 'reset all', 'next show', 'defaults',),
    ),
    Topic(
        slug='checklist-templates',
        title='Save and load a checklist template',
        section='Show day',
        summary='Reuse your task list across shows; loading replaces every current task.',
        pages=(
            'admin:planner_audiochecklist_changelist',
            'planner:audio_checklist',
        ),
        keywords=('checklist', 'template', 'save template', 'load template', 'reuse', 'standard list',),
    ),

    # -- Consoles & I/O ----------------------------------------------
    Topic(
        slug='console-add',
        title='Add a console and name its inputs',
        section='Consoles & I/O',
        summary='Create a console and fill in channel names, hardware and A/B sources.',
        pages=(
            'admin:planner_console_changelist',
        ),
        keywords=('console', 'inputs', 'channel', 'source', 'source hardware', 'a/b', 'autofill', 'dante', 'rivage', 'pm7',),
    ),
    Topic(
        slug='console-outputs',
        title='Set up aux, matrix and stereo outputs',
        section='Consoles & I/O',
        summary='Name mixes, matrices and main buses, and pair stereo mixes.',
        pages=(
            'admin:planner_console_changelist',
        ),
        keywords=('aux', 'mix', 'matrix', 'stereo', 'mono', 'buss', 'bus type', 'wedge', 'outputs',),
    ),
    Topic(
        slug='console-patch-column',
        title='Patch from the console page',
        section='Consoles & I/O',
        summary="Tap a channel's Patch cell to patch, replace or unpatch a stage box port.",
        pages=(
            'admin:planner_console_changelist',
        ),
        keywords=('patch', 'unpatch', 'replace', 'stage box', 'by name', 'ambiguous', 'conflict', 'amber', 'free ports', 'linked', 'name not saved',),
    ),
    Topic(
        slug='console-rivage-export',
        title='Export a Rivage PM CSV',
        section='Consoles & I/O',
        summary='Download a zip of 11 Rivage CSV files with channel and mix names.',
        pages=(
            'admin:planner_console_changelist',
        ),
        keywords=('yamaha', 'rivage', 'pm editor', 'csv', 'export', 'zip', 'inname', 'channel names',),
    ),
    Topic(
        slug='console-templates',
        title='Save and load console templates',
        section='Consoles & I/O',
        summary='Save a console to My templates and load it into another project.',
        pages=(
            'admin:planner_console_changelist',
            'admin:console_template_library',
            'admin:planner_showtemplate_changelist',
        ),
        keywords=('template', 'my templates', 'load template', 'copy console', 'reuse', 'library',),
    ),
    Topic(
        slug='source-hardware',
        title='Add your own source hardware names',
        section='Consoles & I/O',
        summary='Add a mic or DI model to the console Source Hardware dropdown.',
        pages=(
            'admin:planner_console_changelist',
            'admin:planner_sourcehardwareoption_changelist',
        ),
        keywords=('source hardware', 'mic model', 'DI', 'dropdown', 'add new', 'manage list', 'input list',),
    ),
    Topic(
        slug='io-add-device',
        title='Add a stage box or I/O device',
        section='Consoles & I/O',
        summary='Create a stage box with its input and output count.',
        pages=(
            'admin:planner_device_changelist',
        ),
        keywords=('stage box', 'i/o device', 'rack', 'rio', 'input count', 'output count', 'add device',),
    ),
    Topic(
        slug='io-patch-inputs',
        title='Patch stage box inputs to console channels',
        section='Consoles & I/O',
        summary='Pick a console channel for each stage box input to name and link it.',
        pages=(
            'admin:planner_device_changelist',
        ),
        keywords=('patch', 'stage box', 'inputs', 'link', 'channel', 'suggestions', 'signal name',),
    ),
    Topic(
        slug='io-outputs',
        title='Label stage box outputs',
        section='Consoles & I/O',
        summary='Name each stage box output after the aux, matrix or bus it carries.',
        pages=(
            'admin:planner_device_changelist',
        ),
        keywords=('outputs', 'aux', 'matrix', 'wedge', 'stage box', 'label', 'link',),
    ),
    Topic(
        slug='console-io-print',
        title='Print console and I/O device sheets',
        section='Consoles & I/O',
        summary="Make PDFs of a console's channel list or the stage box patch.",
        pages=(
            'admin:planner_console_changelist',
            'admin:planner_device_changelist',
        ),
        keywords=('pdf', 'print', 'export', 'console sheet', 'device sheet', 'patch sheet', 'all devices',),
    ),

    # -- Amps & PA ---------------------------------------------------
    Topic(
        slug='amps-add',
        title='Add amps to the rack',
        section='Amps & PA',
        summary='Create rack locations and add amps by model and name.',
        pages=(
            'admin:planner_amp_changelist',
        ),
        keywords=('amp', 'amplifier', 'rack', 'location', 'la12x', 'add amp', 'ip', 'preset', 'deep edit',),
    ),
    Topic(
        slug='amps-assign-channels',
        title='Label amp inputs, outputs and channel zones',
        section='Amps & PA',
        summary='Fill in AVB, analogue and AES inputs, channel settings and output labels.',
        pages=(
            'admin:planner_amp_changelist',
        ),
        keywords=('amp channel', 'avb', 'aes', 'analogue', 'channel setting', 'nl4', 'cacom', 'sc32', 'zone', 'sub',),
    ),
    Topic(
        slug='amps-output-cabinets',
        title='Say which cabinets are on each amp output',
        section='Amps & PA',
        summary='Pick a cabinet section and how many are in parallel on each output, and check the load.',
        pages=(
            'admin:planner_amp_changelist',
        ),
        keywords=('cabinet', 'speaker', 'output', 'load', 'impedance', 'ohm', 'parallel', 'quantity', 'minimum', 'Kara II', 'KS28', 'power plan', 'drive capacity', 'per output', 'total',),
    ),
    Topic(
        slug='amps-rack-dividers',
        title='Split the rack with dividers',
        section='Amps & PA',
        summary='Add labelled dividers inside a location and reorder locations.',
        pages=(
            'admin:planner_amp_changelist',
        ),
        keywords=('divider', 'section', 'reorder', 'locations', 'rack order', 'collapse',),
    ),
    Topic(
        slug='amps-print',
        title='Print the amp sheet',
        section='Amps & PA',
        summary='Download every amp card as a landscape PDF grouped by location.',
        pages=(
            'admin:planner_amp_changelist',
        ),
        keywords=('pdf', 'print', 'export', 'amp sheet', 'rack sheet',),
    ),
    Topic(
        slug='processors-p1',
        title='Set up an L-Acoustics P1 processor',
        section='Amps & PA',
        summary='Add a P1, then label its inputs, outputs and buses.',
        pages=(
            'admin:planner_systemprocessor_changelist',
            'admin:planner_p1processor_changelist',
        ),
        keywords=('p1', 'l-acoustics', 'processor', 'avb', 'bus', 'system processor', 'milan',),
    ),
    Topic(
        slug='processors-galaxy',
        title='Set up a Meyer GALAXY processor',
        section='Amps & PA',
        summary='Add a GALAXY, then label inputs, outputs, buses and destinations.',
        pages=(
            'admin:planner_systemprocessor_changelist',
            'admin:planner_galaxyprocessor_changelist',
        ),
        keywords=('galaxy', 'meyer', 'processor', 'avb', 'milan', 'bus', 'destination',),
    ),
    Topic(
        slug='pa-cable-add-run',
        title='Add a PA cable run',
        section='Amps & PA',
        summary='Log a speaker cable run by zone or linked Soundvision array.',
        pages=(
            'admin:planner_pacableschedule_changelist',
            'admin:planner_pazone_changelist',
        ),
        keywords=('pa cable', 'nl4', 'nl8', 'cable run', 'zone', 'label', 'destination', 'length', 'duplicate',),
    ),
    Topic(
        slug='pa-cable-fanouts-jumpers',
        title='Add fan-outs, extensions and jumpers',
        section='Amps & PA',
        summary='Add breakouts, extensions and couplers to a run; log jumpers by count.',
        pages=(
            'admin:planner_pacableschedule_changelist',
        ),
        keywords=('fan out', 'y cable', 'extension', 'coupler', 'jumper', 'nl4 jumper', 'dosub', 'dofill',),
    ),
    Topic(
        slug='pa-cable-import-csv',
        title='Import cable runs from CSV',
        section='Amps & PA',
        summary='Bulk-load PA cable runs, fan-outs and couplers from a spreadsheet.',
        pages=(
            'planner:import_pa_cables_csv',
            'admin:planner_pacableschedule_changelist',
        ),
        keywords=('csv', 'import', 'spreadsheet', 'bulk', 'sample csv', 'cable schedule',),
    ),
    Topic(
        slug='pa-cable-totals-print',
        title='Read the cable totals and print the schedule',
        section='Amps & PA',
        summary='Read stock cables needed with 20% spare, and print the PDF.',
        pages=(
            'admin:planner_pacableschedule_changelist',
        ),
        keywords=('totals', 'order', 'stock', "100'", "50'", "25'", 'safety', 'quick order', 'pdf', 'print',),
    ),
    Topic(
        slug='power-plan',
        title='Build a power distribution plan',
        section='Amps & PA',
        summary='Add amps to a power plan and check current per leg and imbalance.',
        pages=(
            'admin:planner_powerdistributionplan_changelist',
            'admin:planner_amplifierassignment_changelist',
            'planner:power_distribution_calculator',
            'planner:power_distribution_calculator_detail',
        ),
        keywords=('power', 'power distribution', 'calculator', 'phase', 'leg', 'amps per leg', 'imbalance', 'programme', '1/8 power', '1/3 power', 'estimate', 'power factor', 'headroom', 'safety margin', '3-phase',),
    ),
    Topic(
        slug='power-plan-generate',
        title='Generate a power plan from the amp module',
        section='Amps & PA',
        summary='One click: a plan with a row per amp, on its real cabinets, legs balanced.',
        pages=(
            'admin:planner_amp_changelist',
            'planner:power_distribution_calculator_detail',
        ),
        keywords=('generate power plan', 'regenerate', 'leg', 'L1', 'L2', 'L3', 'auto', 'balance', 'split-phase', 'single-phase', '3-phase distro', 'other audio electronics', 'allowance', 'worst case',),
    ),
    Topic(
        slug='power-amp-profiles',
        title='Look up amplifier power profiles',
        section='Amps & PA',
        summary='The shared, read-only catalogue of amp power figures.',
        pages=(
            'admin:planner_amplifierprofile_changelist',
        ),
        keywords=('amplifier profile', 'amp power', 'idle watts', 'rated power', 'power factor', 'LA12X', 'LA8', 'LA4X', 'LA7.16i',),
    ),
    Topic(
        slug='power-cabinet-models',
        title='Look up cabinet models and impedances',
        section='Amps & PA',
        summary='The shared, read-only catalogue of loudspeaker cabinets, their sections and nominal impedance.',
        pages=(
            'admin:planner_cabinetmodel_changelist',
        ),
        keywords=('cabinet', 'cabinet model', 'speaker', 'enclosure', 'impedance', 'ohm', 'section', 'LF', 'HF', 'Kara II', 'K2', 'KS28', 'A10', 'passive', 'active',),
    ),
    Topic(
        slug='soundvision-upload',
        title='Upload a Soundvision prediction PDF',
        section='Amps & PA',
        summary='Upload a Soundvision report PDF and have its arrays read in.',
        pages=(
            'admin:planner_soundvisionprediction_changelist',
            'planner:predictions_list',
        ),
        keywords=('soundvision', 'prediction', 'pdf', 'upload', 'l-acoustics', 'array', 'rigging',),
    ),
    Topic(
        slug='soundvision-review-export',
        title='Review arrays and export a prediction summary',
        section='Amps & PA',
        summary='Check trims, weights and box angles, then export CSV or PDF.',
        pages=(
            'planner:prediction_detail',
            'planner:predictions_list',
            'admin:planner_soundvisionprediction_changelist',
            'admin:planner_speakerarray_changelist',
            'admin:planner_speakercabinet_changelist',
        ),
        keywords=('soundvision', 'array', 'trim', 'weight', 'motor load', 'rigging', 'csv', 'pdf', 'panflex', 'mbar',),
    ),

    # -- Comms -------------------------------------------------------
    Topic(
        slug='comm-devices-add',
        title='Add beltpacks and comm devices',
        section='Comms',
        summary='Log beltpacks, panels and stations one at a time or twenty at once.',
        pages=(
            'admin:planner_commbeltpack_changelist',
            'admin:commbeltpack_add_multiple',
            'admin:planner_commposition_changelist',
            'admin:planner_commchannel_changelist',
            'admin:planner_commdevicemodel_changelist',
        ),
        keywords=('beltpack', 'belt pack', 'comm device', 'intercom', 'add multiple', 'bulk', 'model', 'device number', 'channels', 'position', 'headset', 'hardwired', 'wireless', 'key panel',),
    ),
    Topic(
        slug='comm-checkout',
        title='Check beltpacks in and out',
        section='Comms',
        summary='One tap marks a wireless pack OUT or back IN.',
        pages=(
            'admin:planner_commbeltpack_changelist',
            'mobile:comm_list',
        ),
        keywords=('check out', 'check in', 'checked out', 'beltpack', 'wireless', 'IN', 'OUT', 'available', 'load-out', 'phone',),
    ),
    Topic(
        slug='comm-crew-names-csv',
        title='Import crew names from CSV',
        section='Comms',
        summary='Load a crew list from a one-column CSV into this project.',
        pages=(
            'admin:planner_commcrewname_changelist',
            'planner:import_comm_crew_names_csv',
            'admin:planner_commbeltpack_changelist',
            'planner:comm_config_editor',
        ),
        keywords=('crew names', 'csv', 'import', 'spreadsheet', 'excel', 'names', 'roster', 'column a',),
    ),
    Topic(
        slug='comm-print',
        title='Print the beltpack sheet',
        section='Comms',
        summary='Print every comm device with its user, location and channels.',
        pages=(
            'admin:planner_commbeltpack_changelist',
            'admin:planner_location_changelist',
        ),
        keywords=('print', 'pdf', 'beltpack sheet', 'system report', 'comm system', 'export', 'paperwork', 'rack',),
    ),
    Topic(
        slug='cca-start',
        title='Start an Arcadia or FreeSpeak II config',
        section='Comms',
        summary='Create a Clear-Com Arcadia or FreeSpeak II config to edit and export.',
        pages=(
            'planner:comm_config',
            'planner:comm_config_editor',
        ),
        keywords=('clear-com', 'arcadia', 'freespeak', 'fsii', 'cca', 'comm config', 'new configuration', 'base station', 'intercom',),
    ),
    Topic(
        slug='cca-partylines',
        title='Build partylines',
        section='Comms',
        summary='Name, add and remove the talk channels in a Clear-Com config.',
        pages=(
            'planner:comm_config_editor',
        ),
        keywords=('partyline', 'channel', 'clear-com', 'arcadia', 'freespeak', 'helixnet', 'rename', 'PL',),
    ),
    Topic(
        slug='cca-roles-keys',
        title='Set up roles and keysets',
        section='Comms',
        summary="Create a role per position and set each key's channel and behaviour.",
        pages=(
            'planner:comm_config_editor',
        ),
        keywords=('role', 'keyset', 'keys', 'beltpack', 'v-panel', 'talk', 'listen', 'latching', 'momentary', 'reply key', 'helixnet', 'edge',),
    ),
    Topic(
        slug='cca-ports',
        title='Assign ports',
        section='Comms',
        summary='Name 2-wire and 4-wire ports and route them to partylines.',
        pages=(
            'planner:comm_config_editor',
        ),
        keywords=('ports', '2-wire', '4-wire', '2W', '4W', 'termination', 'power', 'matrix', 'rts', 'dante', 'arcadia', 'freespeak',),
    ),
    Topic(
        slug='cca-export',
        title='Export the .cca and load it on the system',
        section='Comms',
        summary='Download the .cca file for an Arcadia or FreeSpeak II base.',
        pages=(
            'planner:comm_config_editor',
        ),
        keywords=('export', 'cca', 'download', 'clear-com', 'arcadia', 'freespeak', 'password', '04312B48', 'load', 'base station',),
    ),
    Topic(
        slug='cca-templates',
        title='Save and load a COMM config template',
        section='Comms',
        summary='Reuse a COMM config by saving it as a template and loading copies.',
        pages=(
            'planner:comm_config',
            'planner:comm_config_editor',
        ),
        keywords=('template', 'save as template', 'load template', 'reuse', 'standard', 'comm config', 'copy',),
    ),

    # -- Documentation & recording -----------------------------------
    Topic(
        slug='system-overview-report',
        title='See the system overview and print the System Report',
        section='Documentation & recording',
        summary='Whole-project overview at a glance, plus the one-PDF Complete System Report.',
        pages=(
            'admin:index',
            'planner:system-dashboard',
        ),
        keywords=('system overview', 'system report', 'system pdf', 'dashboard', 'home', 'complete system report', 'print', 'qr', 'mobile',),
    ),
    Topic(
        slug='ip-addresses',
        title='Record device IP addresses and export the list',
        section='Documentation & recording',
        summary='Edit every device IP on one page; export as PDF or CSV.',
        pages=(
            'planner:ip_address_report',
        ),
        keywords=('ip', 'ip address', 'network', 'dante', 'primary', 'secondary', 'csv', 'pdf', 'duplicate ip',),
    ),
    Topic(
        slug='multitrack-build',
        title='Build a multitrack record session from a console',
        section='Documentation & recording',
        summary='Pick console channels into a named, coloured, ordered recording track list.',
        pages=(
            'planner:multitrack_dashboard',
            'planner:multitrack_create',
            'planner:multitrack_editor',
            'planner:multitrack_edit',
            'planner:console_import_upload',
        ),
        keywords=('multitrack', 'recording', 'record', 'tracks', 'track list', 'session', 'reaper', 'nuendo', 'capacity', 'template', 'colour', 'color', 'import console csv',),
    ),
    Topic(
        slug='multitrack-export',
        title='Export a multitrack session to Reaper or Nuendo Live',
        section='Documentation & recording',
        summary='Download a Reaper project, Reaper track template or Nuendo Live project.',
        pages=(
            'planner:multitrack_editor',
            'planner:multitrack_dashboard',
        ),
        keywords=('multitrack', 'export', 'reaper', 'rpp', 'track template', 'rtracktemplate', 'nuendo', 'nuendo live', 'nlpr', 'daw',),
    ),
    Topic(
        slug='signalflow-start',
        title='Start a signal flow diagram and place gear',
        section='Documentation & recording',
        summary='Create a diagram, drop shapes and link them to project equipment.',
        pages=(
            'planner:signal_flow_list',
            'planner:signal_flow_editor',
        ),
        keywords=('signal flow', 'diagram', 'block diagram', 'flow chart', 'shapes', 'console', 'amp', 'speaker array', 'beltpack', 'equipment picker',),
    ),
    Topic(
        slug='signalflow-ports-export',
        title='Label ports, connect gear and export a PNG',
        section='Documentation & recording',
        summary='Add labelled ports, draw typed connectors, annotate, then export PNG or PDF.',
        pages=(
            'planner:signal_flow_editor',
        ),
        keywords=('signal flow', 'ports', 'connector', 'cable', 'circuit label', 'dante', 'aes', 'madi', 'resize', 'text', 'boundary', 'png', 'pdf', 'export',),
    ),

    # -- Mobile ------------------------------------------------------
    Topic(
        slug='mobile-mic-tracker',
        title='Use the Mic Tracker on your phone',
        section='Mobile',
        summary='Sign in at /m/ and look up who is on which mic.',
        pages=(
            'mobile:login',
            'mobile:dashboard',
            'mobile:project_overview',
            'mobile:mic_tracker_days',
            'mobile:mic_tracker_sessions',
            'mobile:mic_tracker_assignments',
        ),
        keywords=('mobile', 'phone', '/m/', 'mic tracker', 'sign in', 'search', 'backstage',),
    ),
    Topic(
        slug='mobile-predictions',
        title='View predictions on your phone',
        section='Mobile',
        summary='View PA arrays, trims and box angles on your phone.',
        pages=(
            'mobile:project_overview',
            'mobile:predictions_list',
            'mobile:prediction_detail',
        ),
        keywords=('mobile', 'predictions', 'soundvision', 'array', 'rigging', 'trim',),
    ),
)

TOPICS_BY_SLUG = {t.slug: t for t in TOPICS}
