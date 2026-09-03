# planner/utils/pdf_exports/amplifier_pdf.py
"""
Amplifier Assignments PDF Export.

Mirrors the ShowStack "Amp Assignment" rack-view module using the shared
report_kit toolkit (kit.amp_card renders one styled front-panel card per amp).
Grouped by rack location. FILTERED BY CURRENT PROJECT FOR MULTI-TENANCY.
"""

from io import BytesIO

from django.http import HttpResponse
from reportlab.lib.units import inch
from reportlab.platypus import (
    Spacer, PageBreak, CondPageBreak, Paragraph,
)

from planner.utils.pdf_exports import report_kit as kit


def export_all_amps_pdf(current_project):
    """
    Generate PDF export for amplifiers in CURRENT PROJECT ONLY.

    Args:
        current_project: The project to filter by (REQUIRED for multi-tenancy)

    Returns:
        HttpResponse with PDF content
    """
    from planner.models import Amp

    # Safety check - must have a project
    if not current_project:
        buffer = BytesIO()
        S = kit.styles()
        story = [Paragraph("ERROR: No project selected", S['doc_title'])]
        kit.build_pdf(buffer, story, pagesize=kit.LANDSCAPE_PAGE,
                      title="Amplifier Assignments")
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="Error.pdf"'
        return response

    S = kit.styles()
    story = []

    # Title header
    story += kit.title_header("Amplifier Assignments", current_project.name)

    # Query amps for this project only
    amps = (Amp.objects.filter(project=current_project)
            .select_related('location', 'amp_model')
            .prefetch_related('channels')
            .order_by('location__sort_order', 'location__name',
                      'sort_order', 'name'))

    if not amps.exists():
        story.append(Paragraph("No amplifiers configured.", S['empty']))
    else:
        current_location = object()  # sentinel so the first rack always prints
        for amp in amps:
            loc_name = amp.location.name if amp.location else 'Unassigned'
            if loc_name != current_location:
                current_location = loc_name
                story.append(CondPageBreak(kit.SUBTABLE_MIN_ROOM))
                story.append(Paragraph(loc_name, S['sub']))
            # Keep the whole card together so its navy header never splits
            # from the body; each card stays well under a page tall.
            story.append(kit.keep([kit.amp_card(amp)]))
            story.append(Spacer(1, 0.14 * inch))

    buffer = BytesIO()
    kit.build_pdf(buffer, story, pagesize=kit.LANDSCAPE_PAGE,
                  project_name=current_project.name,
                  title="Amplifier Assignments")
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Amplifier_Assignments.pdf"'
    return response
