# planner/utils/pdf_exports/device_pdf.py
"""
Device I/O PDF Export.

Restyled onto the shared report_kit toolkit so it matches the professional
navy/blue look used across all ShowStack module exports (title header, navy
table headers, zebra striping, "Page X of Y" footer, orphan-safe page breaks).

Relies on populated input_number/output_number fields. Physical ports are
numbered 1-based by position in that ordering (NOT the stored *_number, which
can hold legacy/global values) via enumerate(...) -- matching the edit grid.
"""

from io import BytesIO
from reportlab.lib.units import inch
from reportlab.platypus import Spacer, Paragraph
from django.http import HttpResponse

from planner.utils.pdf_exports import report_kit as kit


def _device_blocks(device, S):
    """Return the flowables for a single device: a subheading + its Inputs and
    Outputs subtables. Empty devices get a short 'no signals' note instead."""
    story = []
    header_blocks = [Paragraph(f"Device: {device.name}", S['sub'])]
    if device.location:
        header_blocks.append(Paragraph(f"Location: {device.location.name}", S['meta']))
    emitted = False

    # INPUTS -----------------------------------------------------------------
    # Physical port = 1-based position in input_number order (matches the edit
    # grid), NOT the stored input_number (which can be legacy/global). Rows with
    # no signal or console source are dropped, but numbering keeps counting.
    inputs = device.inputs.filter(input_number__isnull=False).order_by('input_number')
    rows = []
    for port, inp in enumerate(inputs, 1):
        label = (inp.signal_name or '').strip()
        console_source = ''
        if inp.console_input:
            if not label:
                label = inp.console_input.source or ''
            if inp.console_input.console:
                console_source = (
                    f"{inp.console_input.console.name} - Input {inp.console_input.input_ch}"
                )
        if not (label or console_source):
            continue
        rows.append([str(port), label, console_source])
    if rows:
        headers = ['Input #', 'Signal', 'Console Source']
        widths = [w * inch for w in (0.9, 2.6, 3.6)]
        headers, data, widths = kit.prune_empty_columns(headers, rows, widths, keep=(0, 1))
        story += kit.emit_subtable(header_blocks, "Inputs", headers, data, widths, S)
        header_blocks = []
        emitted = True

    # OUTPUTS ----------------------------------------------------------------
    outputs = device.outputs.filter(output_number__isnull=False).order_by('output_number')
    rows = [[str(port), (o.signal_name or '').strip()]
            for port, o in enumerate(outputs, 1) if (o.signal_name or '').strip()]
    if rows:
        headers = ['Output #', 'Signal Name']
        widths = [w * inch for w in (0.9, 6.2)]
        story += kit.emit_subtable(header_blocks, "Outputs", headers, rows, widths, S)
        header_blocks = []
        emitted = True

    if not emitted:
        header_blocks.append(Paragraph("No input/output signals configured.", S['empty']))
        story.append(kit.keep(header_blocks))

    return story


def export_device_pdf(device):
    """
    Generate PDF export for a single Device.

    Args:
        device: Device model instance

    Returns:
        HttpResponse with PDF content
    """
    buffer = BytesIO()
    S = kit.styles()
    pagesize = kit.LANDSCAPE_PAGE

    story = kit.title_header("Device I/O", device.name, pagesize, S)
    story += _device_blocks(device, S)

    project_name = device.project.name if getattr(device, 'project', None) else ''
    kit.build_pdf(buffer, story, pagesize=pagesize, project_name=project_name,
                  title=f"{device.name} - Device I/O")

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Device_{device.name}.pdf"'
    return response


def export_all_devices_pdf(current_project):
    """
    Generate PDF export for ALL devices in current project.

    Args:
        current_project: The project to filter by (REQUIRED for multi-tenancy)

    Returns:
        HttpResponse with PDF content
    """
    from planner.models import Device

    buffer = BytesIO()
    S = kit.styles()
    pagesize = kit.LANDSCAPE_PAGE

    # Safety check
    if not current_project:
        story = kit.title_header("Device I/O", "No project selected", pagesize, S)
        story.append(Paragraph("ERROR: No project selected", S['empty']))
        kit.build_pdf(buffer, story, pagesize=pagesize, title="Device I/O")
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="Error.pdf"'
        return response

    story = kit.title_header("Device I/O", current_project.name, pagesize, S)

    # CRITICAL: Filter by current project AND order by name.
    devices = Device.objects.filter(
        project=current_project
    ).select_related('location').prefetch_related(
        'inputs__console_input__console',
        'outputs__console_output',
    ).order_by('name')

    if not devices.exists():
        story.append(Paragraph("No devices found in this project.", S['empty']))
    else:
        # Each device is its own subheading block; emit_subtable handles page
        # breaks so there is no forced full-page break between devices.
        for device in devices:
            story += _device_blocks(device, S)
            story.append(Spacer(1, 0.2 * inch))

    kit.build_pdf(buffer, story, pagesize=pagesize, project_name=current_project.name,
                  title=f"All Devices - {current_project.name}")

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="All_Devices_{current_project.name}.pdf"'
    return response
