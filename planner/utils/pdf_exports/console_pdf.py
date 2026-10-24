# planner/utils/pdf_exports/console_pdf.py
"""
Console PDF Export - professional PDF generation for Console configurations.

Restyled to use the shared report_kit toolkit (navy palette, banded tables,
"Page X of Y" footer, orphan-free page breaks).

What it prints matches the Console page:

* Channels in the page's order (planner/utils/console_order.py): numbered
  channels as numbers -- 1, 2, ... 144, not 1, 10, 100 -- then "ST 7" and
  other labels.
* A Patch column: the I/O device port feeding each input, or fed by each
  output, with the page's linked / by name / ambiguous / conflict rules
  (planner/utils/console_patch.py) and the same captions.
* Source Hardware, always, so an empty column still says nothing is set.

A channel nobody has used is left out: an input with no source (A or B), no
source hardware, nothing in Group / DCA / Mute / Direct Out / Omni In and no
patch; an output with no name, destination, omni and no patch. A channel
number, Dante number or colour alone does not count -- every console has 144
numbered inputs.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer

from planner.utils.console_order import by_channel_number
from planner.utils.console_patch import PortIndex, feed_label
from planner.utils.pdf_exports import report_kit as kit

# Header -> width (inches) before scaling to the page. The order is the
# column order.
INPUT_COLUMNS = {
    'Dante #': 0.5, 'Input Ch': 0.55, 'Source': 1.4, 'Source (B)': 1.0,
    'Src Hardware': 0.95, 'Src Hardware (B)': 0.85, 'Patch': 1.9,
    'Group': 0.6, 'DCA': 0.55, 'Mute': 0.55, 'Direct Out': 0.65, 'Omni In': 0.6,
}
AUX_COLUMNS = {
    'Dante #': 0.6, 'Aux': 0.5, 'Name': 2.2, 'Patch': 2.4, 'Mono/Stereo': 1.0,
    'Bus Type': 0.8, 'Omni In': 0.9, 'Omni Out': 0.9,
}
MATRIX_COLUMNS = {
    'Dante #': 0.6, 'Matrix': 0.55, 'Name': 2.2, 'Patch': 2.4, 'Mono/Stereo': 1.0,
    'Destination': 1.4, 'Omni Out': 0.9,
}
STEREO_COLUMNS = {
    'Dante #': 0.6, 'Buss': 1.1, 'Name': 2.6, 'Patch': 2.6, 'Omni Out': 1.0,
}
# Printed even when every row is blank.
ALWAYS = {'Source', 'Src Hardware', 'Patch'}
# Free text: wraps inside its column instead of running into the next.
WRAP = {'Source', 'Source (B)', 'Src Hardware', 'Src Hardware (B)', 'Patch',
        'Name', 'Destination', 'Group', 'DCA', 'Mute', 'Direct Out',
        'Omni In', 'Omni Out'}

_CELL = ParagraphStyle('ConsoleCell', fontName='Helvetica', fontSize=8,
                       leading=9.5, textColor=kit.INK)
_MUTED = kit.MUTED.hexval()[2:]
_AMBER = 'b26a00'


def _s(value):
    return '' if value is None else str(value).strip()


def _patch(cell, side):
    """A Patch cell as text: one feed per line, as feed_label writes it."""
    return '\n'.join(feed_label(f, side) for f in cell.feeds) if cell else ''


def _section(title, columns, rows):
    return {'title': title, 'headers': list(columns),
            'widths': [w * inch for w in columns.values()], 'rows': rows}


def console_sections(console):
    """The PDF's tables as plain text, in page order, unused channels left out.

    [{'title', 'headers', 'widths', 'rows'}]; rows are lists of str. Kept
    apart from the drawing so a test can read exactly what is printed.
    """
    inputs = list(by_channel_number(console.consoleinput_set.all(), 'input_ch'))
    auxes = list(by_channel_number(console.consoleauxoutput_set.all(), 'aux_number'))
    matrices = list(by_channel_number(console.consolematrixoutput_set.all(),
                                      'matrix_number'))
    stereos = list(console.consolestereooutput_set.order_by('stereo_type', 'pk'))

    in_cells, out_cells = {}, {}
    if console.project_id:
        index = PortIndex(console.project_id)
        in_cells = index.inputs_for(inputs)
        out_cells = index.outputs_for(auxes + matrices + stereos)

    def out_patch(bus):
        return _patch(out_cells.get((type(bus), bus.pk)), 'Out')

    sections = []

    rows = []
    for inp in inputs:
        patch = _patch(in_cells.get(inp.pk), 'In')
        used = [inp.source, inp.source_b, inp.source_hardware, inp.source_hardware_b,
                inp.group, inp.dca, inp.mute, inp.direct_out, inp.omni_in, patch]
        if not any(_s(v) for v in used):
            continue
        rows.append([_s(inp.dante_number), _s(inp.input_ch), _s(inp.source),
                     _s(inp.source_b), _s(inp.source_hardware),
                     _s(inp.source_hardware_b), patch, _s(inp.group), _s(inp.dca),
                     _s(inp.mute), _s(inp.direct_out), _s(inp.omni_in)])
    sections.append(_section('Console Inputs', INPUT_COLUMNS, rows))

    rows = []
    for aux in auxes:
        patch = out_patch(aux)
        if not any(_s(v) for v in (aux.name, aux.omni_in, aux.omni_out, patch)):
            continue
        rows.append([_s(aux.dante_number), _s(aux.aux_number), _s(aux.name), patch,
                     _s(aux.mono_stereo), _s(aux.bus_type), _s(aux.omni_in),
                     _s(aux.omni_out)])
    sections.append(_section('Aux Outputs', AUX_COLUMNS, rows))

    rows = []
    for mtx in matrices:
        patch = out_patch(mtx)
        if not any(_s(v) for v in (mtx.name, mtx.destination, mtx.omni_out, patch)):
            continue
        rows.append([_s(mtx.dante_number), _s(mtx.matrix_number), _s(mtx.name), patch,
                     _s(mtx.mono_stereo), _s(mtx.destination), _s(mtx.omni_out)])
    sections.append(_section('Matrix Outputs', MATRIX_COLUMNS, rows))

    rows = []
    for st in stereos:
        patch = out_patch(st)
        if not any(_s(v) for v in (st.name, st.omni_out, patch)):
            continue
        rows.append([_s(st.dante_number),
                     st.get_stereo_type_display() if st.stereo_type else '',
                     _s(st.name), patch, _s(st.omni_out)])
    sections.append(_section('Stereo Outputs', STEREO_COLUMNS, rows))

    return sections


def _patch_markup(text):
    """Patch text -> Paragraph markup: captions muted, a conflict amber."""
    lines = []
    for line in text.split('\n'):
        port, sep, caption = line.partition(' — ')
        markup = escape(port)
        if sep:
            markup += f' <font color="#{_MUTED}">— {escape(caption)}</font>'
        if line.endswith(' — CONFLICT'):
            markup = f'<font color="#{_AMBER}"><b>{escape(line)}</b></font>'
        lines.append(markup)
    return '<br/>'.join(lines)


def _fit(headers, widths, avail):
    """Widths that fill the page: too wide, everything shrinks; narrower
    (optional columns pruned), the text columns share what is left."""
    total = sum(widths)
    if total >= avail:
        return [w * avail / total for w in widths]
    text = sum(w for h, w in zip(headers, widths) if h in WRAP)
    if not text:
        return widths
    return [w + (avail - total) * w / text if h in WRAP else w
            for h, w in zip(headers, widths)]


def export_console_pdf(console):
    """
    Generate a comprehensive PDF export for a Console.

    Args:
        console: Console model instance

    Returns:
        HttpResponse with PDF content
    """
    S = kit.styles()
    page = kit.LANDSCAPE_PAGE
    project_name = console.project.name if getattr(console, 'project', None) else ''

    story = []

    # Module title header
    subtitle = console.name
    if project_name:
        subtitle = f"{console.name} &nbsp;&bull;&nbsp; {project_name}"
    story += kit.title_header("Console Configuration", subtitle, page, S)

    section_no = 0
    for section in console_sections(console):
        data = section['rows']
        if not data:
            continue
        keep = [i for i, h in enumerate(section['headers']) if h in ALWAYS]
        headers, data, col_widths = kit.prune_empty_columns(
            section['headers'], data, section['widths'], keep=keep)
        # The frame pads 6 pt a side inside the margins.
        col_widths = _fit(headers, col_widths, kit.usable_width(page) - 12)
        data = [[Paragraph(_patch_markup(v) if h == 'Patch' else escape(v), _CELL)
                 if h in WRAP and v else v
                 for h, v in zip(headers, row)] for row in data]
        section_no += 1
        if section_no > 1:
            story.append(Spacer(1, 0.18 * inch))
        banner = kit.section_banner(section['title'], number=section_no,
                                    pagesize=page, S=S)
        story.extend(kit.emit_subtable([banner], None, headers, data, col_widths, S))

    # ------------------------------------------------------------------
    # Build + return
    # ------------------------------------------------------------------
    buffer = BytesIO()
    kit.build_pdf(
        buffer, story, pagesize=page, project_name=project_name,
        skip_first_footer=False,
        title=f"{console.name} - Console Configuration")

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"Console_{console.name.replace(' ', '_')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
