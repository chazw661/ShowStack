"""Patching from the Console page -- the picker behind each Patch cell.

Phase A (planner/utils/console_patch.py) shows what feeds each channel. This
is the write side: tap a channel's Patch cell, choose an I/O device and a free
port, and the port is linked to the channel. Nothing new about what a link IS:
every write goes through planner/utils/device_patch.py -- ``link_input_port`` /
``link_output_port`` to patch, ``apply_input_link`` / ``apply_output_link`` to
free a port -- so a port patched here is stored exactly as if its channel had
been picked on the I/O device page.

An unnamed channel can be patched. The port takes the name the engineer sees
on this page: a name typed into the row and not yet saved (the request carries
it; the console form is never submitted), else the saved name, else blank.
Saving the page later moves the saved name onto the port (planner/signals.py),
so port and channel agree either way.

What can be patched:

  * Inputs, A (kind ``in``): the A link and the port's name, as below. Only
    FREE ports (no name, no A link -- ``Port.free``; a linked port with a
    blank name is used). A used port is shown dimmed with its use; a port
    that is only another channel's B is free for A and says "B for Ch 5".
  * Inputs, B (kind ``inb``): the B link only (``console_input_b``); the
    port's name and A link are never touched. Any port with no B link may
    be picked, whatever its name or A link, and shows its use ("A for Ch
    3"). This channel's own A port is offered with "same port as A". A
    channel has ONE B source: a second is refused, so B has Replace and no
    Add.
  * Outputs: Aux, Matrix and Stereo.
  * Only I/O devices in the console's project.

The current patch of a channel is its A feeds that are LINKED or BY NAME.
Ambiguous names fit several channels and belong to none, so they are never
replaced or unpatched from here.

Replace or add is always the engineer's explicit choice once a channel already
has a patch: ``replace`` frees the current ports and links the new one in one
transaction; ``add`` keeps them, which on an input is a second A feed -- a
CONFLICT, and the picker says so before it is sent. On an output, one bus to
several ports is normal, so add is just add.

Staleness: every read hands out ``state``, a short hash of the channel's name
and its feeds. A write must send it back; if the channel or its patch changed
since (another tab, another engineer, a rename), the write is refused with 409
and the fresh state, and nothing is written. A port that stopped being free is
a 409 too. The check runs after the channel and port rows are locked, inside
the write's transaction.

Split ports: when a split becomes a stored record, a split port's patch will
belong to its device page. ``port_lock`` is where that goes -- it names why a
port may not be patched or unpatched here, the picker greys the port with that
reason, and ``apply`` refuses it. Nothing is locked today.
"""

import hashlib

from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from planner.models import (
    ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput, ConsoleStereoOutput,
    DeviceInput, DeviceOutput,
)
from planner.utils import device_patch
from planner.utils.console_patch import BY_NAME, LINKED, PortIndex, _bus_label

KINDS = {
    'in': ConsoleInput,
    'inb': ConsoleInput,      # the same channel, its B slot
    'aux': ConsoleAuxOutput,
    'mtx': ConsoleMatrixOutput,
    'st': ConsoleStereoOutput,
}
REPLACE, ADD = 'replace', 'add'


class PatchError(Exception):
    """A refused write: HTTP status, a machine code, a sentence for the panel."""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def kind_of(channel, slot='A'):
    if isinstance(channel, ConsoleInput):
        return 'inb' if slot == 'B' else 'in'
    for kind, model in KINDS.items():
        if isinstance(channel, model):
            return kind
    raise ValueError(channel)


def slot_of(kind):
    return 'B' if kind == 'inb' else 'A'


def is_input(channel):
    return isinstance(channel, ConsoleInput)


def channel_name(channel):
    return ((channel.source if is_input(channel) else channel.name) or '').strip()


def channel_label(channel):
    return f'Ch {channel.input_ch}' if is_input(channel) else _bus_label(channel)


def load_channel(kind, pk, project, lock=False):
    """The project's channel of this kind, or None. ``lock`` takes a row lock
    (Postgres) on the channel for the rest of the transaction."""
    model = KINDS.get(kind)
    if model is None or project is None:
        return None
    qs = model.objects.select_related('console').filter(pk=pk, console__project=project)
    if lock:
        qs = qs.select_for_update(of=('self',))
    return qs.first()


def _console_rows(channel):
    """Every row on the channel's side of its console -- what the Console page
    registers -- so a name shared with another row reads as ambiguous here
    exactly as it does on the page."""
    console = channel.console
    if is_input(channel):
        rows = list(ConsoleInput.objects.filter(console=console))
    else:
        rows = [r for model in (ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput)
                for r in model.objects.filter(console=console)]
    for row in rows:
        row.console = console   # inputs_for/outputs_for read it; spare the query
    return rows


def cell_for(channel, index):
    index.register(_console_rows(channel))
    return index.cell_for(channel)


def slot_cell(cell, slot):
    """The part of a cell one Patch column shows: its A feeds or its B feeds."""
    return cell.only(slot) if cell is not None else None


def state_token(channel, cell, slot='A'):
    feeds = sorted((f.port.pk, f.how, f.slot, f.port.name)
                   for f in (cell.feeds if cell else ()) if f.slot == slot)
    raw = repr((channel_name(channel), slot, feeds))
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def current_feeds(channel, cell, slot='A'):
    """The channel's current patch in one slot: A feeds that are linked or
    by name, or its B feeds (always linked)."""
    return [f for f in (cell.feeds if cell else ())
            if f.how in (LINKED, BY_NAME) and f.slot == slot]


def port_lock(port):
    """Why ``port`` may not be patched or unpatched from the Console page, or
    None. Nothing is locked yet; a split port will be (see module docstring)."""
    return None


def _ports(channel, index):
    return index.inputs if is_input(channel) else index.outputs


# -- reading -----------------------------------------------------------------

def render_cell(channel, cell, editable, state=None, slot='A'):
    """One Patch cell: the channel's A feeds, or (``slot='B'``) its B feeds."""
    return render_to_string('admin/planner/console/_patch_cell.html', {
        'cell': slot_cell(cell, slot),
        'side': 'In' if is_input(channel) else 'Out',
        'slot': slot,
        'editable': editable,
        'edit_url': reverse('planner:console_patch', args=[kind_of(channel, slot), channel.pk]),
        'state': state if state is not None else state_token(channel, cell, slot),
        'channel_label': channel_label(channel) + (' (B)' if slot == 'B' else ''),
    })


def render_free_ports(index):
    return render_to_string('admin/planner/console/_patch_free_ports.html',
                            {'devices': index.free_ports()})


def _channel_ref(index, link, console_id):
    """'Ch 5', or 'MON Ch 5' for a channel on another console."""
    found = index.channel_labels.get(link[1]) if link else None
    if found is None:
        return 'a channel'
    cid, cname, label = found
    return label if cid == console_id else f'{cname} {label}'


def port_use(port, index, channel, slot):
    """What a port already carries, as the picker shows it, and whether
    ``slot`` may take it. (selectable, use text, same-port warning)."""
    console_id = channel.console_id
    if not is_input(channel):
        return port.free, port.name or ('(linked)' if port.link else ''), ''
    uses = []
    if slot == 'B':
        if port.link_b and port.link_b[1] == channel.pk:
            return False, 'here', ''
        if port.link_b:
            return False, 'B for ' + _channel_ref(index, port.link_b, console_id), ''
        warn = ''
        if port.link and port.link[1] == channel.pk:
            warn = 'same port as A'
            uses.append('A here')
        elif port.link:
            uses.append('A for ' + _channel_ref(index, port.link, console_id))
        if port.name:
            uses.append(port.name)
        return True, ' · '.join(uses), warn
    if port.link and port.link[1] == channel.pk:
        return False, 'here', ''
    if port.name:
        uses.append(port.name)
    elif port.link:
        uses.append('(linked)')
    if port.link_b:
        uses.append('B for ' + _channel_ref(index, port.link_b, console_id))
    return port.free, ' · '.join(uses), ''


def picker(channel, index, slot='A'):
    """Everything the panel shows for one channel slot, and the state to send back."""
    cell = cell_for(channel, index)
    state = state_token(channel, cell, slot)
    current = {f.port.pk for f in current_feeds(channel, cell, slot)}
    side = 'In' if is_input(channel) else 'Out'

    feeds = []
    for f in (cell.feeds if cell else ()):
        if f.slot != slot:
            continue
        lock = port_lock(f.port)
        feeds.append({
            'port': f.port.pk, 'device': f.port.device_name, 'number': f.port.number,
            'url': f.url, 'how': f.how, 'slot': f.slot, 'conflict': f.conflict,
            'others': list(f.others), 'lock': lock, 'same_port': f.same_port,
            'unsaved': f.unsaved, 'port_name': f.port.name, 'saved_name': f.saved_name,
            'can_unpatch': f.port.pk in current and not lock,
        })

    devices = {}
    for port in _ports(channel, index):
        d = devices.get(port.device_id)
        if d is None:
            d = devices[port.device_id] = {
                'id': port.device_id, 'name': port.device_name,
                'url': reverse('admin:planner_device_change', args=[port.device_id]),
                'free': 0, 'total': 0, 'ports': [],
            }
        lock = port_lock(port)
        selectable, use, warn = port_use(port, index, channel, slot)
        selectable = selectable and not lock and port.pk not in current
        d['total'] += 1
        d['free'] += selectable
        d['ports'].append({
            'id': port.pk, 'number': port.number, 'name': port.name, 'use': use,
            'free': selectable, 'linked': bool(port.link), 'warn': warn,
            'mine': port.pk in current, 'lock': lock,
        })

    return {
        'kind': kind_of(channel, slot),
        'slot': slot,
        'channel': {'id': channel.pk, 'label': channel_label(channel),
                    'name': channel_name(channel), 'console': channel.console.name},
        'side': side,
        'state': state,
        'feeds': feeds,
        'has_current': bool(current),
        'devices': sorted(devices.values(), key=lambda d: (d['name'].casefold(), d['id'])),
        'cell_html': render_cell(channel, cell, True, state, slot),
    }


# -- writing -----------------------------------------------------------------

NAME_MAX = DeviceInput._meta.get_field('signal_name').max_length


def _save(row, slot='A'):
    if slot == 'B':
        row.save(update_fields=['console_input_b'])
    elif isinstance(row, DeviceInput):
        row.save(update_fields=['signal_name', 'console_input'])
    else:
        row.save(update_fields=['signal_name', 'content_type', 'object_id'])


def _unlink(row, slot='A'):
    if slot == 'B':
        device_patch.link_input_port_b(row, None)
    elif isinstance(row, DeviceInput):
        device_patch.apply_input_link(row, '', None)
    else:
        device_patch.apply_output_link(row, '', None)
    _save(row, slot)


def _link(row, channel, name, slot='A'):
    if slot == 'B':
        device_patch.link_input_port_b(row, channel)
    elif isinstance(row, DeviceInput):
        device_patch.link_input_port(row, channel, name)
    else:
        device_patch.link_output_port(row, channel, name)
    _save(row, slot)


def apply(kind, channel_pk, project, *, action, port_pk, state, mode='', name=''):
    """Patch ``port_pk`` to the channel, or unpatch it. Atomic; raises
    PatchError (nothing written) when refused. ``name`` is the channel's name
    as typed on the page and not yet saved, if any (see above); a B patch
    ignores it -- B never writes a port's name."""
    slot = slot_of(kind)
    name = (name or '').strip()
    if len(name) > NAME_MAX:
        raise PatchError(400, 'name_too_long',
                         f'A port name is at most {NAME_MAX} characters.')
    with transaction.atomic():
        channel = load_channel(kind, channel_pk, project, lock=True)
        if channel is None:
            raise PatchError(404, 'channel_gone',
                             'This channel is no longer on this console. Reload the page.')
        rows_model = DeviceInput if is_input(channel) else DeviceOutput
        row = (rows_model.objects.select_for_update(of=('self',))
               .filter(pk=port_pk, device__project=project, device__kind='io').first())
        if row is None:
            raise PatchError(404, 'port_gone', 'That port is no longer in this project.')

        index = PortIndex(project.pk)
        cell = cell_for(channel, index)
        label = channel_label(channel) + (' (B)' if slot == 'B' else '')
        if state != state_token(channel, cell, slot):
            raise PatchError(409, 'stale', f'{label} changed since you opened it. '
                                           'Here is what it is now.')
        port = next(p for p in _ports(channel, index) if p.pk == row.pk)
        lock = port_lock(port)
        if lock:
            raise PatchError(409, 'locked', lock)
        current = current_feeds(channel, cell, slot)

        if action == 'unpatch':
            if port.pk not in {f.port.pk for f in current}:
                raise PatchError(409, 'stale', 'That port is not patched here any more.')
            _unlink(row, slot)
            return

        if action != 'patch':
            raise PatchError(400, 'bad_action', 'Unknown action.')
        if not port_use(port, index, channel, slot)[0]:
            raise PatchError(409, 'port_taken',
                             f'{port.device_name} {"In" if is_input(channel) else "Out"} '
                             f'{port.number} was patched since you opened this. Pick another.')
        if slot == 'B' and current and mode != REPLACE:
            raise PatchError(409, 'one_b', f'{label} already has a B source. A channel has '
                                           'one B source: Replace it, or unpatch it first.')
        if current and mode not in (REPLACE, ADD):
            raise PatchError(400, 'choose', 'Choose Replace or Add.')

        if mode == REPLACE and current:
            for f in current:
                if port_lock(f.port):
                    raise PatchError(409, 'locked', port_lock(f.port))
            old = (rows_model.objects.select_for_update(of=('self',))
                   .filter(pk__in=[f.port.pk for f in current], device__project=project))
            for old_row in old:
                _unlink(old_row, slot)
        if slot == 'B':
            # Any B left after the replace (a conflict that slipped through,
            # or a write that raced this one) refuses the patch.
            other = device_patch.b_taken(channel, exclude=[row.pk])
            if other is not None:
                raise PatchError(409, 'one_b', f'{label} is already B on {other.device.name}. '
                                               'A channel has one B source.')
        _link(row, channel, name or channel_name(channel), slot)


def response_payload(kind, channel_pk, project, channel=None):
    """Fresh cell, free ports and picker: for a read, after a write, or after
    a refused one. Pass ``channel`` when it is already loaded and current."""
    index = PortIndex(project.pk)
    if channel is None:
        channel = load_channel(kind, channel_pk, project)
    payload = {'free_html': render_free_ports(index)}
    if channel is not None:
        payload.update(picker(channel, index, slot_of(kind)))
    return payload
