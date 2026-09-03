# planner/utils/pdf_exports/soundvision_pdf.py

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from planner.utils.pdf_exports import report_kit as kit


def _array_facts(array):
    """Yield (label, value) pairs for an array's attributes, skipping blanks."""
    facts = []
    if array.array_base_name:
        facts.append(("Base Name", array.array_base_name))
    if getattr(array, 'symmetry_type', None):
        facts.append(("Symmetry", array.symmetry_type))
    if array.group_context:
        facts.append(("Group", array.group_context))
    if array.configuration:
        facts.append(("Configuration",
                      array.get_configuration_display()
                      if hasattr(array, 'get_configuration_display') else array.configuration))
    if array.bumper_type and array.bumper_type != 'NONE':
        facts.append(("Bumper",
                      array.get_bumper_type_display()
                      if hasattr(array, 'get_bumper_type_display') else array.bumper_type))
    if array.mbar_hole:
        facts.append(("MBAR Hole", array.mbar_hole))
    pos = []
    if array.position_x is not None:
        pos.append(f"X: {array.position_x}")
    if array.position_y is not None:
        pos.append(f"Y: {array.position_y}")
    if array.position_z is not None:
        pos.append(f"Z: {array.position_z}")
    if pos:
        facts.append(("Position", ", ".join(pos)))
    if getattr(array, 'bottom_elevation', None) is not None:
        feet = int(array.bottom_elevation)
        inches = int((float(array.bottom_elevation) - feet) * 12)
        facts.append(("Bottom Trim Height", f"{feet}' {inches}\""))
    return facts


def generate_soundvision_pdf(prediction):
    """
    Generate PDF for Soundvision Prediction with all arrays and cabinets.

    Args:
        prediction: SoundvisionPrediction model instance

    Returns:
        BytesIO buffer containing the PDF
    """
    pagesize = kit.LANDSCAPE_PAGE
    S = kit.styles()

    # Title + subtitle
    title_parts = []
    if prediction.show_day:
        title_parts.append(str(prediction.show_day))
    title_parts.append(prediction.file_name)
    subtitle = " - ".join(title_parts)

    story = kit.title_header("Soundvision Prediction", subtitle, pagesize, S)

    # File / version / generated meta line
    meta_parts = [f"File: {prediction.file_name}"]
    if prediction.version:
        meta_parts.append(f"Version {prediction.version}")
    if prediction.date_generated:
        meta_parts.append(f"Generated {prediction.date_generated.strftime('%b %d, %Y')}")
    story.append(Paragraph("  •  ".join(meta_parts), S['meta']))

    if prediction.notes:
        story.append(Paragraph(f"<b>Notes:</b> {prediction.notes}", S['meta']))
    story.append(Spacer(1, 0.12 * inch))

    arrays = prediction.speaker_arrays.all().order_by('source_name')

    if not arrays.exists():
        story.append(Paragraph("No speaker arrays found in this prediction.", S['empty']))
    else:
        # System summary
        total_arrays = arrays.count()
        total_cabinets = sum(a.cabinets.count() for a in arrays)
        summary = Table(
            [['TOTAL ARRAYS', 'TOTAL CABINETS'], [str(total_arrays), str(total_cabinets)]],
            colWidths=[2.2 * inch, 2.2 * inch], hAlign='LEFT')
        summary.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), kit.NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8.5),
            ('FONTSIZE', (0, 1), (-1, 1), 13),
            ('TEXTCOLOR', (0, 1), (-1, 1), kit.NAVY),
            ('GRID', (0, 0), (-1, -1), 0.5, kit.HAIRLINE),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(summary)
        story.append(Spacer(1, 0.14 * inch))

        array_header_style = ParagraphStyle(
            'ArrayHeader', fontSize=10.5, textColor=colors.white, backColor=kit.NAVY,
            fontName='Helvetica-Bold', leftIndent=8, rightIndent=8,
            spaceBefore=8, spaceAfter=4, leading=18, borderPadding=(3, 4, 3, 4))
        array_info = ParagraphStyle(
            'ArrayInfo', fontSize=8, textColor=kit.INK, leftIndent=12, leading=11)

        for idx, array in enumerate(arrays):
            blocks = [Paragraph(array.source_name or f"Array {idx + 1}", array_header_style)]
            for label, val in _array_facts(array):
                blocks.append(Paragraph(f"<b>{label}:</b> {val}", array_info))

            cabinets = array.cabinets.all().order_by('position_number')
            if cabinets.exists():
                headers = ['#', 'Model', 'Angle', 'Panflex']
                col_widths = [0.5 * inch, 2.4 * inch, 1.1 * inch, 1.6 * inch]
                data = []
                for cab_idx, cab in enumerate(cabinets, 1):
                    angle = f"{cab.angle_to_next}°" if cab.angle_to_next is not None else ''
                    panflex = cab.get_panflex_setting_display() if (
                        hasattr(cab, 'get_panflex_setting_display') and cab.panflex_setting) else ''
                    data.append([str(cab_idx), cab.speaker_model or '', angle, panflex])

                headers, data, col_widths = kit.prune_empty_columns(
                    headers, data, col_widths, keep=(0, 1))
                cab_table = kit.data_table(headers, data, col_widths)
                if cab_table is not None:
                    blocks.append(Spacer(1, 0.04 * inch))
                    blocks.append(cab_table)
            else:
                blocks.append(Paragraph("<i>No cabinets defined for this array</i>", S['empty']))

            story.append(kit.keep(blocks))
            story.append(Spacer(1, 0.12 * inch))

    buf = BytesIO()
    kit.build_pdf(buf, story, pagesize=pagesize,
                  project_name=str(prediction.project) if prediction.project_id else '',
                  title="Soundvision Prediction")
    buf.seek(0)
    return buf
