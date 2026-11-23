"""A comm device's patch: what its page lists, checks and saves.

A comm device (``Device.kind == 'comm'``: an Arcadia or another intercom main
station) has Dante ins and outs (its ``DeviceInput`` / ``DeviceOutput`` rows),
4-wire ports and 2-wire ports (``CommPort``). Its own page is the only place
its patch is edited. Each row there is a text box with a datalist, as the amp
and processor pickers are, listing every port it can go to:

  Dante In n  <-  an I/O device INPUT (the jack the audio goes in at: "MK88 In
                  3", "DVS In 1" = the Mac's mic), or another comm device's
                  Dante Out
  Dante Out n ->  an I/O device OUTPUT (where it comes out: "MK88 Out 3"), or
                  another comm device's Dante In
  4W n send   ->  an I/O device INPUT   (a cable into it)
  4W n receive <- an I/O device OUTPUT  (a cable from it)
  2W n            typed text ("Wired BP chain SL") and a cable type; no picker

Dante lists put devices on this device's Dante network first; an entry on
another network ends "[Main 96k]", picking it is allowed and warned about
(``Row.warning``; the Wiring Diagram's Warnings panel lists it too).

Dante and 4W patches are ``Connection`` rows, one per signal, running the way
the signal does. Nothing else is stored: a row's text is read from its link
on every page load, so a renamed device or port needs no rewrite. Text that
is not exactly one entry is an error on its row, never free text.

``build(device, data)`` reads the page (``data`` None) or checks a POST;
``apply(page)`` saves a checked one. No request, no admin: ``planner/admin.py``
calls these.
"""
from collections import defaultdict
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from planner.connections import sources as S
from planner.connections.sources import Source
from planner.models import CommPort, Connection, Device, DeviceInput, DeviceOutput

DIN, DOUT, SEND, RECV = 'din', 'dout', 'send', 'recv'
FIELDS = (DIN, DOUT, SEND, RECV)
DANTE_FIELDS = (DIN, DOUT)
PRESENT = 'comm-patch-present'      # the page's grids were in the POST
MODELS = {'deviceinput': DeviceInput, 'deviceoutput': DeviceOutput, 'commport': CommPort}
NOT_LISTED = 'Pick an entry from the list, or leave it blank.'


def _ct(model):
    return ContentType.objects.get_for_model(model)


def network_differs(a, b):
    """Two Dante networks, both set and not the same one."""
    a, b = Device.network_key(a), Device.network_key(b)
    return bool(a and b and a != b)


# -- ports ---------------------------------------------------------------------

def _numbered(model, number_field, **filters):
    """[(pk, device id, position, signal name)]: ports numbered by position
    on their device, as its page and the wiring diagram number them."""
    rows = (model.objects.filter(**filters, **{f'{number_field}__isnull': False})
            .order_by('device_id', number_field, 'pk')
            .values_list('pk', 'device_id', 'signal_name'))
    position = defaultdict(int)
    out = []
    for pk, device_id, name in rows:
        position[device_id] += 1
        out.append((pk, device_id, position[device_id], (name or '').strip()))
    return out


def sync_ports(device):
    """Make a comm device's port rows match its counts: add the missing ones,
    delete those past the count (``build`` has refused a patched one)."""
    if not device.is_comm:
        return
    for model, number, count in ((DeviceInput, 'input_number', device.input_count),
                                 (DeviceOutput, 'output_number', device.output_count)):
        have = set(model.objects.filter(device=device).values_list(number, flat=True))
        for n in range(1, count + 1):
            if n not in have:
                model.objects.create(device=device, signal_name='', **{number: n})
        for port in model.objects.filter(device=device, **{f'{number}__gt': count}):
            port.delete()       # one by one: its links go with it
    for kind, count in ((CommPort.FOUR_WIRE, device.four_wire_count),
                        (CommPort.TWO_WIRE, device.two_wire_count)):
        have = set(device.comm_ports.filter(kind=kind).values_list('number', flat=True))
        for n in range(1, count + 1):
            if n not in have:
                CommPort.objects.create(device=device, kind=kind, number=n)
        for port in device.comm_ports.filter(kind=kind, number__gt=count):
            port.delete()


# -- picker entries --------------------------------------------------------------

def _entry(device, port, signal):
    port = f'{device} {port}'
    return f'{signal} · {port}' if signal else port


def all_sources(device):
    """Every (port, field) this comm device's rows can pick, in list order:
    for the Dante fields its own network's devices first, then by device
    name and port. Entries that would read the same are lengthened
    (``sources.disambiguate``)."""
    others = {d.pk: d for d in (Device.objects.filter(project_id=device.project_id)
                                .exclude(pk=device.pk).select_related('location'))}
    out = []

    def add(fields, model_name, rows, word):
        for pk, device_id, position, signal in rows:
            other = others.get(device_id)
            if other is None:
                continue
            for f in fields:
                if (other.kind == Device.COMM) != (word.startswith('Dante')):
                    continue
                text = _entry(other.name, f'{word} {position}', signal)
                far = f in DANTE_FIELDS and network_differs(device.dante_network,
                                                            other.dante_network)
                if far:
                    text = f'{text} [{other.dante_network.strip()}]'
                same = (f in DANTE_FIELDS and Device.network_key(device.dante_network)
                        and Device.network_key(device.dante_network)
                        == Device.network_key(other.dante_network))
                out.append(((FIELDS.index(f), 0 if same else 1, other.name.casefold(),
                             other.name, device_id, word, position, pk),
                            Source(model_name, pk, f, text, other.name, ('device', device_id),
                                   other.location.name if other.location_id else '',
                                   other.primary_ip_address or '',
                                   network=other.dante_network.strip() if far else '')))

    pid = device.project_id
    inputs = _numbered(DeviceInput, 'input_number', device__project_id=pid)
    outputs = _numbered(DeviceOutput, 'output_number', device__project_id=pid)
    add((DIN, SEND), 'deviceinput', inputs, 'In')            # I/O inputs
    add((DOUT, RECV), 'deviceoutput', outputs, 'Out')        # I/O outputs
    add((DIN,), 'deviceoutput', outputs, 'Dante Out')        # another comm device's
    add((DOUT,), 'deviceinput', inputs, 'Dante In')
    out.sort(key=lambda item: item[0])
    return S.disambiguate([source for _, source in out])


def _any_length(_field):
    return 10 ** 6


def picker(sources):
    """{field: {entry text: Source}}: every entry naming exactly one port."""
    entries = S.picker(sources, _any_length)
    return {f: entries.get(f, {}) for f in FIELDS}


def listing(sources):
    """{field: [entry text]} for the page's datalists."""
    return {f: [s.text for s in S.listing(sources, f, 10 ** 6)] for f in FIELDS}


# -- the page --------------------------------------------------------------------

@dataclass
class Cell:
    name: str               # the POST field
    value: str = ''
    field: str = ''         # DIN / DOUT / SEND / RECV; '' for plain text
    error: str = ''
    warning: str = ''
    source: Source | None = None


@dataclass
class Row:
    port: object
    label: str
    cells: dict = field(default_factory=dict)       # 'link' / 'send' / 'recv' / 'cable' / 'dest'


@dataclass
class Page:
    device: Device
    din: list
    dout: list
    four_wire: list
    two_wire: list
    lists: dict             # {field: [entry text]}
    far: dict               # {field: {entry text: its network}}: the warned-about entries
    errors: list = field(default_factory=list)
    checked: bool = False   # built from a POST

    @property
    def rows(self):
        return self.din + self.dout + self.four_wire + self.two_wire

    @property
    def cells(self):
        return [c for r in self.rows for c in r.cells.values()]

    @property
    def warnings(self):
        return [f'{r.label}: {c.warning}' for r in self.rows for c in r.cells.values()
                if c.warning]


def _links(device, inputs, outputs, comm):
    """This device's stored links: ({(field, port pk): Connection})."""
    cts = {m: _ct(model).pk for m, model in MODELS.items()}
    out = {}
    for conn in Connection.objects.filter(project_id=device.project_id,
                                          to_ct_id=cts['deviceinput'], to_id__in=inputs):
        out[(DIN, conn.to_id)] = conn
    for conn in Connection.objects.filter(project_id=device.project_id,
                                          from_ct_id=cts['deviceoutput'], from_id__in=outputs):
        out[(DOUT, conn.from_id)] = conn
    for conn in Connection.objects.filter(project_id=device.project_id,
                                          from_ct_id=cts['commport'], from_id__in=comm):
        out[(SEND, conn.from_id)] = conn
    for conn in Connection.objects.filter(project_id=device.project_id,
                                          to_ct_id=cts['commport'], to_id__in=comm):
        out[(RECV, conn.to_id)] = conn
    return out


def _far_end(f, conn):
    """(model, pk) of the end of ``conn`` that is not this device's row."""
    if f in (DIN, RECV):
        return conn.from_ct.model, conn.from_id
    return conn.to_ct.model, conn.to_id


def _taken_text(conn, labels):
    return labels.get((conn.from_ct.model, conn.from_id), 'another port')


def port_labels(project_id):
    """{(model, pk): "Arcadia Dante In 3" / "MK88 Out 3" / "Arcadia 4W 1"} for
    every device port of the project."""
    kinds = dict(Device.objects.filter(project_id=project_id).values_list('pk', 'kind'))
    names = dict(Device.objects.filter(project_id=project_id).values_list('pk', 'name'))
    out = {}
    for model_name, model, number, word in (('deviceinput', DeviceInput, 'input_number', 'In'),
                                            ('deviceoutput', DeviceOutput, 'output_number', 'Out')):
        for pk, device_id, position, _ in _numbered(model, number, device__project_id=project_id):
            dante = 'Dante ' if kinds.get(device_id) == Device.COMM else ''
            out[(model_name, pk)] = f'{names.get(device_id, "")} {dante}{word} {position}'
    for port in CommPort.objects.filter(device__project_id=project_id):
        out[('commport', port.pk)] = f'{names.get(port.device_id, "")} {port.label}'
    return out


def build(device, data=None, counts=None):
    """The comm device's patch page. ``data`` None: as stored. Else a POST's
    QueryDict, checked: every cell keeps what was typed, a bad one carries
    its ``error`` (and ``page.errors`` is not empty). ``counts``: the port
    counts the same POST asks for ({'input_count': 4, ...}); a patched port
    past a lowered count is an error."""
    inputs = list(device.inputs.filter(input_number__isnull=False).order_by('input_number', 'pk'))
    outputs = list(device.outputs.filter(output_number__isnull=False)
                   .order_by('output_number', 'pk'))
    comm = list(device.comm_ports.order_by('kind', 'number'))
    sources = all_sources(device)
    entries = picker(sources)
    by_key = {(s.field, s.model, s.pk): s for s in sources}
    stored = _links(device, [p.pk for p in inputs], [p.pk for p in outputs],
                    [p.pk for p in comm])
    for conn in stored.values():
        conn.from_ct, conn.to_ct = (ContentType.objects.get_for_id(conn.from_ct_id),
                                    ContentType.objects.get_for_id(conn.to_ct_id))
    checked = data is not None and PRESENT in data
    page = Page(device, [], [], [], [], listing(sources),
                {f: {s.text: s.network for s in sources if s.field == f and s.network}
                 for f in DANTE_FIELDS}, checked=checked)

    def link_cell(f, port, name):
        cell = Cell(name, field=f)
        conn = stored.get((f, port.pk))
        if checked:
            cell.value = (data.get(name) or '').strip()
            if cell.value:
                cell.source = entries[f].get(cell.value)
                if cell.source is None:
                    cell.error = NOT_LISTED
        elif conn is not None:
            cell.source = by_key.get((f,) + _far_end(f, conn))
            cell.value = cell.source.text if cell.source else ''
        if cell.source is not None and cell.source.network:
            cell.warning = (f'{cell.source.group} is on Dante network '
                            f'“{cell.source.network}”, not “{device.dante_network.strip()}”. '
                            'Devices on different networks cannot be routed to each other.')
        return cell

    def text_cell(name, value, max_length):
        cell = Cell(name, value=value or '')
        if checked:
            cell.value = (data.get(name) or '').strip()
            if len(cell.value) > max_length:
                cell.error = f'{max_length} characters at most.'
        return cell

    for n, port in enumerate(inputs, 1):
        page.din.append(Row(port, f'Dante In {n}',
                            {'link': link_cell(DIN, port, f'comm-din-{port.pk}')}))
    for n, port in enumerate(outputs, 1):
        page.dout.append(Row(port, f'Dante Out {n}',
                             {'link': link_cell(DOUT, port, f'comm-dout-{port.pk}')}))
    for port in comm:
        base = f'comm-{port.kind}-{port.pk}'
        if port.kind == CommPort.FOUR_WIRE:
            conns = [stored.get((SEND, port.pk)), stored.get((RECV, port.pk))]
            cable = next((c.cable_type for c in conns if c is not None),
                         CommPort.DEFAULT_4W_CABLE)
            page.four_wire.append(Row(port, port.label, {
                'send': link_cell(SEND, port, f'{base}-send'),
                'recv': link_cell(RECV, port, f'{base}-recv'),
                'cable': text_cell(f'{base}-cable', cable, 40)}))
        else:
            page.two_wire.append(Row(port, port.label, {
                'dest': text_cell(f'{base}-dest', port.destination, 100),
                'cable': text_cell(f'{base}-cable', port.cable_type, 40)}))
    if not checked:
        return page

    labels = port_labels(device.project_id)
    mine = {(m, p.pk) for m, ports in (('deviceinput', inputs), ('deviceoutput', outputs),
                                       ('commport', comm)) for p in ports}
    cts = {m: _ct(model).pk for m, model in MODELS.items()}
    # A port takes one feed per transport, and a Dante Out goes to one place:
    # neither twice on this page, nor where another device's row already is.
    claimed = {}
    for row in page.rows:
        for cell in row.cells.values():
            s = cell.source
            if s is None or cell.error:
                continue
            one_feed = cell.field in (DOUT, SEND)                   # the far end is fed
            one_place = cell.field == DIN and s.model == 'deviceoutput'   # a comm Dante Out
            if not (one_feed or one_place):
                continue
            transport = 'dante' if cell.field in DANTE_FIELDS else 'analog'
            key = (s.model, s.pk, transport)
            if key in claimed:
                cell.error = f'{s.text} is already picked on {claimed[key]}.'
                continue
            claimed[key] = row.label
            if one_feed:
                others = Connection.objects.filter(to_ct_id=cts[s.model], to_id=s.pk,
                                                   transport=transport)
            else:
                others = Connection.objects.filter(from_ct_id=cts[s.model], from_id=s.pk)
            for other in others.select_related('from_ct', 'to_ct'):
                ends = {(other.from_ct.model, other.from_id), (other.to_ct.model, other.to_id)}
                if not ends & mine:
                    if one_feed:
                        cell.error = (f'{s.text} is already fed by '
                                      f'{_taken_text(other, labels)}.')
                    else:
                        cell.error = (f'{s.text} already goes to '
                                      f'{labels.get((other.to_ct.model, other.to_id), "another port")}.')

    if counts:
        limits = {DIN: counts.get('input_count'), DOUT: counts.get('output_count')}
        for f, rows in ((DIN, page.din), (DOUT, page.dout)):
            for n, row in enumerate(rows, 1):
                if limits[f] is not None and n > limits[f] and row.cells['link'].value:
                    row.cells['link'].error = ('This port is patched: clear it before '
                                               'lowering the count.')
        for kind, rows, key in ((CommPort.FOUR_WIRE, page.four_wire, 'four_wire_count'),
                                (CommPort.TWO_WIRE, page.two_wire, 'two_wire_count')):
            limit = counts.get(key)
            for row in rows:
                used = [c for name, c in row.cells.items() if name != 'cable' and c.value]
                if limit is not None and row.port.number > limit and used:
                    used[0].error = 'This port is patched: clear it before lowering the count.'

    page.errors = [f'{r.label}: {c.error}' for r in page.rows for c in r.cells.values()
                   if c.error]
    return page


def unbuilt_ports_patched(device, counts):
    """Labels of stored patched ports a lowered count would delete, for a
    POST that did not carry the grids."""
    page = build(device)
    out = []
    for rows, key in ((page.din, 'input_count'), (page.dout, 'output_count')):
        limit = counts.get(key)
        out += [r.label for n, r in enumerate(rows, 1)
                if limit is not None and n > limit and r.cells['link'].value]
    for rows, key in ((page.four_wire, 'four_wire_count'), (page.two_wire, 'two_wire_count')):
        limit = counts.get(key)
        out += [r.label for r in rows if limit is not None and r.port.number > limit
                and any(c.value for name, c in r.cells.items() if name != 'cable')]
    return out


def apply(page):
    """Save a checked page with no errors: its links replace the device's
    stored ones (removed first, so a patch can move between rows in one
    save), and its 2-wire text is written. Returns the Connections kept or
    made."""
    if not page.checked or page.errors:
        raise ValueError('apply() needs a checked page with no errors')
    device = page.device
    cts = {m: _ct(model) for m, model in MODELS.items()}
    wanted = {}             # (from ct id, from id, to ct id, to id, transport) -> cable type
    for row in page.din:
        s = row.cells['link'].source
        if s:
            wanted[(cts[s.model].pk, s.pk, cts['deviceinput'].pk, row.port.pk, 'dante')] = ''
    for row in page.dout:
        s = row.cells['link'].source
        if s:
            wanted[(cts['deviceoutput'].pk, row.port.pk, cts[s.model].pk, s.pk, 'dante')] = ''
    for row in page.four_wire:
        cable = row.cells['cable'].value
        s = row.cells['send'].source
        if s:
            wanted[(cts['commport'].pk, row.port.pk, cts[s.model].pk, s.pk, 'analog')] = cable
        s = row.cells['recv'].source
        if s:
            wanted[(cts[s.model].pk, s.pk, cts['commport'].pk, row.port.pk, 'analog')] = cable

    with transaction.atomic():
        stored = _links(device, [r.port.pk for r in page.din], [r.port.pk for r in page.dout],
                        [r.port.pk for r in page.four_wire + page.two_wire])
        kept = {}
        for conn in {c.pk: c for c in stored.values()}.values():
            key = (conn.from_ct_id, conn.from_id, conn.to_ct_id, conn.to_id, conn.transport)
            if key in wanted:
                kept[key] = conn
            else:
                conn.delete()
        out = []
        for key, cable in wanted.items():
            conn = kept.get(key)
            if conn is None:
                conn = Connection(project_id=device.project_id, from_ct_id=key[0],
                                  from_id=key[1], to_ct_id=key[2], to_id=key[3],
                                  transport=key[4], cable_type=cable)
                conn.save()
            elif conn.cable_type != cable:
                conn.cable_type = cable
                conn.save()
            out.append(conn)
        for row in page.two_wire:
            port, dest, cable = row.port, row.cells['dest'].value, row.cells['cable'].value
            if (port.destination, port.cable_type) != (dest, cable):
                port.destination, port.cable_type = dest, cable
                port.save(update_fields=['destination', 'cable_type'])
    return out


# -- the other device's page -----------------------------------------------------

def port_notes(device):
    """What an I/O device's ports show, read-only, for the comms links they
    are in: {('in' | 'out', port pk): [{'text': '← Arcadia Dante Out 3',
    'device_id': <the comm device>}]}. The arrow runs the way the signal does:
    ← fed by, → feeds."""
    cts = {_ct(model).pk: m for m, model in MODELS.items()}
    ids = {'deviceinput': set(device.inputs.values_list('pk', flat=True)),
           'deviceoutput': set(device.outputs.values_list('pk', flat=True))}
    if not (ids['deviceinput'] or ids['deviceoutput']):
        return {}
    from django.db.models import Q
    q = Q()
    for model_name, pks in ids.items():
        ct = _ct(MODELS[model_name]).pk
        q |= Q(from_ct_id=ct, from_id__in=pks) | Q(to_ct_id=ct, to_id__in=pks)
    rows = [c for c in Connection.objects.filter(q, project_id=device.project_id).order_by('pk')
            if cts.get(c.from_ct_id) and cts.get(c.to_ct_id)]
    if not rows:
        return {}
    labels = port_labels(device.project_id)
    owner = {}
    for model_name, model in MODELS.items():
        pks = {pk for c in rows for ct, pk in ((c.from_ct_id, c.from_id), (c.to_ct_id, c.to_id))
               if cts[ct] == model_name}
        owner.update({(model_name, pk): dev for pk, dev in
                      model.objects.filter(pk__in=pks).values_list('pk', 'device_id')})
    side = {'deviceinput': 'in', 'deviceoutput': 'out'}
    notes = defaultdict(list)
    for c in rows:
        frm, to = (cts[c.from_ct_id], c.from_id), (cts[c.to_ct_id], c.to_id)
        for here, there, arrow, way in ((to, frm, '←', ' send'), (frm, to, '→', ' receive')):
            if here[0] in ids and here[1] in ids[here[0]] and owner.get(there) != device.pk:
                text = labels.get(there, '')
                if there[0] == 'commport':
                    text += way
                notes[(side[here[0]], here[1])].append(
                    {'text': f'{arrow} {text}', 'device_id': owner.get(there)})
    return dict(notes)
