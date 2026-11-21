"""What an amp channel's inputs can be linked to (wiring diagram, PR 2b-2).

The rack view's datalists are the picker. Each field lists every output that
can feed it, one entry per output, unique because it names the device:

  AVB      processor AVB outputs           "AVB 3 - L Main (SL P1)"
  AES      processor AES + I/O outputs     "L Main · SL P1 AES 3", "CENTER · Stage Box Out 3"
  Analog   processor analogue + I/O        "Fill · SR P1 Analog 2", "Stage Box Out 4"

Saving text that is exactly one entry links the input (a ``Connection``);
anything else links nothing and removes a link the input had. No fuzzy
matching. Two outputs that would read the same (two processors of one name)
are lengthened with their location, then their IP (``sources.disambiguate``),
so both stay pickable. The text is a copy: when a linked output, its
processor or its device is renamed, ``rewrite`` brings it back in line
(called through ``sources.changed``).
"""
from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from planner.connections import sources as S
from planner.connections.sources import Source
from planner.models import (AmpChannel, Connection, DeviceOutput, GalaxyOutput,
                            P1Output)

FIELDS = ('avb_stream', 'aes_input', 'analog_input')
FIELD_TRANSPORT = {'avb_stream': 'avb', 'aes_input': 'aes', 'analog_input': 'analog'}
TRANSPORT_FIELD = {t: f for f, t in FIELD_TRANSPORT.items()}
PROCESSOR_FIELD = {'AVB': 'avb_stream', 'AES': 'aes_input', 'ANALOG': 'analog_input'}
PROCESSOR_FIELD_TYPE = {f: t for t, f in PROCESSOR_FIELD.items()}
TYPE_WORD = {'AES': 'AES', 'ANALOG': 'Analog'}
SOURCE_MODELS = {'p1output': P1Output, 'galaxyoutput': GalaxyOutput,
                 'deviceoutput': DeviceOutput}


def processor_entry(field, processor, number, label):
    label = (label or '').strip()
    if field == 'avb_stream':
        return f'AVB {number} - {label} ({processor})' if label else f'AVB {number} ({processor})'
    port = f'{processor} {TYPE_WORD[PROCESSOR_FIELD_TYPE[field]]} {number}'
    return f'{label} · {port}' if label else port


def io_entry(device, position, signal):
    """I/O outputs are numbered by position, as the device page and the
    wiring diagram number them."""
    port = f'{device} Out {position}'
    signal = (signal or '').strip()
    return f'{signal} · {port}' if signal else port


def io_sources(project, fields):
    """Every I/O output of the project, once per field in ``fields``, keyed
    for ordering by device name then position."""
    rows = (DeviceOutput.objects
            .filter(device__project=project, output_number__isnull=False)
            .order_by('device_id', 'output_number', 'pk')
            .values_list('pk', 'device_id', 'device__name', 'signal_name',
                         'device__location__name', 'device__primary_ip_address'))
    out = []
    position = defaultdict(int)
    for pk, device_id, name, signal, location, ip in rows:
        position[device_id] += 1
        text = io_entry(name, position[device_id], signal)
        for field in fields:
            out.append(((name.casefold(), name, device_id, position[device_id], pk),
                        Source('deviceoutput', pk, field, text, name, ('device', device_id),
                               location or '', ip or '')))
    return out


def all_sources(project):
    """Every (output, field) pair of the project with its entry, in list order:
    processors by name then port, then I/O devices by name then position.
    Entries that would read the same are lengthened, or marked duplicates."""
    out = []
    for model, owner, prefix in ((P1Output, 'p1_processor', 'p1output'),
                                 (GalaxyOutput, 'galaxy_processor', 'galaxyoutput')):
        proc = f'{owner}__system_processor'
        rows = (model.objects
                .filter(**{f'{proc}__project': project})
                .values_list('pk', f'{proc}__name', 'output_type', 'channel_number', 'label',
                             f'{proc}_id', f'{proc}__location__name', f'{proc}__ip_address'))
        for pk, name, port_type, number, label, proc_id, location, ip in rows:
            field = PROCESSOR_FIELD.get(port_type)
            if field:
                out.append(((0, name.casefold(), name, FIELDS.index(field), number, pk),
                            Source(prefix, pk, field, processor_entry(field, name, number, label),
                                   name, ('processor', proc_id), location or '', ip or '')))
    out += [((1,) + key, source) for key, source in io_sources(project, ('aes_input', 'analog_input'))]
    out.sort(key=lambda item: item[0])
    return S.disambiguate([source for _, source in out])


def _max_length(field):
    return AmpChannel._meta.get_field(field).max_length


def picker(project, sources=None):
    """{field: {entry text: Source}}, every entry naming exactly one output
    and short enough to store, in list order."""
    sources = all_sources(project) if sources is None else sources
    entries = S.picker(sources, _max_length)
    return {field: entries.get(field, {}) for field in FIELDS}


def listing(sources):
    """{field: [entry text]} for the rack view's datalists: every entry once,
    duplicates included (they link nothing, but nothing vanishes)."""
    return {field: [s.text for s in S.listing(sources, field, _max_length(field))]
            for field in FIELDS}


def _ct(model):
    return ContentType.objects.get_for_model(model)


def links_for(channels):
    """{(channel pk, field): Connection} for these amp channels."""
    rows = (Connection.objects.filter(to_ct=_ct(AmpChannel), to_id__in=[c.pk for c in channels])
            .select_related('from_ct'))
    return {(c.to_id, TRANSPORT_FIELD[c.transport]): c for c in rows
            if c.transport in TRANSPORT_FIELD}


def link_from_text(channel, field, entries=None):
    """After ``field`` of ``channel`` is saved: link it when its text is
    exactly one entry, else remove any link it had. Returns the Connection
    or None."""
    transport = FIELD_TRANSPORT[field]
    project = channel.amp.project
    entries = picker(project) if entries is None else entries
    source = entries[field].get(getattr(channel, field) or '')
    existing = Connection.objects.filter(to_ct=_ct(AmpChannel), to_id=channel.pk,
                                         transport=transport)
    if source is None:
        existing.delete()
        return None
    with transaction.atomic():
        conn = existing.select_for_update().first() or Connection(
            project=project, to_ct=_ct(AmpChannel), to_id=channel.pk, transport=transport)
        conn.from_ct = _ct(SOURCE_MODELS[source.model])
        conn.from_id = source.pk
        conn.save()
    return conn


def unlink(channel, field):
    """Remove the input's link and keep its text."""
    Connection.objects.filter(to_ct=_ct(AmpChannel), to_id=channel.pk,
                              transport=FIELD_TRANSPORT[field]).delete()


def rewrite(project, rows):
    """Bring linked amp inputs' text in line with their source's entry.
    ``rows``: the project's Connections as (from ct, from id, to ct, to id,
    transport). Returns how many fields changed."""
    amp_ct = _ct(AmpChannel).pk
    rows = [r for r in rows if r[2] == amp_ct and r[4] in TRANSPORT_FIELD]
    if not rows:
        return 0
    text = {(_ct(SOURCE_MODELS[s.model]).pk, s.pk, s.field): s.text
            for s in all_sources(project)}
    current = {pk: dict(zip(FIELDS, vals)) for pk, *vals in AmpChannel.objects.filter(
        pk__in={r[3] for r in rows}).values_list('pk', *FIELDS)}
    changed = 0
    for from_ct, from_id, _, to_id, transport in rows:
        field = TRANSPORT_FIELD[transport]
        new = text.get((from_ct, from_id, field))
        if new is None or to_id not in current:
            continue
        new = new[:_max_length(field)]
        if current[to_id][field] != new:
            changed += AmpChannel.objects.filter(pk=to_id).update(**{field: new})
    return changed
