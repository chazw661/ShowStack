"""One set of rules for linking an I/O device port to a console channel.

A port carries two things: ``signal_name`` (text, always shown) and a link to
the console channel it feeds -- ``DeviceInput.console_input`` for inputs, the
``content_type``/``object_id`` generic link for outputs, which can point at an
Aux, a Matrix or a Stereo bus and nothing else.

The rules, in one place so the I/O device page, the backfill command and any
later "patch from the console page" all agree:

  * Picking a console channel sets the link AND the name.
  * A free-typed name leaves the link empty.
  * Clearing the name clears both.
  * A linked port keeps its link only while its name still IS the channel's
    name. A name edited to something else is a free-typed name.
  * Renaming the channel moves the port's name with it (planner/signals.py),
    so the link holds and every reader of ``signal_name`` shows the current
    channel name -- including blank -> a name. Saving the Console page also
    runs ``sync_port_names``, which covers what the rename cannot see.
  * Patching from the Console page (``link_input_port`` / ``link_output_port``)
    links the port whatever the channel's name, even none: the port takes the
    name the engineer sees on that page, saved or not, and a blank one is
    filled when the channel is named and saved. A linked port with a blank name
    is still used, not free.

A link is written as a short reference string -- ``in:<pk>``, ``aux:<pk>``,
``mtx:<pk>``, ``st:<pk>`` -- which is what the combobox carries in a hidden field. It is
always resolved inside one project: a reference to another project's channel,
or to a channel deleted since the page loaded, resolves to nothing and the port
keeps its name without a link. It never raises, because the hidden field is
not something the engineer can see or correct.
"""

from django.contrib.contenttypes.models import ContentType

from planner.models import (
    ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput, ConsoleStereoOutput,
    DeviceInput, DeviceOutput,
)

INPUT_PREFIX = 'in'
OUTPUT_MODELS = {'aux': ConsoleAuxOutput, 'mtx': ConsoleMatrixOutput,
                 'st': ConsoleStereoOutput}


def norm(name):
    """Comparison key for a signal name: trimmed, case-insensitive."""
    return (name or '').strip().casefold()


def input_ref(console_input_id):
    return f'{INPUT_PREFIX}:{console_input_id}' if console_input_id else ''


def output_ref(model, pk):
    """``aux:12`` / ``mtx:3`` / ``st:7`` for a linkable bus; '' for anything
    else."""
    for prefix, linked in OUTPUT_MODELS.items():
        if model is linked:
            return f'{prefix}:{pk}' if pk else ''
    return ''


def output_ref_for(device_output):
    """The reference a DeviceOutput's stored generic link corresponds to."""
    if not (device_output.content_type_id and device_output.object_id):
        return ''
    model = ContentType.objects.get_for_id(device_output.content_type_id).model_class()
    return output_ref(model, device_output.object_id)


def _split(ref):
    prefix, _, pk = (ref or '').partition(':')
    return prefix, int(pk) if pk.isdigit() else None


def resolve_input_ref(ref, project_id):
    """The project's ConsoleInput a reference names, or None."""
    prefix, pk = _split(ref)
    if prefix != INPUT_PREFIX or pk is None or not project_id:
        return None
    return (ConsoleInput.objects
            .filter(pk=pk, console__project_id=project_id)
            .first())


def resolve_output_ref(ref, project_id):
    """The project's Aux/Matrix/Stereo bus a reference names, or None."""
    prefix, pk = _split(ref)
    model = OUTPUT_MODELS.get(prefix)
    if model is None or pk is None or not project_id:
        return None
    return model.objects.filter(pk=pk, console__project_id=project_id).first()


def name_not_saved(port_name, channel_name):
    """Is a LINKED port named something other than its channel's saved name?

    Normally impossible -- a channel's save moves its name onto its ports --
    so it means the port was patched from the Console page with a name typed
    there and the page was never saved (or the channel was since saved blank).
    A blank port name is not a mismatch: it is waiting for the channel's name.
    The Console page's Patch cell and the I/O device page both flag it.
    """
    return bool(norm(port_name)) and norm(port_name) != norm(channel_name)


def sync_port_names(console):
    """After the Console page is saved: every port linked to one of its
    channels takes that channel's saved name, blank included.

    The rename signal (planner/signals.py) only runs for a row that was saved,
    and Django saves only rows that changed. A port patched with a name typed
    on the page (``link_input_port``) whose row was then typed back to its
    saved name -- or, unnamed, cleared again -- has no changed row, so nothing
    else would ever correct it, and its cell would say "name not saved" for
    good. Only ports ``name_not_saved`` flags are written. Returns how many.
    """
    fixed = 0

    def write(model, targets):
        nonlocal fixed
        by_name = {}
        for pk, name in targets:
            by_name.setdefault(name, []).append(pk)
        for name, pks in by_name.items():
            fixed += model.objects.filter(pk__in=pks).update(signal_name=name)

    write(DeviceInput, [
        (pk, (source or '').strip())
        for pk, name, source in DeviceInput.objects
        .filter(console_input__console=console)
        .values_list('pk', 'signal_name', 'console_input__source')
        if name_not_saved(name, source)])

    for model in OUTPUT_MODELS.values():
        names = dict(model.objects.filter(console=console).values_list('pk', 'name'))
        if not names:
            continue
        write(DeviceOutput, [
            (pk, (names[object_id] or '').strip())
            for pk, name, object_id in DeviceOutput.objects
            .filter(content_type=ContentType.objects.get_for_model(model),
                    object_id__in=names)
            .values_list('pk', 'signal_name', 'object_id')
            if name_not_saved(name, names[object_id])])
    return fixed


def link_holds(posted_name, channel_name, initial_name):
    """Does a posted name keep its link?

    Yes when it is the linked channel's current name, or when the engineer did
    not touch the field (which covers a channel renamed to blank: the port
    shows its last name, and leaving it alone must not silently unlink it).
    A blank name holds only when it was blank already (a port patched to an
    unnamed channel, left alone); clearing a name clears both.
    """
    if not norm(posted_name):
        return not norm(initial_name)
    return norm(posted_name) in {norm(channel_name), norm(initial_name)} - {''}


def apply_input_link(device_input, posted_name, channel, initial_name=''):
    """Set ``device_input``'s name and link from one combobox submission.

    ``channel`` is the resolved ConsoleInput the hidden field named (or None).
    Does not save.
    """
    name = (posted_name or '').strip()
    if channel is not None and link_holds(name, channel.source, initial_name):
        device_input.console_input = channel
        device_input.signal_name = (channel.source or '').strip() or name
    else:
        device_input.console_input = None
        device_input.signal_name = name


def link_input_port(device_input, channel, name=''):
    """Link ``device_input`` to ``channel`` from the Console page. ``name`` is
    the channel's name as that page shows it (typed and not yet saved, or
    saved) and may be blank. Does not save."""
    device_input.console_input = channel
    device_input.signal_name = (name or '').strip()


def link_output_port(device_output, bus, name=''):
    """Output counterpart of ``link_input_port``. Does not save."""
    device_output.content_type = ContentType.objects.get_for_model(type(bus))
    device_output.object_id = bus.pk
    device_output.signal_name = (name or '').strip()


def apply_output_link(device_output, posted_name, bus, initial_name=''):
    """Output counterpart of ``apply_input_link``; ``bus`` is a resolved
    ConsoleAuxOutput/ConsoleMatrixOutput/ConsoleStereoOutput or None. Does not save."""
    name = (posted_name or '').strip()
    if bus is not None and link_holds(name, bus.name, initial_name):
        device_output.content_type = ContentType.objects.get_for_model(type(bus))
        device_output.object_id = bus.pk
        device_output.signal_name = (bus.name or '').strip() or name
    else:
        device_output.content_type = None
        device_output.object_id = None
        device_output.signal_name = name
