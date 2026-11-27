"""Which device feeds which, as far as the stored text says. Read-only.

Three rules, each worked out live from what the other modules store -- no
result is saved, so editing a label changes the answer at once:

  (a) console / I/O output -> processor input
      * an I/O device output whose name is a processor input's label;
      * a console Matrix whose Destination is a processor input's label, or
        "<processor> <type> <n>" ("SL P1 AES 1"), or a processor's name on its
        own (a device-level match: the processor, no port).
      A Matrix fed out through an I/O output that itself matched (or is
      linked to) the same processor is dropped (VIA_IO): the I/O output is
      the physical hop, and counting both would draw the feed twice.
      Only inputs with no stored link are matched: an AES / Analog input
      linked to its source (a ``Connection``, PR 2b-3) is drawn from it.

  (b) processor (or I/O) output -> amp channel input
      Only inputs with no stored link: an input linked to its source output
      (a ``Connection``, PR 2b-2) is drawn from it, confirmed, never matched.
      ``x`` / ``-`` / ``n/a`` / blank are PLACEHOLDERS: an empty field, not
      text that failed to match. The field picks the output type. Being IN
      USE (a label or an assigned bus) is a tie-breaker, never a filter: when
      candidates sit on more than one processor, the unused ones drop out --
      P1 and Galaxy configs pre-create every output, so two P1s both "have"
      AVB 1 -- and a single processor left decides it; none or several left
      is ambiguous. One processor's unlabelled output still matches on its
      own. Accepted:
      * AVB Stream: ``AVB <n> - <label>`` (what the rack view's suggestions
        write, admin.py issue #43) -- channel AND label must match, channel
        only is DRIFT (the output was renamed after the amp was patched);
        ``AVB <n>`` or a bare ``<n>`` -- AVB output n, on whichever processor
        has one (two processors: ambiguous). A bare number that more than
        ``BARE_NUMBER_MAX`` outputs could be is not a match at all: "3" on a
        big rig says nothing.
      * AES Input, tried in order:
        1. ``<label>`` -- a processor AES output's label;
        2. ``<label> - <n>`` / ``<n> - <label>`` ("Center - 3") -- AES output
           n; when several processors have one, the one whose label is
           <label> wins, else ambiguous;
        3. ``<label>`` -- an I/O device output's name (a stage box feeding
           the amp directly, VIA I/O). A processor label wins over it.
      * Analogue Input: the fallback is fed from a processor's analogue
        outputs OR straight from an I/O device, depending on the engineer,
        so both are ONE POOL and neither is preferred (``_analog``):
        ``<label> - <n>`` / ``<n> - <label>`` is certain only when exactly one
        output in the pool is number n with that label (I/O: its name and
        its position on the device); ``<label>`` or ``<n>`` alone matches in
        the pool, with the in-use tie-breaker (I/O: named). "A" / "B" are
        input selections, not names, and never match.
      Several outputs on one I/O device: SAME_DEVICE (like SAME_PROCESSOR);
      candidates on different devices: ambiguous. A `` (<processor name>)``
      suffix, which the suggestions add when two processors share a label,
      limits candidates to that processor.

  (c) an older PA cable run that names neither end -> its two ends
      Only rows with no amp, no amp rack and no linked array: a run that
      has any of those was entered with its ends and is drawn as entered
      (``entered_pa_run``), never matched from text.
      In such a row Destination ("To") is the speaker array -- except when it
      is an amp rack's name (an Amp Location) or contains "amp rack", which
      some old rows do: then it is the AMP end, and the speaker end is
      unnamed.
      speaker end: Destination against each Speaker Array's base, display and
      source name; when no single array matches, the text itself (one node
      per distinct text, so cables naming the same thing meet there).
      amp end: the Amp FK; else the rack Destination names; else nothing.
      The row's Cable Label (model PAZone) is the cable's label, not an end.

Every match has one verdict:

  MATCHED         one port (or one processor by name)
  SAME_PROCESSOR  several ports, all on one processor -- certain, not
                  ambiguous: "L Main" on AES 1 and Analog 1 of one P1 is a
                  primary and its fallback
  SAME_DEVICE     (b) via I/O: several outputs of that name, all on one I/O
                  device ("L&R" twice on one stage box) -- certain likewise
  AMBIGUOUS       candidates on more than one processor / array / amp. Never
                  resolved: the graph draws the text, unlinked, and lists them
  UNMATCHED       nothing fits
  DRIFT           (b) only, see above
  VIA_IO          (a) only, see above
  PLACEHOLDER     (b) only: an x / - / n/a in an amp input field

Text is compared by ``norm``: case-folded, en/em dashes as "-", whitespace
collapsed. Blank text is not a source and never matches.

``ProjectIndex.load`` fetches everything in a fixed number of queries however
big the project is; the rule functions only read it. The graph and the
``infer_connections`` report both call ``match_all`` so they cannot disagree.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType

from planner.connections import endpoints as ep
from planner.models import (
    Amp, AmpChannel, AmpLocation, Connection, Console, ConsoleAuxOutput,
    CommPort, ConsoleMatrixOutput, ConsoleStereoOutput, Device, DeviceInput, DeviceOutput,
    GalaxyInput, GalaxyOutput, P1Input, P1Output, PACableSchedule, SpeakerArray,
    SystemProcessor,
)

MATCHED = 'matched'
SAME_PROCESSOR = 'same_processor'
AMBIGUOUS = 'ambiguous'
UNMATCHED = 'unmatched'
DRIFT = 'drift'
VIA_IO = 'via_io'
PLACEHOLDER = 'placeholder'
RACK = 'rack'                 # (c): the Destination named the amp rack

SAME_DEVICE = 'same_device'

RESOLVED = (MATCHED, SAME_PROCESSOR, SAME_DEVICE)

# (b): AmpChannel field -> the processor output type it can be fed from.
AMP_INPUT_FIELDS = (('avb_stream', 'AVB'), ('aes_input', 'AES'), ('analog_input', 'ANALOG'))
FIELD_TRANSPORT = {'avb_stream': 'avb', 'aes_input': 'aes', 'analog_input': 'analog'}
TRANSPORT_FIELD = {t: f for f, t in FIELD_TRANSPORT.items()}

_DASHES = re.compile('[‐-―−]')
_SPACES = re.compile(r'\s+')
_SUFFIX = re.compile(r'^(.*?)\s*\(([^()]*)\)\s*$')
_AVB = re.compile(r'^avb\s*(\d+)\s*(?:-\s*(.*))?$')
_TYPE_WORDS = {'analog': 'ANALOG', 'analogue': 'ANALOG', 'aes': 'AES',
               'aes/ebu': 'AES', 'avb': 'AVB', 'avb/milan': 'AVB'}
_BARE_NUMBER = re.compile(r'^(\d+)$')
BARE_NUMBER_MAX = 3      # a bare "3" with more candidates than this is not matched
_LABEL_NUMBER = re.compile(r'^(?P<label>.*\S)\s*-\s*(?P<n>\d+)$')
_NUMBER_LABEL = re.compile(r'^(?P<n>\d+)\s*-\s*(?P<label>\S.*)$')
PLACEHOLDERS = {'x', '-', 'n/a'}
_RACK_WORDS = 'amp rack'
_TYPED_PORT = re.compile(r'^(analog|analogue|aes/ebu|aes|avb/milan|avb)\s*(\d+)$')


def _ips(obj):
    """The IP Address Manager's two addresses for a console or I/O device."""
    return {'primary_ip': obj.primary_ip_address or '',
            'secondary_ip': obj.secondary_ip_address or ''}


def norm(text):
    """Comparison key: case-folded, dashes unified, whitespace collapsed."""
    text = _DASHES.sub('-', text or '')
    return _SPACES.sub(' ', text).strip().casefold()


# -- what the index holds ----------------------------------------------------

@dataclass
class Node:
    id: str
    kind: str
    label: str
    location: dict | None = None
    extra: dict = field(default_factory=dict)
    ip: str = ''        # tells two same-named devices apart (graph.unique_names); not in the JSON


@dataclass
class Port:
    ref: str
    node: str                 # node id of the device the port is on
    label: ep.PortLabel
    text: str = ''            # the port's name / label as stored
    type: str = ''            # processor ports: 'ANALOG' / 'AES' / 'AVB'
    number: int | None = None
    pk: int = 0
    in_use: bool = True       # processor output: a label or an assigned bus; I/O output: a name


@dataclass
class AmpInput:
    """One filled-in input field of one amp channel."""
    channel: Port
    field: str                # 'avb_stream' / 'aes_input' / 'analog_input'
    text: str


@dataclass
class Match:
    rule: str                 # 'a' / 'b'
    verdict: str
    source: Port              # (a) the output; (b) the amp channel
    text: str
    targets: tuple = ()       # resolved: processor ports, or a processor node id
    candidates: tuple = ()    # ambiguous / drift: what it could have been
    field: str = ''           # (b) only
    via: str = ''             # (a) 'label' / 'typed' / 'name'; (b) 'io' for an I/O output
    excluded: int = 0         # (b): unused outputs dropped to break a tie (0 = no tie decided)

    @property
    def transport(self):
        if self.field:
            return FIELD_TRANSPORT[self.field]
        return None


@dataclass
class End:
    """One end of a free-text PA cable run (rule c)."""
    verdict: str
    text: str
    target: str = ''          # node id
    via: str = ''             # 'fk' / 'amp_location' / 'rack_text' / 'array' / 'text'
    candidates: tuple = ()


@dataclass
class CableMatch:
    row: object               # the PACableSchedule
    speaker: End
    amp: End


def _location(loc, kind='location'):
    if loc is None:
        return None
    out = {'id': loc.pk, 'name': loc.name, 'kind': kind}
    if kind == ep.AMP_LOCATION:
        out['sort_order'] = loc.sort_order      # the amp column groups in this order
    return out


class ProjectIndex:
    """Every row the rules and the graph read, for one project, loaded once."""

    def __init__(self, project):
        self.project = project
        self.nodes = {}               # node id -> Node
        self.ports = {}               # port ref -> Port
        self.device_inputs = []       # (Port, linked ConsoleInput Port or None) -- A
        self.device_inputs_b = []     # (Port, B ConsoleInput Port, Source (B) text)
        self.device_outputs = []      # (Port, linked bus ref or '')
        self.matrices = []            # (Port, destination text)
        self.processor_inputs = []    # Port
        self.processor_outputs = []   # Port, used or not (see Port.in_use)
        self.amp_inputs = []          # AmpInput
        self.amp_placeholders = []    # AmpInput holding x / - / n/a
        self.amp_channels = []        # Port, every channel, filled in or not
        self.amp_links = []           # (Connection pk, source Port or None, channel Port or None, transport)
        self.linked_inputs = set()    # (channel ref, field) with a stored link
        self.processor_links = []     # (Connection pk, source Port or None, input Port or None, transport)
        self.linked_processor_inputs = set()   # processor input refs with a stored link
        self.pa_rows = []             # PACableSchedule
        self.array_names = defaultdict(set)     # norm(name) -> {node id}
        self.amp_location_names = defaultdict(set)
        self.processor_names = defaultdict(set)

    @classmethod
    def load(cls, project):
        index = cls(project)
        index._load()
        return index

    def _add(self, node):
        self.nodes[node.id] = node
        return node

    def _port(self, port):
        self.ports[port.ref] = port
        return port

    def _load(self):
        pid = self.project.pk

        # Devices -------------------------------------------------------
        for c in (Console.objects.filter(project_id=pid, is_template=False)
                  .select_related('location')):
            self._add(Node(ep.node_id(ep.CONSOLE, c.pk), ep.CONSOLE, c.name,
                           _location(c.location), _ips(c), c.primary_ip_address or ''))
        for d in Device.objects.filter(project_id=pid).select_related('location'):
            self._add(Node(ep.node_id(ep.DEVICE, d.pk), ep.DEVICE, d.name,
                           _location(d.location),
                           {**_ips(d), 'console_connection': d.console_connection or '',
                            # only when set, so a project with neither reads as before
                            **({'device_kind': d.kind} if d.kind != Device.IO else {}),
                            **({'dante_network': d.dante_network.strip()}
                               if d.dante_network.strip() else {})},
                           d.primary_ip_address or ''))
        for p in SystemProcessor.objects.filter(project_id=pid).select_related('location'):
            node = self._add(Node(ep.node_id(ep.PROCESSOR, p.pk), ep.PROCESSOR, p.name,
                                  _location(p.location), {'device_type': p.device_type},
                                  p.ip_address or ''))
            if norm(p.name):
                self.processor_names[norm(p.name)].add(node.id)
        for a in Amp.objects.filter(project_id=pid).select_related('location', 'amp_model'):
            self._add(Node(ep.node_id(ep.AMP, a.pk), ep.AMP, a.name,
                           _location(a.location, ep.AMP_LOCATION),
                           {'model': str(a.amp_model) if a.amp_model_id else ''},
                           a.ip_address or ''))
        for loc in AmpLocation.objects.filter(project_id=pid):
            node = self._add(Node(ep.node_id(ep.AMP_LOCATION, loc.pk), ep.AMP_LOCATION,
                                  loc.name, extra={'sort_order': loc.sort_order}))
            if norm(loc.name):
                self.amp_location_names[norm(loc.name)].add(node.id)
        for arr in SpeakerArray.objects.filter(prediction__project_id=pid):
            node = self._add(Node(ep.node_id(ep.ARRAY, arr.pk), ep.ARRAY, arr.display_name,
                                  extra={'prediction': arr.prediction_id}))
            for name in {arr.array_base_name, arr.display_name, arr.source_name}:
                if norm(name):
                    self.array_names[norm(name)].add(node.id)

        # Console buses (what a DeviceOutput's generic link points at) ----
        bus_cts = {}
        for model, prefix, label in (
                (ConsoleAuxOutput, 'consoleauxoutput', lambda b: ep.aux_label(b.aux_number)),
                (ConsoleMatrixOutput, 'consolematrixoutput',
                 lambda b: ep.matrix_label(b.matrix_number)),
                (ConsoleStereoOutput, 'consolestereooutput',
                 lambda b: ep.stereo_label(b.stereo_type))):
            bus_cts[ContentType.objects.get_for_model(model).pk] = prefix
            for bus in model.objects.filter(console__project_id=pid,
                                            console__is_template=False):
                port = self._port(Port(ep.port_ref(prefix, bus.pk),
                                       ep.node_id(ep.CONSOLE, bus.console_id),
                                       label(bus), (bus.name or '').strip(), pk=bus.pk))
                if model is ConsoleMatrixOutput and norm(bus.destination):
                    self.matrices.append((port, bus.destination.strip()))

        # I/O device ports, numbered by position as the device page does ---
        rows = (DeviceInput.objects
                .filter(device__project_id=pid, input_number__isnull=False)
                .order_by('device_id', 'input_number', 'pk')
                .values_list('pk', 'device_id', 'signal_name', 'console_input_id',
                             'console_input__console_id', 'console_input__input_ch',
                             'console_input__dante_number',
                             'console_input_b_id', 'console_input_b__console_id',
                             'console_input_b__input_ch', 'console_input_b__dante_number',
                             'console_input_b__source_b', 'device__kind'))
        position = defaultdict(int)
        for (pk, device_id, name, ci_pk, console_id, input_ch, dante,
             b_pk, b_console, b_ch, b_dante, source_b, device_kind) in rows:
            position[device_id] += 1
            if device_kind == Device.COMM:
                # A comm device's Dante In: an end of its comms links only --
                # no console link, and never matched by name.
                self._port(Port(ep.port_ref('deviceinput', pk),
                                ep.node_id(ep.DEVICE, device_id),
                                ep.PortLabel('Dante In', position[device_id]),
                                (name or '').strip(), pk=pk))
                continue
            port = self._port(Port(ep.port_ref('deviceinput', pk),
                                   ep.node_id(ep.DEVICE, device_id),
                                   ep.io_input_label(position[device_id]),
                                   (name or '').strip(), pk=pk))
            channel = None
            # A link into a template console or another project draws nothing.
            if ci_pk and ep.node_id(ep.CONSOLE, console_id) in self.nodes:
                channel = self._port(Port(ep.port_ref('consoleinput', ci_pk),
                                          ep.node_id(ep.CONSOLE, console_id),
                                          ep.console_input_label(input_ch, dante, ci_pk),
                                          pk=ci_pk))
            self.device_inputs.append((port, channel))
            # B: its own stored link (never a name), drawn as its own line.
            if b_pk and ep.node_id(ep.CONSOLE, b_console) in self.nodes:
                channel_b = self._port(Port(ep.port_ref('consoleinput', b_pk),
                                            ep.node_id(ep.CONSOLE, b_console),
                                            ep.console_input_label(b_ch, b_dante, b_pk),
                                            pk=b_pk))
                self.device_inputs_b.append((port, channel_b, (source_b or '').strip()))

        rows = (DeviceOutput.objects
                .filter(device__project_id=pid, output_number__isnull=False)
                .order_by('device_id', 'output_number', 'pk')
                .values_list('pk', 'device_id', 'signal_name', 'content_type_id', 'object_id',
                             'device__kind'))
        position = defaultdict(int)
        for pk, device_id, name, ct_id, obj_id, device_kind in rows:
            position[device_id] += 1
            if device_kind == Device.COMM:
                self._port(Port(ep.port_ref('deviceoutput', pk),
                                ep.node_id(ep.DEVICE, device_id),
                                ep.PortLabel('Dante Out', position[device_id]),
                                (name or '').strip(), pk=pk))
                continue
            port = self._port(Port(ep.port_ref('deviceoutput', pk),
                                   ep.node_id(ep.DEVICE, device_id),
                                   ep.io_output_label(position[device_id]),
                                   (name or '').strip(), number=position[device_id], pk=pk,
                                   in_use=bool((name or '').strip())))
            bus = ''
            if ct_id in bus_cts and obj_id:
                ref = ep.port_ref(bus_cts[ct_id], obj_id)
                bus = ref if ref in self.ports else ''
            self.device_outputs.append((port, bus))

        # Processor ports ---------------------------------------------------
        for model, prefix, type_field, owner, out in (
                (P1Input, 'p1input', 'input_type', 'p1_processor', False),
                (P1Output, 'p1output', 'output_type', 'p1_processor', True),
                (GalaxyInput, 'galaxyinput', 'input_type', 'galaxy_processor', False),
                (GalaxyOutput, 'galaxyoutput', 'output_type', 'galaxy_processor', True)):
            rows = (model.objects
                    .filter(**{f'{owner}__system_processor__project_id': pid})
                    .order_by(f'{owner}__system_processor_id', type_field, 'channel_number')
                    .values_list('pk', f'{owner}__system_processor_id', type_field,
                                 'channel_number', 'label',
                                 *(['assigned_bus'] if out else [])))
            for pk, proc_id, port_type, number, label, *bus in rows:
                label = (label or '').strip()
                port = self._port(Port(ep.port_ref(prefix, pk),
                                       ep.node_id(ep.PROCESSOR, proc_id),
                                       ep.processor_port_label(port_type, number),
                                       label, port_type, number, pk,
                                       in_use=bool(label) or bool(bus and bus[0])))
                (self.processor_outputs if out else self.processor_inputs).append(port)

        # Amp channels ------------------------------------------------------
        rows = (AmpChannel.objects
                .filter(amp__project_id=pid)
                .order_by('amp_id', 'channel_number', 'pk')
                .values_list('pk', 'amp_id', 'channel_number', 'channel_name',
                             'avb_stream', 'aes_input', 'analog_input'))
        for pk, amp_id, number, name, *values in rows:
            port = self._port(Port(ep.port_ref('ampchannel', pk), ep.node_id(ep.AMP, amp_id),
                                   ep.amp_channel_label(number), (name or '').strip(),
                                   number=number, pk=pk))
            self.amp_channels.append(port)
            for (fname, _), value in zip(AMP_INPUT_FIELDS, values):
                if norm(value) in PLACEHOLDERS:
                    self.amp_placeholders.append(AmpInput(port, fname, value.strip()))
                elif norm(value):
                    self.amp_inputs.append(AmpInput(port, fname, value.strip()))

        # Stored links: an amp input linked to its source output (PR 2b-2) --
        prefixes = {ContentType.objects.get_for_model(model).pk: prefix
                    for model, prefix in ((P1Output, 'p1output'), (GalaxyOutput, 'galaxyoutput'),
                                          (DeviceOutput, 'deviceoutput'))}
        amp_ct = ContentType.objects.get_for_model(AmpChannel).pk
        rows = (Connection.objects.filter(project_id=pid, to_ct_id=amp_ct)
                .order_by('pk').values_list('pk', 'from_ct_id', 'from_id', 'to_id', 'transport'))
        for pk, from_ct, from_id, to_id, transport in rows:
            source = self.ports.get(ep.port_ref(prefixes.get(from_ct, ''), from_id))
            channel = self.ports.get(ep.port_ref('ampchannel', to_id))
            self.amp_links.append((pk, source, channel, transport))
            if transport in TRANSPORT_FIELD:
                self.linked_inputs.add((ep.port_ref('ampchannel', to_id), TRANSPORT_FIELD[transport]))

        # Stored links: a processor input linked to its source (PR 2b-3) --
        prefixes = {ContentType.objects.get_for_model(model).pk: prefix
                    for model, prefix in ((DeviceOutput, 'deviceoutput'),
                                          (ConsoleAuxOutput, 'consoleauxoutput'),
                                          (ConsoleMatrixOutput, 'consolematrixoutput'),
                                          (ConsoleStereoOutput, 'consolestereooutput'))}
        inputs = {ContentType.objects.get_for_model(model).pk: prefix
                  for model, prefix in ((P1Input, 'p1input'), (GalaxyInput, 'galaxyinput'))}
        rows = (Connection.objects.filter(project_id=pid, to_ct_id__in=inputs)
                .order_by('pk').values_list('pk', 'from_ct_id', 'from_id', 'to_ct_id', 'to_id',
                                            'transport'))
        for pk, from_ct, from_id, to_ct, to_id, transport in rows:
            source = self.ports.get(ep.port_ref(prefixes.get(from_ct, ''), from_id))
            ref = ep.port_ref(inputs[to_ct], to_id)
            self.processor_links.append((pk, source, self.ports.get(ref), transport))
            self.linked_processor_inputs.add(ref)

        # Stored links: the comms patch (connections/comm_patch.py) ---------
        for port in CommPort.objects.filter(device__project_id=pid).order_by(
                'device_id', 'kind', 'number'):
            node = self.nodes.get(ep.node_id(ep.DEVICE, port.device_id))
            if port.kind == CommPort.FOUR_WIRE:
                self._port(Port(ep.port_ref('commport', port.pk),
                                ep.node_id(ep.DEVICE, port.device_id),
                                ep.PortLabel('4W', port.number), pk=port.pk))
            elif port.destination.strip() and node is not None:
                # A 2-wire port goes where its text says: no link, so it
                # rides on the comm device's node (the Comms tab draws it).
                node.extra.setdefault('two_wire', []).append({
                    'number': port.number, 'destination': port.destination.strip(),
                    'cable_type': port.cable_type.strip()})
        comm_cts = {ContentType.objects.get_for_model(model).pk: prefix
                    for model, prefix in ((DeviceInput, 'deviceinput'),
                                          (DeviceOutput, 'deviceoutput'),
                                          (CommPort, 'commport'))}
        rows = (Connection.objects.filter(project_id=pid, to_ct_id__in=comm_cts)
                .order_by('pk').values_list('pk', 'from_ct_id', 'from_id', 'to_ct_id', 'to_id',
                                            'transport', 'cable_type'))
        self.comm_links = []          # (Connection pk, from Port, to Port, transport, cable type)
        for pk, from_ct, from_id, to_ct, to_id, transport, cable_type in rows:
            source = self.ports.get(ep.port_ref(comm_cts.get(from_ct, ''), from_id))
            target = self.ports.get(ep.port_ref(comm_cts[to_ct], to_id))
            self.comm_links.append((pk, source, target, transport, cable_type))

        # PA cable runs -------------------------------------------------------
        self.pa_rows = list(PACableSchedule.objects.filter(project_id=pid)
                            .select_related('label')
                            .prefetch_related('speaker_arrays', 'fan_outs__extensions', 'links')
                            .order_by('id'))


# -- rule (a) ----------------------------------------------------------------

def _verdict(ports):
    """Resolved / ambiguous / unmatched from a list of candidate ports."""
    if not ports:
        return UNMATCHED
    if len({p.node for p in ports}) > 1:
        return AMBIGUOUS
    return MATCHED if len(ports) == 1 else SAME_PROCESSOR


def _resolve(rule, source, text, ports, **kw):
    verdict = _verdict(ports)
    ports = tuple(ports)
    if verdict in RESOLVED:
        return Match(rule, verdict, source, text, targets=ports, **kw)
    return Match(rule, verdict, source, text, candidates=ports, **kw)


def _unlinked_inputs(index):
    """Processor inputs with no stored link: only these are matched by text
    (a linked one is drawn from its source, PR 2b-3)."""
    return [p for p in index.processor_inputs if p.ref not in index.linked_processor_inputs]


def _inputs_by_label(index):
    by_label = defaultdict(list)
    for port in _unlinked_inputs(index):
        if norm(port.text):
            by_label[norm(port.text)].append(port)
    return by_label


def _typed_port(index, key):
    """"sl p1 aes 1" -> the candidate input ports of every processor so named."""
    found = []
    for name, nodes in index.processor_names.items():
        if not key.startswith(name + ' '):
            continue
        m = _TYPED_PORT.match(key[len(name) + 1:])
        if not m:
            continue
        port_type, number = _TYPE_WORDS[m.group(1)], int(m.group(2))
        found += [p for p in _unlinked_inputs(index)
                  if p.node in nodes and p.type == port_type and p.number == number]
    return found


def match_matrix(index, port, text, by_label=None):
    by_label = _inputs_by_label(index) if by_label is None else by_label
    key = norm(text)
    if by_label.get(key):
        return _resolve('a', port, text, by_label[key], via='label')
    typed = _typed_port(index, key)
    if typed:
        return _resolve('a', port, text, typed, via='typed')
    named = sorted(index.processor_names.get(key, ()))
    if len(named) == 1:
        return Match('a', MATCHED, port, text, targets=(named[0],), via='name')
    if named:
        return Match('a', AMBIGUOUS, port, text, candidates=tuple(named), via='name')
    return Match('a', UNMATCHED, port, text)


def match_device_output(index, port, by_label=None):
    by_label = _inputs_by_label(index) if by_label is None else by_label
    return _resolve('a', port, port.text, by_label.get(norm(port.text), []))


def _target_nodes(match):
    return {t if isinstance(t, str) else t.node for t in match.targets}


def rule_a(index):
    by_label = _inputs_by_label(index)
    io = [match_device_output(index, port, by_label)
          for port, _ in index.device_outputs if norm(port.text)]

    # Which processors each bus already reaches through a matched I/O output.
    reached = defaultdict(set)
    bus_of ={port.ref: bus for port, bus in index.device_outputs}
    for m in io:
        if m.verdict in RESOLVED and bus_of.get(m.source.ref):
            reached[bus_of[m.source.ref]] |= _target_nodes(m)
    for _, source, target, _ in index.processor_links:     # linked I/O outputs too
        if source and target and bus_of.get(source.ref):
            reached[bus_of[source.ref]].add(target.node)

    matrices = []
    for port, text in index.matrices:
        m = match_matrix(index, port, text, by_label)
        if m.verdict in RESOLVED and _target_nodes(m) & reached[port.ref]:
            m.verdict = VIA_IO
        matrices.append(m)
    return io + matrices


# -- rule (b) ----------------------------------------------------------------

def _split_suffix(index, text):
    """"L Main (SL P1)" -> ("L Main", {node ids of 'SL P1'}). A bracket that is
    not a processor's name is part of the label."""
    m = _SUFFIX.match(text)
    if m and norm(m.group(2)) in index.processor_names:
        return m.group(1), index.processor_names[norm(m.group(2))]
    return text, None


def _by_number(outputs, number, label=''):
    """Output ``number`` of one type. Several processors have one: the one
    whose label is ``label`` wins, else they are all candidates."""
    on_number = [p for p in outputs if p.number == number]
    labelled = [p for p in on_number if label and norm(p.text) == label]
    return labelled or on_number


def match_amp_input(index, amp_input):
    port_type = dict(AMP_INPUT_FIELDS)[amp_input.field]
    body, only = _split_suffix(index, amp_input.text)
    outputs = [p for p in index.processor_outputs
               if p.type == port_type and (only is None or p.node in only)]
    key = norm(body)
    src, text = amp_input.channel, amp_input.text

    def resolve(ports, via):
        excluded = 0
        if len({p.node for p in ports}) > 1:
            used = [p for p in ports if p.in_use]
            if used and len({p.node for p in used}) == 1:
                ports, excluded = used, len(ports) - len(used)
        match = _resolve('b', src, text, ports, field=amp_input.field, via=via)
        match.excluded = excluded
        if match.verdict == SAME_PROCESSOR and match.targets[0].node.startswith(ep.DEVICE + ':'):
            match.verdict = SAME_DEVICE     # _verdict's word; these are I/O outputs
        if match.verdict in RESOLVED and all(_is_io(t) for t in match.targets):
            match.via = 'io'
        return match

    if port_type == 'ANALOG':
        return _analog(index, key, outputs, only, resolve, src, text, amp_input.field)

    if port_type == 'AVB':
        m = _AVB.match(key) or _BARE_NUMBER.match(key)
        if m:
            number = int(m.group(1))
            label = norm(m.group(2)) if m.re is _AVB else ''
            on_channel = [p for p in outputs if p.number == number]
            if not label:
                match = resolve(on_channel, 'number')
                return _bare(match) if m.re is _BARE_NUMBER else match
            exact = [p for p in on_channel if norm(p.text) == label]
            if exact or not on_channel:
                return resolve(exact, 'label')
            return Match('b', DRIFT, src, text, candidates=tuple(on_channel),
                         field=amp_input.field)
        return resolve([p for p in outputs if norm(p.text) == key], 'label')

    exact = [p for p in outputs if norm(p.text) == key]
    if exact:
        return resolve(exact, 'label')
    m = _LABEL_NUMBER.match(key) or _NUMBER_LABEL.match(key)
    if m:
        found = _by_number(outputs, int(m.group('n')), norm(m.group('label')))
        if found:
            return resolve(found, 'number')
    if only is None:
        named = [p for p, _ in index.device_outputs if norm(p.text) == key]
        if named:
            return resolve(named, 'io')
    return resolve([], 'label')


def _is_io(port):
    return port.ref.startswith('deviceoutput:')


NEVER_NAMES = {'a', 'b'}      # analogue "A" / "B": an input selection, not a name


def _analog(index, key, outputs, only, resolve, src, text, field):
    """Analogue Input: processor analogue outputs and I/O outputs, one pool."""
    if key in NEVER_NAMES:
        return Match('b', UNMATCHED, src, text, field=field)
    pool = outputs + ([p for p, _ in index.device_outputs] if only is None else [])
    m = _LABEL_NUMBER.match(key) or _NUMBER_LABEL.match(key)
    if m:
        number, label = int(m.group('n')), norm(m.group('label'))
        both = [p for p in pool if p.number == number and norm(p.text) == label]
        if both:
            return resolve(both, 'number')          # several on one device: same_*
        either = [p for p in pool if p.number == number or norm(p.text) == label]
        if either:
            return Match('b', AMBIGUOUS, src, text, candidates=tuple(either), field=field)
        return Match('b', UNMATCHED, src, text, field=field)
    if _BARE_NUMBER.match(key):
        return _bare(resolve([p for p in pool if p.number == int(key)], 'number'))
    return resolve([p for p in pool if norm(p.text) == key], 'label')


def _bare(match):
    """A bare number with more than BARE_NUMBER_MAX candidates is not matched."""
    if match.verdict == AMBIGUOUS and len(match.candidates) > BARE_NUMBER_MAX:
        return Match('b', UNMATCHED, match.source, match.text, field=match.field)
    return match


def rule_b(index):
    return [match_amp_input(index, ai) for ai in index.amp_inputs
            if (ai.channel.ref, ai.field) not in index.linked_inputs]


# -- rule (c) ----------------------------------------------------------------

def _end(nodes, text, via):
    nodes = sorted(nodes)
    if len(nodes) == 1:
        return End(MATCHED, text, nodes[0], via)
    return End(AMBIGUOUS, text, via=via, candidates=tuple(nodes))


def _looks_like_rack(index, key):
    return key in index.amp_location_names or _RACK_WORDS in key


def match_cable(index, row):
    destination = (row.destination or '').strip()
    key = norm(destination)
    amp_node = ep.node_id(ep.AMP, row.amp_id) if row.amp_id else ''
    fk = End(MATCHED, '', amp_node, 'fk') if amp_node in index.nodes else None

    if key and _looks_like_rack(index, key):
        racks = index.amp_location_names.get(key, ())
        if fk:
            amp = fk
        elif len(racks) == 1:
            amp = End(MATCHED, destination, next(iter(racks)), 'amp_location')
        else:                           # "SR Amp Racks", no Amp Location of that name
            amp = End(UNMATCHED, destination, via='rack_text')
        return CableMatch(row, End(RACK, ''), amp)

    arrays = index.array_names.get(key, ()) if key else ()
    if arrays:
        speaker = _end(arrays, destination, 'array')
    else:
        speaker = End(UNMATCHED, destination, via='text' if key else '')
    return CableMatch(row, speaker, fk or End(UNMATCHED, ''))


def entered_pa_run(row):
    """A run entered with an end -- an amp, an amp rack or a linked array.

    The graph draws it as entered; rule (c) reads only the rest. Reads the
    prefetched arrays, so no query."""
    return bool(row.amp_id or row.amp_location_id or row.speaker_arrays.all())


def rule_c(index):
    return [match_cable(index, row) for row in index.pa_rows if not entered_pa_run(row)]


@dataclass
class Matches:
    a: list
    b: list
    c: list


def match_all(index):
    return Matches(rule_a(index), rule_b(index), rule_c(index))
