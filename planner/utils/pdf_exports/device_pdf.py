# planner/utils/pdf_exports/device_pdf.py
"""
Device I/O PDF Export - Clean version that relies on populated input_number/output_number fields
"""

from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from io import BytesIO
from django.http import HttpResponse

from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN, BRAND_BLUE


def export_device_pdf(device):
    """
    Generate PDF export for a single Device
    
    Args:
        device: Device model instance
        
    Returns:
        HttpResponse with PDF content
    """
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"{device.name} - Device I/O"
    )
    
    story = []
    styles = PDFStyles()
    
    # Header
    story.append(Paragraph(f"<b>Device I/O - {device.name}</b>", styles.get_header_style()))
    if device.location:
        story.append(Paragraph(f"Location: {device.location.name}", styles.get_subsection_style()))
    story.append(Spacer(1, 0.3 * inch))
    
    # INPUTS Section
    story.append(Paragraph("<b>INPUTS</b>", styles.get_section_style()))
    story.append(Spacer(1, 0.1 * inch))
    
    # CRITICAL: Order by input_number (now that they're populated!)
    device_inputs = device.inputs.filter(input_number__isnull=False).order_by('input_number')
    
    if device_inputs.exists():
        input_data = [['#', 'Input', 'Console Source']]
        
        for inp in device_inputs:
            # Get input assignment from console_input.source field
            input_label = ''
            console_source = ''
            
            if inp.console_input:
                # ConsoleInput.source contains dropdown values like "wless", "podium", "Vid L"
                input_label = inp.console_input.source or ''
                
                if inp.console_input.console:
                    console_input_num = inp.console_input.input_ch
                    console_source = f"{inp.console_input.console.name} - Input {console_input_num}"
            
            input_data.append([
                str(inp.input_number),
                input_label,
                console_source
            ])
        
        col_widths = [0.5*inch, 2*inch, 6.5*inch]
        input_table = Table(input_data, colWidths=col_widths)
        input_table.setStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ])
        story.append(input_table)
    else:
        story.append(Paragraph("No inputs configured", styles.get_subsection_style()))
    
    story.append(Spacer(1, 0.3 * inch))
    
    # OUTPUTS Section
    story.append(Paragraph("<b>OUTPUTS</b>", styles.get_section_style()))
    story.append(Spacer(1, 0.1 * inch))
    
    # CRITICAL: Order by output_number (now that they're populated!)
    device_outputs = device.outputs.filter(output_number__isnull=False).order_by('output_number')
    
    if device_outputs.exists():
        output_data = [['#', 'Output', 'Console Destination']]
        
        for out in device_outputs:
            # For outputs, use signal_name (contains "FB", "Lobby", "Left", "Right", etc.)
            output_label = out.signal_name or ''
            
            # Build destination from console_output
            console_dest = ''
            if out.console_output and out.console_output.console:
                output_type = 'Output'
                if hasattr(out.console_output, 'aux_number'):
                    output_type = f"Aux {out.console_output.aux_number}"
                elif hasattr(out.console_output, 'matrix_number'):
                    output_type = f"Matrix {out.console_output.matrix_number}"
                
                console_dest = f"{out.console_output.console.name} - {output_type}"
            
            output_data.append([
                str(out.output_number),
                output_label,
                console_dest
            ])
        
        col_widths = [0.5*inch, 2*inch, 6.5*inch]
        output_table = Table(output_data, colWidths=col_widths)
        output_table.setStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ])
        story.append(output_table)
    else:
        story.append(Paragraph("No outputs configured", styles.get_subsection_style()))
    
    # Build PDF
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Device_{device.name}.pdf"'
    
    return response


def export_all_devices_pdf(current_project):
    """
    Generate PDF export for ALL devices in current project
    
    Args:
        current_project: The project to filter by (REQUIRED for multi-tenancy)
        
    Returns:
        HttpResponse with PDF content
    """
    from planner.models import Device
    
    # Safety check
    if not current_project:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=LANDSCAPE_PAGE)
        story = [Paragraph("ERROR: No project selected", PDFStyles().get_header_style())]
        doc.build(story)
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="Error.pdf"'
        return response
    
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"All Devices - {current_project.name}"
    )
    
    story = []
    styles = PDFStyles()
    
    # Header
    story.append(Paragraph(f"<b>All I/O Devices - {current_project.name}</b>", styles.get_header_style()))
    story.append(Spacer(1, 0.3 * inch))
    
    # CRITICAL: Filter by current project AND order by name
    devices = Device.objects.filter(
        project=current_project
    ).select_related('location').prefetch_related(
        'inputs__console_input__console',
        'outputs__console_output'
    ).order_by('name')
    
    if not devices.exists():
        story.append(Paragraph("No devices found in this project", styles.get_subsection_style()))
    else:
        first_device = True
        for device in devices:
            # Page break between devices (except first)
            if not first_device:
                story.append(PageBreak())
            first_device = False
            
            # Device name
            story.append(Paragraph(f"<b>{device.name}</b>", styles.get_section_style()))
            if device.location:
                story.append(Paragraph(f"Location: {device.location.name}", styles.get_subsection_style()))
            story.append(Spacer(1, 0.2 * inch))
            
            # INPUTS
            device_inputs = device.inputs.filter(input_number__isnull=False).order_by('input_number')
            
            if device_inputs.exists():
                story.append(Paragraph("<b>INPUTS</b>", styles.get_subsection_style()))
                story.append(Spacer(1, 0.1 * inch))
                
                input_data = [['#', 'Input', 'Console Source']]
                
                for inp in device_inputs:
                    input_label = ''
                    console_source = ''
                    
                    if inp.console_input:
                        input_label = inp.console_input.source or ''
                        if inp.console_input.console:
                            console_source = f"{inp.console_input.console.name} - In {inp.console_input.input_ch}"
                    
                    input_data.append([
                        str(inp.input_number),
                        input_label,
                        console_source
                    ])
                
                col_widths = [0.5*inch, 2*inch, 6.5*inch]
                input_table = Table(input_data, colWidths=col_widths)
                input_table.setStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ])
                story.append(input_table)
                story.append(Spacer(1, 0.2 * inch))
            
            # OUTPUTS
            device_outputs = device.outputs.filter(output_number__isnull=False).order_by('output_number')
            
            if device_outputs.exists():
                story.append(Paragraph("<b>OUTPUTS</b>", styles.get_subsection_style()))
                story.append(Spacer(1, 0.1 * inch))
                
                output_data = [['#', 'Output', 'Console Destination']]
                
                for out in device_outputs:
                    output_label = out.signal_name or ''
                    
                    console_dest = ''
                    if out.console_output and out.console_output.console:
                        output_type = 'Output'
                        if hasattr(out.console_output, 'aux_number'):
                            output_type = f"Aux {out.console_output.aux_number}"
                        elif hasattr(out.console_output, 'matrix_number'):
                            output_type = f"Matrix {out.console_output.matrix_number}"
                        
                        console_dest = f"{out.console_output.console.name} - {output_type}"
                    
                    output_data.append([
                        str(out.output_number),
                        output_label,
                        console_dest
                    ])
                
                col_widths = [0.5*inch, 2*inch, 6.5*inch]
                output_table = Table(output_data, colWidths=col_widths)
                output_table.setStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ])
                story.append(output_table)
    
    # Build PDF
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="All_Devices_{current_project.name}.pdf"'
    
    return response