"""What a connection can start or end at, and how each end is named.

Two kinds of end:

  device   a box on the diagram: Console, I/O Device, System Processor, Amp,
           Speaker Array. Its node id is ``<kind>:<pk>``.
  port     one row on a device: an I/O input/output, a console channel or bus,
           a processor input/output, an amp channel. A port is drawn on the
           node of the device it belongs to; its ref is ``<model>:<pk>`` and
           its label is how that device's own page names it ("In 3", "Mtx 2",
           "AES 1", "Ch 4").

The graph also uses synthetic nodes that no device model backs:
``amp_rack`` (``amp_rack:unlinked``, one per project: the amp end of every PA
cable run with no Amp linked; ``amp_rack:text:<text>``: a run whose
Destination says "amp rack" but names no Amp Location), ``amp_location`` (an
Amp Location a run leaves from, or that an old run's Destination names),
``destination`` (``destination:<text>``: where a run entered from an amp or
rack goes, as typed -- a speaker or a fan-out, shared by runs naming the same
place) and ``unlinked`` (text that names no device, or names more than one).

Plain functions and constants only: no queries. The loaders in
``matchers.ProjectIndex`` fetch the rows; this module names them.
"""
from dataclasses import dataclass

# Device kinds -> node id prefix. The prefix is also the node's ``kind``.
CONSOLE = 'console'
DEVICE = 'device'
PROCESSOR = 'processor'
AMP = 'amp'
ARRAY = 'speaker_array'
AMP_LOCATION = 'amp_location'   # an amp's location dict carries this kind
AMP_RACK = 'amp_rack'
AMP_RACK_UNLINKED = 'amp_rack:unlinked'
AMP_RACK_UNLINKED_LABEL = 'Amp rack \u2014 not linked'
SPEAKER_UNNAMED_LABEL = 'Speaker \u2014 not named'
DESTINATION = 'destination'
UNLINKED = 'unlinked'

DEVICE_KINDS = (CONSOLE, DEVICE, PROCESSOR, AMP, ARRAY)

# Port models -> the device kind they are drawn on. The key is the ref prefix.
PORT_OWNERS = {
    'deviceinput': DEVICE,
    'deviceoutput': DEVICE,
    'consoleinput': CONSOLE,
    'consoleauxoutput': CONSOLE,
    'consolematrixoutput': CONSOLE,
    'consolestereooutput': CONSOLE,
    'p1input': PROCESSOR,
    'p1output': PROCESSOR,
    'galaxyinput': PROCESSOR,
    'galaxyoutput': PROCESSOR,
    'ampchannel': AMP,
}

# Processor port types as the models store them -> transport and label text.
PROCESSOR_TYPES = {'ANALOG': 'analog', 'AES': 'aes', 'AVB': 'avb'}
PROCESSOR_TYPE_LABELS = {'ANALOG': 'Analog', 'AES': 'AES', 'AVB': 'AVB'}


def node_id(kind, pk):
    return f'{kind}:{pk}'


def port_ref(model, pk):
    return f'{model}:{pk}'


@dataclass(frozen=True)
class PortLabel:
    """"In 3" as (prefix 'In', number 3); "St L" as ('St', 'L').

    Kept apart so the graph can compress a run of ports into "In 1–15"."""
    prefix: str
    number: object  # int where the port is numbered, else the text

    def __str__(self):
        return f'{self.prefix} {self.number}'


def _as_number(value):
    text = str(value).strip() if value is not None else ''
    return int(text) if text.isdigit() else text


def io_input_label(position):
    """I/O ports are numbered by position on the device, as its page does
    (``utils/console_patch._ports``), not by the stored input_number."""
    return PortLabel('In', position)


def io_output_label(position):
    return PortLabel('Out', position)


def console_input_label(input_ch, dante_number, pk):
    return PortLabel('Ch', _as_number(input_ch or dante_number or pk))


def aux_label(aux_number):
    return PortLabel('Aux', _as_number(aux_number))


def matrix_label(matrix_number):
    return PortLabel('Mtx', _as_number(matrix_number))


def stereo_label(stereo_type):
    return PortLabel('St', stereo_type)


def processor_port_label(port_type, channel_number):
    return PortLabel(PROCESSOR_TYPE_LABELS.get(port_type, port_type), channel_number)


def amp_channel_label(channel_number):
    return PortLabel('Ch', channel_number)
