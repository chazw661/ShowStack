# planner/utils/pdf_exports/console_pdf.py
"""
Console PDF Export - professional PDF generation for Console configurations.

Restyled to use the shared report_kit toolkit (navy palette, banded tables,
"Page X of Y" footer, orphan-free page breaks). Same data / columns as before.
"""

from io import BytesIO

from reportlab.platypus import Spacer
from reportlab.lib.units import inch
from django.http import HttpResponse

from planner.utils.pdf_exports import report_kit as kit


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

    def add_section(title, headers, data, col_widths):
        """Add a numbered section banner + pruned/styled table, kept together."""
        nonlocal section_no
        if len(data) < 1:
            return
        headers, data, col_widths = kit.prune_empty_columns(
            headers, data, col_widths)
        section_no += 1
        if section_no > 1:
            story.append(Spacer(1, 0.18 * inch))
        banner = kit.section_banner(title, number=section_no, pagesize=page, S=S)
        story.extend(
            kit.emit_subtable([banner], None, headers, data, col_widths, S))

    # ------------------------------------------------------------------
    # Section 1: Console Inputs
    # ------------------------------------------------------------------
    if console.consoleinput_set.exists():
        headers = ['Dante #', 'Input Ch', 'Source', 'Src Hardware', 'Group',
                   'DCA', 'Mute', 'Direct Out', 'Omni In']
        data = []
        for inp in console.consoleinput_set.all().order_by('dante_number'):
            if (inp.dante_number or inp.input_ch or inp.source or inp.group
                    or inp.dca or inp.mute or inp.direct_out or inp.omni_in):
                data.append([
                    str(inp.dante_number) if inp.dante_number else '',
                    inp.input_ch or '',
                    inp.source or '',
                    inp.source_hardware or '',
                    inp.group or '',
                    inp.dca or '',
                    inp.mute or '',
                    inp.direct_out or '',
                    inp.omni_in or '',
                ])
        col_widths = [0.55 * inch, 0.6 * inch, 1.5 * inch, 1.1 * inch, 0.6 * inch,
                      0.5 * inch, 0.5 * inch, 0.7 * inch, 0.7 * inch]
        add_section('Console Inputs', headers, data, col_widths)

    # ------------------------------------------------------------------
    # Section 2: Aux Outputs
    # ------------------------------------------------------------------
    if console.consoleauxoutput_set.exists():
        headers = ['Dante #', 'Aux', 'Name', 'Mono/Stereo', 'Bus Type', 'Omni Out']
        aux_outputs = list(console.consoleauxoutput_set.all())
        aux_outputs.sort(
            key=lambda x: int(x.aux_number)
            if x.aux_number and x.aux_number.isdigit() else 999)
        data = []
        for aux in aux_outputs:
            if (aux.aux_number or aux.dante_number or aux.name or aux.mono_stereo
                    or (hasattr(aux, 'bus_type') and aux.bus_type)
                    or (hasattr(aux, 'omni_out') and aux.omni_out)):
                data.append([
                    str(aux.dante_number) if aux.dante_number else '',
                    aux.aux_number or '',
                    aux.name or '',
                    aux.mono_stereo or '',
                    getattr(aux, 'bus_type', '') or '',
                    getattr(aux, 'omni_out', '') or '',
                ])
        col_widths = [0.8 * inch, 0.6 * inch, 3 * inch, 1 * inch, 1 * inch, 1 * inch]
        add_section('Aux Outputs', headers, data, col_widths)

    # ------------------------------------------------------------------
    # Section 3: Matrix Outputs
    # ------------------------------------------------------------------
    if console.consolematrixoutput_set.exists():
        headers = ['Dante #', 'Matrix', 'Name', 'Mono/Stereo', 'Destination', 'Omni Out']
        matrix_outputs = list(console.consolematrixoutput_set.all())
        matrix_outputs.sort(
            key=lambda x: int(x.matrix_number)
            if x.matrix_number and x.matrix_number.isdigit() else 999)
        data = []
        for mtx in matrix_outputs:
            if (mtx.matrix_number or mtx.dante_number or mtx.name or mtx.mono_stereo
                    or (hasattr(mtx, 'destination') and mtx.destination)
                    or (hasattr(mtx, 'omni_out') and mtx.omni_out)):
                data.append([
                    str(mtx.dante_number) if mtx.dante_number else '',
                    mtx.matrix_number or '',
                    mtx.name or '',
                    mtx.mono_stereo or '',
                    getattr(mtx, 'destination', '') or '',
                    getattr(mtx, 'omni_out', '') or '',
                ])
        col_widths = [0.8 * inch, 0.7 * inch, 2.5 * inch, 1 * inch, 1.5 * inch, 0.9 * inch]
        add_section('Matrix Outputs', headers, data, col_widths)

    # ------------------------------------------------------------------
    # Section 4: Stereo Outputs
    # ------------------------------------------------------------------
    if console.consolestereooutput_set.exists():
        headers = ['Dante #', 'Buss', 'Name', 'Omni Out']
        data = []
        for stereo in console.consolestereooutput_set.all():
            data.append([
                str(stereo.dante_number or ''),
                stereo.get_stereo_type_display() if stereo.stereo_type else '',
                str(stereo.name or ''),
                str(getattr(stereo, 'omni_out', '') or ''),
            ])
        col_widths = [1.2 * inch, 1.8 * inch, 4 * inch, 1.5 * inch]
        add_section('Stereo Outputs', headers, data, col_widths)

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
