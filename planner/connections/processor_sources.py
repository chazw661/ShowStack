"""What a P1 / Galaxy AES or Analog input can be linked to (wiring diagram, PR 2b-3).

The processor page's datalist is the picker: every output of every I/O device
in the project, then every console Aux / Matrix / Stereo output, one entry
each, naming its device or console:

  "Left · Y001 Out 17"     (unnamed: "Y001 Out 17")
  "Lobby · FOH PM5 Mtx 3"  (unnamed: "FOH PM5 Mtx 3")

Same rules as the amp pickers (``amp_sources``): saved text that is exactly
one entry links the input (a ``Connection`` whose transport is the input's
own type, aes or analog); anything else links nothing and removes a link it
had. Entries that would read the same are lengthened (``sources``). AVB
inputs are network streams and are never linked here.
"""
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from planner.connections import endpoints as ep
from planner.connections import sources as S
from planner.connections.amp_sources import io_sources
from planner.connections.sources import Source
from planner.models import (Connection, ConsoleAuxOutput, ConsoleMatrixOutput,
                            ConsoleStereoOutput, DeviceOutput, GalaxyInput, P1Input)

INPUT_TRANSPORT = {'AES': 'aes', 'ANALOG': 'analog'}
TARGET_MODELS = {'p1input': P1Input, 'galaxyinput': GalaxyInput}
BUS_MODELS = (
    (ConsoleAuxOutput, 'consoleauxoutput', 'aux_number', ep.aux_label),
    (ConsoleMatrixOutput, 'consolematrixoutput', 'matrix_number', ep.matrix_label),
    (ConsoleStereoOutput, 'consolestereooutput', 'stereo_type', ep.stereo_label),
)
SOURCE_MODELS = {'deviceoutput': DeviceOutput,
                 **{prefix: model for model, prefix, _, _ in BUS_MODELS}}
STEREO_ORDER = {'L': 0, 'R': 1, 'M': 2}
MAX_LENGTH = min(m._meta.get_field('label').max_length for m in TARGET_MODELS.values())


def console_entry(console, port, name):
    port = f'{console} {port}'
    name = (name or '').strip()
    return f'{name} · {port}' if name else port


def _bus_order(number):
    number = ep._as_number(number)
    if isinstance(number, int):
        return (0, number, '')
    return (1, STEREO_ORDER.get(number, 9), str(number))


def all_sources(project):
    """Every output that can feed a processor input, in list order: I/O
    devices by name then position, then consoles by name, aux, matrix,
    stereo. Entries that would read the same are lengthened."""
    out = [((0,) + key, source) for key, source in io_sources(project, ('',))]
    for kind, (model, prefix, number_field, label) in enumerate(BUS_MODELS):
        rows = (model.objects
                .filter(console__project=project, console__is_template=False)
                .values_list('pk', 'console_id', 'console__name', number_field, 'name',
                             'console__location__name', 'console__primary_ip_address'))
        for pk, console_id, console, number, name, location, ip in rows:
            text = console_entry(console, label(number), name)
            out.append(((1, console.casefold(), console, console_id, kind, _bus_order(number), pk),
                        Source(prefix, pk, '', text, console, ('console', console_id),
                               location or '', ip or '')))
    out.sort(key=lambda item: item[0])
    return S.disambiguate([source for _, source in out])


def picker(project, sources=None):
    """{entry text: Source}: every entry naming exactly one output."""
    sources = all_sources(project) if sources is None else sources
    return S.picker(sources, lambda field: MAX_LENGTH).get('', {})


def listing(sources):
    """The datalist's entries, duplicates included (they link nothing)."""
    return S.listing(sources, '', MAX_LENGTH)


def _ct(model):
    return ContentType.objects.get_for_model(model)


def owner_project(processor_input):
    if isinstance(processor_input, P1Input):
        return processor_input.p1_processor.system_processor.project
    return processor_input.galaxy_processor.system_processor.project


def links_for(inputs):
    """{(model name, input pk): Connection} for these processor inputs."""
    pks = {}
    for i in inputs:
        pks.setdefault(type(i), []).append(i.pk)
    out = {}
    for model, ids in pks.items():
        for c in (Connection.objects.filter(to_ct=_ct(model), to_id__in=ids)
                  .select_related('from_ct')):
            out[(model._meta.model_name, c.to_id)] = c
    return out


def link_from_text(processor_input, entries=None):
    """After an input's label is saved: link it when its text is exactly one
    entry, else remove any link it had. Returns the Connection or None."""
    transport = INPUT_TRANSPORT.get(processor_input.input_type)
    if transport is None:
        return None
    project = owner_project(processor_input)
    entries = picker(project) if entries is None else entries
    source = entries.get(processor_input.label or '')
    to_ct = _ct(type(processor_input))
    existing = Connection.objects.filter(to_ct=to_ct, to_id=processor_input.pk)
    if source is None:
        existing.delete()
        return None
    with transaction.atomic():
        conn = existing.select_for_update().first() or Connection(
            project=project, to_ct=to_ct, to_id=processor_input.pk)
        conn.transport = transport
        conn.from_ct = _ct(SOURCE_MODELS[source.model])
        conn.from_id = source.pk
        conn.save()
    return conn


def unlink(processor_input):
    """Remove the input's link and keep its text."""
    Connection.objects.filter(to_ct=_ct(type(processor_input)), to_id=processor_input.pk).delete()


def rewrite(project, rows):
    """Bring linked processor inputs' text in line with their source's entry.
    ``rows`` as for ``amp_sources.rewrite``. Returns how many changed."""
    targets = {_ct(model).pk: model for model in TARGET_MODELS.values()}
    rows = [r for r in rows if r[2] in targets]
    if not rows:
        return 0
    text = {(_ct(SOURCE_MODELS[s.model]).pk, s.pk): s.text for s in all_sources(project)}
    changed = 0
    for ct_id, model in targets.items():
        mine = [r for r in rows if r[2] == ct_id]
        if not mine:
            continue
        current = dict(model.objects.filter(pk__in={r[3] for r in mine})
                       .values_list('pk', 'label'))
        for from_ct, from_id, _, to_id, _ in mine:
            new = text.get((from_ct, from_id))
            if new is not None and to_id in current and current[to_id] != new[:MAX_LENGTH]:
                changed += model.objects.filter(pk=to_id).update(label=new[:MAX_LENGTH])
    return changed
