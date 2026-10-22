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

  * Inputs: the A source only. A link has no A/B; the B feed stays name-based
    (a port named after the channel's Source (B)), shown but not editable here.
  * Outputs: Aux, Matrix and Stereo.
  * Only I/O devices in the console's project, and only FREE ports (no name,
    no link -- ``Port.free``; a linked port with a blank name is used). A used
    port is shown with its name, dimmed.

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


def kind_of(channel):
    for kind, model in KINDS.items():
        if isinstance(channel, model):
            return kind
    raise ValueError(channel)


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


def state_token(channel, cell):
    feeds = sorted((f.port.pk, f.how, f.slot, f.port.name) for f in (cell.feeds if cell else ()))
    raw = repr((channel_name(channel), feeds))
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def current_feeds(channel, cell):
    """The channel's current patch: A feeds that are linked or by name."""
    return [f for f in (cell.feeds if cell else ())
            if f.how in (LINKED, BY_NAME) and (f.slot == 'A' or not is_input(channel))]


def port_lock(port):
    """Why ``port`` may not be patched or unpatched from the Console page, or
    None. Nothing is locked yet; a split port will be (see module docstring)."""
    return None


def _ports(channel, index):
    return index.inputs if is_input(channel) else index.outputs


# -- reading -----------------------------------------------------------------

def render_cell(channel, cell, editable, state=None):
    return render_to_string('admin/planner/console/_patch_cell.html', {
        'cell': cell,
        'side': 'In' if is_input(channel) else 'Out',
        'editable': editable,
        'edit_url': reverse('planner:console_patch', args=[kind_of(channel), channel.pk]),
        'state': state if state is not None else state_token(channel, cell),
        'channel_label': channel_label(channel),
    })


def render_free_ports(index):
    return render_to_string('admin/planner/console/_patch_free_ports.html',
                            {'devices': index.free_ports()})


def picker(channel, index):
    """Everything the panel shows for one channel, and the state to send back."""
    cell = cell_for(channel, index)
    state = state_token(channel, cell)
    current = {f.port.pk for f in current_feeds(channel, cell)}
    side = 'In' if is_input(channel) else 'Out'

    feeds = []
    for f in (cell.feeds if cell else ()):
        lock = port_lock(f.port)
        feeds.append({
            'port': f.port.pk, 'device': f.port.device_name, 'number': f.port.number,
            'url': f.url, 'how': f.how, 'slot': f.slot, 'conflict': f.conflict,
            'others': list(f.others), 'lock': lock,
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
        d['total'] += 1
        d['free'] += port.free and not lock
        d['ports'].append({
            'id': port.pk, 'number': port.number, 'name': port.name,
            'free': port.free and not lock, 'linked': bool(port.link),
            'mine': port.pk in current, 'lock': lock,
        })

    return {
        'kind': kind_of(channel),
        'channel': {'id': channel.pk, 'label': channel_label(channel),
                    'name': channel_name(channel), 'console': channel.console.name},
        'side': side,
        'state': state,
        'feeds': feeds,
        'has_current': bool(current),
        'devices': sorted(devices.values(), key=lambda d: (d['name'].casefold(), d['id'])),
        'cell_html': render_cell(channel, cell, True, state),
    }


# -- writing -----------------------------------------------------------------

NAME_MAX = DeviceInput._meta.get_field('signal_name').max_length


def _save(row):
    if isinstance(row, DeviceInput):
        row.save(update_fields=['signal_name', 'console_input'])
    else:
        row.save(update_fields=['signal_name', 'content_type', 'object_id'])


def _unlink(row):
    if isinstance(row, DeviceInput):
        device_patch.apply_input_link(row, '', None)
    else:
        device_patch.apply_output_link(row, '', None)
    _save(row)


def _link(row, channel, name):
    if isinstance(row, DeviceInput):
        device_patch.link_input_port(row, channel, name)
    else:
        device_patch.link_output_port(row, channel, name)
    _save(row)


def apply(kind, channel_pk, project, *, action, port_pk, state, mode='', name=''):
    """Patch ``port_pk`` to the channel, or unpatch it. Atomic; raises
    PatchError (nothing written) when refused. ``name`` is the channel's name
    as typed on the page and not yet saved, if any (see above)."""
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
               .filter(pk=port_pk, device__project=project).first())
        if row is None:
            raise PatchError(404, 'port_gone', 'That port is no longer in this project.')

        index = PortIndex(project.pk)
        cell = cell_for(channel, index)
        if state != state_token(channel, cell):
            raise PatchError(409, 'stale', f'{channel_label(channel)} changed since you opened it. '
                                           'Here is what it is now.')
        port = next(p for p in _ports(channel, index) if p.pk == row.pk)
        lock = port_lock(port)
        if lock:
            raise PatchError(409, 'locked', lock)
        current = current_feeds(channel, cell)

        if action == 'unpatch':
            if port.pk not in {f.port.pk for f in current}:
                raise PatchError(409, 'stale', 'That port is not patched here any more.')
            _unlink(row)
            return

        if action != 'patch':
            raise PatchError(400, 'bad_action', 'Unknown action.')
        if not port.free:
            raise PatchError(409, 'port_taken',
                             f'{port.device_name} {"In" if is_input(channel) else "Out"} '
                             f'{port.number} was patched since you opened this. Pick another.')
        if current and mode not in (REPLACE, ADD):
            raise PatchError(400, 'choose', 'Choose Replace or Add.')

        if mode == REPLACE and current:
            for f in current:
                if port_lock(f.port):
                    raise PatchError(409, 'locked', port_lock(f.port))
            old = (rows_model.objects.select_for_update(of=('self',))
                   .filter(pk__in=[f.port.pk for f in current], device__project=project))
            for old_row in old:
                _unlink(old_row)
        _link(row, channel, name or channel_name(channel))


def response_payload(kind, channel_pk, project, channel=None):
    """Fresh cell, free ports and picker: for a read, after a write, or after
    a refused one. Pass ``channel`` when it is already loaded and current."""
    index = PortIndex(project.pk)
    if channel is None:
        channel = load_channel(kind, channel_pk, project)
    payload = {'free_html': render_free_ports(index)}
    if channel is not None:
        payload.update(picker(channel, index))
    return payload
