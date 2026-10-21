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
    channel name.

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


def link_holds(posted_name, channel_name, initial_name):
    """Does a posted name keep its link?

    Yes when it is the linked channel's current name, or when the engineer did
    not touch the field (which covers a channel renamed to blank: the port
    shows its last name, and leaving it alone must not silently unlink it).
    A blank name never holds -- clearing the field clears both.
    """
    if not norm(posted_name):
        return False
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
