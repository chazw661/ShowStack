"""
System Processor PDF Export.

Restyled to match the ShowStack professional report look (navy palette, zebra
tables, "Page X of Y" footer). Mirrors the processor section of the Complete
System Report (`system_report._section_processors`): per processor a
"Processor: {name}" subheading with a meta line, then Inputs and Outputs
tables grouped Analog -> AES -> AVB, empty columns pruned, only labeled
channels shown.
"""

from io import BytesIO

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer

from planner.models import SystemProcessor
from planner.utils.pdf_exports import report_kit as kit


# Channel-type ordering: Analog -> AES -> AVB (matches the system report).
_PROC_TYPE_ORDER = {'ANALOG': 0, 'AES': 1, 'AVB': 2}


def _channel_sort(chan, type_attr):
    return (_PROC_TYPE_ORDER.get(getattr(chan, type_attr, ''), 9), chan.channel_number)


def generate_system_processor_pdf(current_project):
    """
    Generate the System Processors PDF, filtered by the current project.

    Args:
        current_project: The Project instance to scope to (REQUIRED for
            multi-tenancy).

    Returns:
        BytesIO buffer positioned at 0, ready to hand to HttpResponse.
    """
    buffer = BytesIO()
    S = kit.styles()
    pagesize = kit.LANDSCAPE_PAGE

    story = kit.title_header(
        "System Processors",
        current_project.name if current_project else "",
        pagesize, S,
    )

    if not current_project:
        story.append(Paragraph("No project selected.", S['empty']))
        kit.build_pdf(buffer, story, pagesize=pagesize, title="System Processors")
        buffer.seek(0)
        return buffer

    processors = SystemProcessor.objects.filter(
        project=current_project
    ).select_related('location').order_by('location__name', 'name')

    if not processors.exists():
        story.append(Paragraph(
            f"No system processors found in project: {current_project.name}",
            S['empty'],
        ))
        kit.build_pdf(buffer, story, pagesize=pagesize,
                      project_name=current_project.name, title="System Processors")
        buffer.seek(0)
        return buffer

    for proc in processors:
        type_disp = (proc.get_device_type_display()
                     if hasattr(proc, 'get_device_type_display') else proc.device_type)
        head = [Paragraph(f"Processor: {proc.name or 'Unnamed'}", S['sub'])]
        meta_bits = [f"Type: {type_disp}"]
        if proc.location:
            meta_bits.append(f"Location: {proc.location.name}")
        if proc.ip_address:
            meta_bits.append(f"IP: {proc.ip_address}")
        head.append(Paragraph("  •  ".join(meta_bits), S['meta']))
        if getattr(proc, 'notes', None):
            head.append(Paragraph(f"Notes: {proc.notes}", S['meta']))

        in_rows, out_rows, out_headers, out_widths = [], [], None, None
        p1 = getattr(proc, 'p1_config', None)
        gal = getattr(proc, 'galaxy_config', None)

        if p1:
            for c in sorted(p1.inputs.all(), key=lambda c: _channel_sort(c, 'input_type')):
                if (c.label or '').strip():
                    in_rows.append([c.get_input_type_display(), str(c.channel_number), c.label])
            for c in sorted(p1.outputs.all(), key=lambda c: _channel_sort(c, 'output_type')):
                if (c.label or '').strip() or c.assigned_bus:
                    out_rows.append([
                        c.get_output_type_display(), str(c.channel_number), c.label or '',
                        f"Bus {c.assigned_bus}" if c.assigned_bus else '',
                    ])
            out_headers = ['Type', 'Ch', 'Label', 'Bus']
            out_widths = [w * inch for w in (1.5, 0.8, 4.2, 1.2)]
        elif gal:
            for c in sorted(gal.inputs.all(), key=lambda c: _channel_sort(c, 'input_type')):
                if (c.label or '').strip():
                    in_rows.append([c.get_input_type_display(), str(c.channel_number), c.label])
            for c in sorted(gal.outputs.all(), key=lambda c: _channel_sort(c, 'output_type')):
                if (c.label or '').strip() or c.assigned_bus or (c.destination or '').strip():
                    out_rows.append([
                        c.get_output_type_display(), str(c.channel_number), c.label or '',
                        f"Bus {c.assigned_bus}" if c.assigned_bus else '', c.destination or '',
                    ])
            out_headers = ['Type', 'Ch', 'Label', 'Bus', 'Destination']
            out_widths = [w * inch for w in (1.3, 0.7, 2.9, 1.0, 2.6)]

        emitted = False
        if in_rows:
            in_headers = ['Type', 'Ch', 'Label']
            in_widths = [w * inch for w in (1.7, 0.8, 5.0)]
            story += kit.emit_subtable(head, "Inputs", in_headers, in_rows, in_widths, S)
            head = []
            emitted = True
        if out_rows:
            # Drop Bus / Destination columns when nothing populates them.
            out_headers, out_rows, out_widths = kit.prune_empty_columns(
                out_headers, out_rows, out_widths, keep=(0, 1, 2))
            story += kit.emit_subtable(head, "Outputs", out_headers, out_rows, out_widths, S)
            head = []
            emitted = True

        if not emitted:
            note = ("No channels labeled." if (p1 or gal)
                    else "No channel configuration for this processor.")
            head.append(Paragraph(note, S['empty']))
            story.append(kit.keep(head))

        story.append(Spacer(1, 0.2 * inch))

    kit.build_pdf(buffer, story, pagesize=pagesize,
                  project_name=current_project.name, title="System Processors")
    buffer.seek(0)
    return buffer
