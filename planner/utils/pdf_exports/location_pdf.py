# planner/utils/pdf_exports/location_pdf.py
"""
Location PDF Export - Equipment listing by location

Shows all equipment assigned to each location, grouped by module.
Restyled onto the shared report_kit toolkit so it matches the other
ShowStack module exports: navy title header, full-width section banner per
location, zebra-striped data tables, empty-column pruning, orphan-free
headings, and a "Page X of Y" footer.
"""

from reportlab.lib.units import inch
from reportlab.platypus import Spacer, PageBreak, Paragraph
from django.http import HttpResponse
from datetime import datetime
import io

from planner.utils.pdf_exports import report_kit as kit


def export_all_locations_pdf(request):
    """
    Generate PDF showing ALL locations with their equipment
    Organized by location, then by module within each location
    """
    from planner.models import Location, Amp

    # Get all locations for current project
    if hasattr(request, 'current_project') and request.current_project:
        locations = Location.objects.filter(
            project=request.current_project
        ).prefetch_related(
            'consoles',
            'devices',
            'system_processors',
            'comm_beltpacks__position',
            'comm_beltpacks__name'
        ).order_by('name')
    else:
        locations = Location.objects.none()

    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"All_Locations_Equipment_List.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    if hasattr(request, 'current_project') and request.current_project:
        project_name = request.current_project.name
    else:
        project_name = "All Projects"

    S = kit.styles()
    page = kit.PORTRAIT_PAGE
    story = []

    subtitle = (
        f"Project: {project_name}  |  "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    story += kit.title_header("Equipment by Location", subtitle, page, S)

    for location in locations:
        # Location-level flowables that must stay with the first sub-table
        # (or, if the location is empty, with the "no equipment" note).
        pending = [kit.section_banner(location.name, pagesize=page, S=S)]
        if location.description:
            pending.append(Paragraph(location.description, S['meta']))

        sections = _all_location_sections(location)

        if not sections:
            story += pending
            story.append(Paragraph(
                "No equipment assigned to this location", S['empty']))
            story.append(PageBreak())
            continue

        first = True
        for heading, headers, data, col_widths in sections:
            headers, data, col_widths = kit.prune_empty_columns(
                headers, data, col_widths, keep=(0,))
            blocks = list(pending) if first else []
            blocks.append(_sub_heading(heading, S))
            story += kit.emit_subtable(blocks, None, headers, data,
                                       col_widths, S=S)
            story.append(Spacer(1, 0.12 * inch))
            first = False

        story.append(PageBreak())

    kit.build_pdf(io_buffer := io.BytesIO(), story, pagesize=page,
                  project_name=project_name, title="Equipment by Location")
    response.write(io_buffer.getvalue())
    io_buffer.close()
    return response


def export_location_pdf(request, location_id):
    """
    Generate PDF showing all equipment in a specific location
    Organized by module: Consoles, Devices, Amps, System Processors, Comm Belt Packs
    """
    from planner.models import Location, Amp

    location = Location.objects.select_related('project').prefetch_related(
        'consoles',
        'devices',
        'system_processors',
        'comm_beltpacks__position',
        'comm_beltpacks__name'
    ).get(id=location_id)

    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"{location.name.replace(' ', '_')}_Equipment_List.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    project_name = location.project.name
    S = kit.styles()
    page = kit.PORTRAIT_PAGE
    story = []

    subtitle = (
        f"Project: {project_name}  |  "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    story += kit.title_header(f"Equipment Location: {location.name}",
                             subtitle, page, S)

    pending = [kit.section_banner(location.name, pagesize=page, S=S)]
    if location.description:
        pending.append(Paragraph(
            f"Description: {location.description}", S['meta']))

    consoles = location.consoles.all()
    devices = location.devices.all()
    amps = Amp.objects.none()  # issue #29: amps live on AmpLocation now
    processors = location.system_processors.all()
    beltpacks = location.comm_beltpacks.all().order_by('bp_number')

    sections = _single_location_sections(consoles, devices, processors,
                                         beltpacks)

    if not sections:
        story += pending
        story.append(Paragraph(
            "No equipment assigned to this location", S['empty']))
    else:
        first = True
        for heading, headers, data, col_widths in sections:
            headers, data, col_widths = kit.prune_empty_columns(
                headers, data, col_widths, keep=(0,))
            blocks = list(pending) if first else []
            blocks.append(_sub_heading(heading, S))
            story += kit.emit_subtable(blocks, None, headers, data,
                                       col_widths, S=S)
            story.append(Spacer(1, 0.14 * inch))
            first = False

    # Equipment summary
    summary_headers = ['Module', 'Count']
    summary_data = [
        ['Consoles', str(consoles.count())],
        ['I/O Devices', str(devices.count())],
        ['Amplifiers', str(amps.count())],
        ['System Processors', str(processors.count())],
        ['Comm Belt Packs', str(beltpacks.count())],
        ['Total Equipment', str(consoles.count() + devices.count()
                                + amps.count() + processors.count()
                                + beltpacks.count())],
    ]
    story.append(Spacer(1, 0.2 * inch))
    story += kit.emit_subtable([_sub_heading("Equipment Summary", S)], None,
                               summary_headers, summary_data,
                               [3 * inch, 1 * inch], S=S)

    kit.build_pdf(io_buffer := io.BytesIO(), story, pagesize=page,
                  project_name=project_name,
                  title=f"Equipment Location: {location.name}")
    response.write(io_buffer.getvalue())
    io_buffer.close()
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sub_heading(text, S):
    return Paragraph(text, S['sub'])


def _all_location_sections(location):
    """Build (heading, headers, data, col_widths) tuples for each equipment
    type present on a location, for the all-locations report."""
    sections = []

    consoles = location.consoles.all()
    if consoles.exists():
        data = [[c.name, c.primary_ip_address or 'N/A',
                 '✓' if c.is_template else ''] for c in consoles]
        sections.append(("Consoles",
                         ['Console Name', 'IP Address', 'Template'],
                         data,
                         [3 * inch, 2 * inch, 1 * inch]))

    devices = location.devices.all()
    if devices.exists():
        data = [[d.name, f"{d.input_count}/{d.output_count}",
                 d.primary_ip_address or 'N/A'] for d in devices]
        sections.append(("I/O Devices",
                         ['Device Name', 'I/O', 'IP Address'],
                         data,
                         [3 * inch, 1 * inch, 2 * inch]))

    processors = location.system_processors.all()
    if processors.exists():
        data = [[p.name, p.device_type, p.ip_address or 'N/A']
                for p in processors]
        sections.append(("System Processors",
                         ['Processor Name', 'Type', 'IP Address'],
                         data,
                         [2.5 * inch, 1.5 * inch, 2 * inch]))

    beltpacks = location.comm_beltpacks.all().order_by('bp_number')
    if beltpacks.exists():
        data = []
        for bp in beltpacks:
            position_name = bp.position.name if bp.position else 'Unassigned'
            crew_name = bp.name.name if bp.name else ''
            system_type = (bp.get_system_type_display()
                           if hasattr(bp, 'get_system_type_display')
                           else bp.system_type)
            ip = bp.ip_address or '' if bp.system_type == 'HARDWIRED' else ''
            data.append([f"BP #{bp.bp_number}", system_type, position_name,
                         crew_name, ip])
        sections.append(("Comm Belt Packs",
                         ['BP #', 'Type', 'Position', 'Name', 'IP Address'],
                         data,
                         [0.8 * inch, 1 * inch, 1.5 * inch, 1.5 * inch,
                          1.2 * inch]))

    return sections


def _single_location_sections(consoles, devices, processors, beltpacks):
    """Build (heading, headers, data, col_widths) tuples for the single
    location report (richer columns than the all-locations view)."""
    sections = []

    if consoles.exists():
        data = [[c.name, c.primary_ip_address or 'N/A',
                 c.secondary_ip_address or 'N/A',
                 '✓ Template' if c.is_template else ''] for c in consoles]
        sections.append(("Consoles",
                         ['Console Name', 'Primary IP', 'Secondary IP',
                          'Status'],
                         data,
                         [2.5 * inch, 1.5 * inch, 1.5 * inch, 1 * inch]))

    if devices.exists():
        data = [[d.name, str(d.input_count), str(d.output_count),
                 d.primary_ip_address or 'N/A',
                 d.secondary_ip_address or 'N/A'] for d in devices]
        sections.append(("I/O Devices",
                         ['Device Name', 'Inputs', 'Outputs', 'Primary IP',
                          'Secondary IP'],
                         data,
                         [2 * inch, 0.7 * inch, 0.7 * inch, 1.5 * inch,
                          1.5 * inch]))

    if processors.exists():
        data = []
        for p in processors:
            notes = (p.notes[:50] + '...'
                     if p.notes and len(p.notes) > 50 else (p.notes or ''))
            data.append([p.name, p.device_type, p.ip_address or 'N/A', notes])
        sections.append(("System Processors",
                         ['Processor Name', 'Type', 'IP Address', 'Notes'],
                         data,
                         [2 * inch, 1.2 * inch, 1.5 * inch, 1.8 * inch]))

    if beltpacks.exists():
        data = []
        for bp in beltpacks:
            position_name = bp.position.name if bp.position else 'Unassigned'
            crew_name = bp.name.name if bp.name else ''
            system_type = (bp.get_system_type_display()
                           if hasattr(bp, 'get_system_type_display')
                           else bp.system_type)
            headset = (bp.get_headset_display()
                       if hasattr(bp, 'get_headset_display') and bp.headset
                       else '')
            ip = bp.ip_address or '' if bp.system_type == 'HARDWIRED' else ''
            data.append([f"BP #{bp.bp_number}", system_type, position_name,
                         crew_name, headset, ip])
        sections.append(("Comm Belt Packs",
                         ['BP #', 'Type', 'Position', 'Name', 'Headset',
                          'IP Address'],
                         data,
                         [0.7 * inch, 0.9 * inch, 1.3 * inch, 1.3 * inch,
                          1 * inch, 1.3 * inch]))

    return sections
