"""What feeds each console channel -- the Console page's read-only patch view.

For every channel row on a console it answers "which I/O device port is
patched here?", and for every I/O device in the project "which ports are still
free?". Read-only: nothing here writes, and the rules for *making* a link live
in planner/utils/device_patch.py.

Where a feed comes from, best first:

  LINKED     the port's stored link points at this channel (set by picking it
             on the I/O device page, or by link_device_inputs_by_name). A
             linked port counts for that channel ONLY: it never shows on
             another console, whatever its name. Same names on two consoles
             do not mean a split -- a monitor desk often has its own I/O.
  BY_NAME    the port has no link, and its name is a channel's name on this
             console and on no other console in the project, and on exactly
             one channel here -- typically a port patched before the link fix.
  AMBIGUOUS  the port has no link and its name fits more than one channel:
             several on this console (a duplicate "Spare"), or channels on
             other consoles too (FOH and MON with one channel list). Shown,
             dimmed, on each channel here it fits, naming the channels or the
             consoles, and counted on none. Never a conflict.

Inputs have an A and a B source. A port whose name is the channel's Source (B)
is that channel's B feed. A link always means A: the stored link has no A/B.
Two or more ports LINKED to one channel is a CONFLICT and each is flagged;
names alone never make one.

Outputs follow the same link / name rules. A bus feeding several I/O outputs
is normal (the same aux to two stage boxes), so outputs have no conflicts. Aux,
Matrix and Stereo can all be linked.

Cost, per request, however many channels or consoles: **two queries** -- every
DeviceInput in the project, every DeviceOutput -- plus, only when an unlinked
port's name matches a channel on this console, one more per side to see
whether another console has that name too. At most four. Cached on the
request by ``PortIndex.for_request``. This console's own channels are the rows
the Console page's inlines already loaded; nothing here fetches them again.
"""

from dataclasses import dataclass, field
from functools import cached_property
from itertools import groupby

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from planner.models import (
    ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput, ConsoleStereoOutput,
    DeviceInput, DeviceOutput,
)
from planner.utils.device_patch import norm

LINKED, BY_NAME, AMBIGUOUS = 'linked', 'by_name', 'ambiguous'
_ORDER = {LINKED: 0, BY_NAME: 1, AMBIGUOUS: 2}


@dataclass(frozen=True)
class Port:
    device_id: int
    device_name: str
    number: int          # 1-based position on the device, as its page and PDF number it
    name: str
    link: tuple | None   # inputs: (console id, channel pk); outputs: (content type id, pk)
    pk: int = 0          # the DeviceInput / DeviceOutput row

    @property
    def free(self):
        """Free = no name and no link. The one definition, used by the
        free-ports block and by the picker on the Console page."""
        return not self.name and not self.link


@dataclass
class Feed:
    port: Port
    how: str
    slot: str = 'A'      # inputs only
    conflict: bool = False
    others: tuple = ()   # for AMBIGUOUS: the channels ('ch 90') or consoles it fits
    across: bool = False # for AMBIGUOUS: ``others`` are consoles, not channels

    @property
    def url(self):
        return reverse('admin:planner_device_change', args=[self.port.device_id])


@dataclass
class Cell:
    feeds: list = field(default_factory=list)

    @property
    def conflict(self):
        return any(f.conflict for f in self.feeds)


def compress(numbers):
    """[17, 18, 19, 20, 29, 30, 31] -> '17-20, 29-31'."""
    parts = []
    for _, run in groupby(enumerate(sorted(numbers)), lambda p: p[1] - p[0]):
        run = [n for _, n in run]
        parts.append(str(run[0]) if len(run) == 1 else f'{run[0]}-{run[-1]}')
    return ', '.join(parts)


def _ports(rows):
    """Number each device's ports by position, the way its page does."""
    ports = []
    for _, device_rows in groupby(rows, key=lambda r: r[0]):
        for number, (device_id, device_name, name, ct_id, pk, row_pk) in enumerate(device_rows, 1):
            ports.append(Port(device_id, device_name, number, (name or '').strip(),
                              (ct_id, pk) if pk else None, row_pk))
    return ports


class PortIndex:
    """Every I/O device port in one project, loaded once per request."""

    def __init__(self, project_id):
        self.project_id = project_id

    @classmethod
    def for_request(cls, request, project_id):
        cache = request.__dict__.setdefault('_ss_port_index', {})
        if project_id not in cache:
            cache[project_id] = cls(project_id)
        return cache[project_id]

    @cached_property
    def inputs(self):
        rows = (DeviceInput.objects
                .filter(device__project_id=self.project_id, input_number__isnull=False)
                .order_by('device__name', 'device_id', 'input_number', 'pk')
                .values_list('device_id', 'device__name', 'signal_name',
                             'console_input__console_id', 'console_input_id', 'pk'))
        return _ports(rows)

    # -- names on every console ----------------------------------------------
    #
    # norm(name) -> {console id: console name}, for every non-template
    # console in the project. Only read when an unlinked port's name matches
    # a channel here, so a fully linked show never pays for it.

    @cached_property
    def input_names(self):
        rows = (ConsoleInput.objects
                .filter(console__project_id=self.project_id, console__is_template=False)
                .values_list('console_id', 'console__name', 'source', 'source_b'))
        names = {}
        for console_id, console_name, *values in rows:
            for value in values:
                if norm(value):
                    names.setdefault(norm(value), {})[console_id] = console_name
        return names

    @cached_property
    def output_names(self):
        def q(model):
            return (model.objects
                    .filter(console__project_id=self.project_id, console__is_template=False)
                    .values_list('console_id', 'console__name', 'name')
                    .order_by())  # a compound query takes no per-part ORDER BY
        rows = q(ConsoleAuxOutput).union(q(ConsoleMatrixOutput), q(ConsoleStereoOutput),
                                         all=True)
        names = {}
        for console_id, console_name, value in rows:
            if norm(value):
                names.setdefault(norm(value), {})[console_id] = console_name
        return names

    @staticmethod
    def _other_consoles(names, name, console_id):
        """Names of the OTHER consoles with a channel called ``name``."""
        found = names.get(norm(name), {})
        return sorted((n for cid, n in found.items() if cid != console_id), key=str.casefold)

    @cached_property
    def outputs(self):
        rows = (DeviceOutput.objects
                .filter(device__project_id=self.project_id, output_number__isnull=False)
                .order_by('device__name', 'device_id', 'output_number', 'pk')
                .values_list('device_id', 'device__name', 'signal_name',
                             'content_type_id', 'object_id', 'pk'))
        return _ports(rows)

    # -- console rows -----------------------------------------------------
    #
    # The Console page's four inlines each hand over the rows they loaded
    # (``register``), and a row's cell is computed on first request
    # (``cell_for``). Django builds every inline formset before it renders
    # any of them, so by the first cell_for the whole console is registered
    # -- which matters for outputs: a name on both an Aux and a Matrix is
    # ambiguous, and a port linked to Aux 3 is not a by-name feed for any
    # other bus on the same console.

    def register(self, rows):
        rows = [r for r in rows if r.pk]
        if not rows:
            return
        kind = 'inputs' if isinstance(rows[0], ConsoleInput) else 'outputs'
        self.__dict__.setdefault('_rows', {'inputs': {}, 'outputs': {}})
        self._rows[kind].update(((type(r), r.pk), r) for r in rows)
        self.__dict__.pop('_cells_' + kind, None)

    def cell_for(self, row):
        """The Cell for a registered row; None for one that is not."""
        if not getattr(row, 'pk', None):
            return None
        kind = 'inputs' if isinstance(row, ConsoleInput) else 'outputs'
        attr = '_cells_' + kind
        if attr not in self.__dict__:
            rows = list(self.__dict__.get('_rows', {}).get(kind, {}).values())
            self.__dict__[attr] = (self.inputs_for(rows) if kind == 'inputs'
                                   else self.outputs_for(rows))
        key = row.pk if kind == 'inputs' else (type(row), row.pk)
        return self.__dict__[attr].get(key)

    def inputs_for(self, channels):
        """{ConsoleInput pk: Cell} for one console's input rows."""
        channels = [c for c in channels if c.pk]
        if not channels:
            return {}
        console = channels[0].console
        cells = {c.pk: Cell() for c in channels}
        labels = {c.pk: f'ch {c.input_ch}' for c in channels}
        by_name = {}  # name -> {channel pk: slot}; A wins over B on one channel
        for c in channels:
            for value, slot in ((c.source_b, 'B'), (c.source, 'A')):
                if norm(value):
                    by_name.setdefault(norm(value), {})[c.pk] = slot

        for port in self.inputs:
            # An input link is stored as (console id, channel pk). Linked
            # elsewhere means not here, whatever the name.
            if port.link:
                if port.link[1] in cells:
                    cells[port.link[1]].feeds.append(Feed(port, LINKED))
                continue
            hits = by_name.get(norm(port.name), {})
            if not hits:
                continue
            consoles = self._other_consoles(self.input_names, port.name, console.pk)
            if consoles:
                others = tuple(sorted([console.name, *consoles], key=str.casefold))
                for pk, slot in hits.items():
                    cells[pk].feeds.append(Feed(port, AMBIGUOUS, slot, others=others, across=True))
            elif len(hits) == 1:
                (pk, slot), = hits.items()
                cells[pk].feeds.append(Feed(port, BY_NAME, slot))
            else:
                others = tuple(labels[pk] for pk in hits)
                for pk, slot in hits.items():
                    cells[pk].feeds.append(Feed(port, AMBIGUOUS, slot, others=others))

        for cell in cells.values():
            cell.feeds.sort(key=lambda f: (f.slot, _ORDER[f.how], f.port.device_name, f.port.number))
            for slot in ('A', 'B'):
                linked = [f for f in cell.feeds if f.slot == slot and f.how == LINKED]
                if len(linked) > 1:
                    for f in linked:
                        f.conflict = True
        return cells

    def outputs_for(self, buses):
        """{(model, pk): Cell} for one console's aux, matrix and stereo rows."""
        buses = [b for b in buses if b.pk]
        if not buses:
            return {}
        console = buses[0].console
        ct = {model: ContentType.objects.get_for_model(model).pk
              for model in (ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput)}
        cells = {(type(b), b.pk): Cell() for b in buses}
        linked = {(ct[type(b)], b.pk): (type(b), b.pk) for b in buses}
        labels = {(type(b), b.pk): _bus_label(b) for b in buses}
        by_name = {}
        for b in buses:
            if norm(b.name):
                by_name.setdefault(norm(b.name), []).append((type(b), b.pk))

        for port in self.outputs:
            if port.link:
                if port.link in linked:
                    cells[linked[port.link]].feeds.append(Feed(port, LINKED))
                continue
            hits = by_name.get(norm(port.name), [])
            if not hits:
                continue
            consoles = self._other_consoles(self.output_names, port.name, console.pk)
            if consoles:
                others = tuple(sorted([console.name, *consoles], key=str.casefold))
                for key in hits:
                    cells[key].feeds.append(Feed(port, AMBIGUOUS, others=others, across=True))
            elif len(hits) == 1:
                cells[hits[0]].feeds.append(Feed(port, BY_NAME))
            else:
                others = tuple(labels[k] for k in hits)
                for key in hits:
                    cells[key].feeds.append(Feed(port, AMBIGUOUS, others=others))
        for cell in cells.values():
            cell.feeds.sort(key=lambda f: (_ORDER[f.how], f.port.device_name, f.port.number))
        return cells

    # -- free ports ---------------------------------------------------------

    def free_ports(self):
        """One summary per device: free = blank name AND no link."""
        devices = {}
        for side, ports in (('inputs', self.inputs), ('outputs', self.outputs)):
            for port in ports:
                d = devices.setdefault(port.device_id, {
                    'id': port.device_id, 'name': port.device_name,
                    'inputs': [], 'outputs': [], 'input_total': 0, 'output_total': 0,
                })
                d[side[:-1] + '_total'] += 1
                if port.free:
                    d[side].append(port.number)
        summaries = []
        for d in sorted(devices.values(), key=lambda d: (d['name'].casefold(), d['id'])):
            summaries.append({
                'name': d['name'],
                'url': reverse('admin:planner_device_change', args=[d['id']]),
                'free_inputs': len(d['inputs']), 'input_total': d['input_total'],
                'input_ranges': compress(d['inputs']),
                'free_outputs': len(d['outputs']), 'output_total': d['output_total'],
                'output_ranges': compress(d['outputs']),
            })
        return summaries


def _bus_label(bus):
    if isinstance(bus, ConsoleAuxOutput):
        return f'Aux {bus.aux_number}'
    if isinstance(bus, ConsoleMatrixOutput):
        return f'Mtx {bus.matrix_number}'
    return f'St {bus.stereo_type}'
