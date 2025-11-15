# planner/utils/pdf_exports/device_pdf.py
"""
Device I/O PDF Export - Fixed with correct field names and multi-tenancy
"""

from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from io import BytesIO
from django.http import HttpResponse

from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN, BRAND_BLUE


def export_all_devices_pdf(current_project):
    """
    Generate PDF export for ALL devices - filtered by current project
    
    Args:
        current_project: The project to filter by (REQUIRED for multi-tenancy)
        
    Returns:
        HttpResponse with PDF content
    """
    from planner.models import Device
    
    # Safety check - must have a project
    if not current_project:
        return HttpResponse("No project selected", status=403)
    
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
    
    # CRITICAL: Filter by project and prefetch all relationships
    devices = Device.objects.filter(
        project=current_project
    ).select_related(
        'location'
    ).prefetch_related(
        'inputs',
        'outputs',
        'inputs__console_input',  # Based on your field names
        'inputs__console_input__console',  # Get the console too
        'outputs__console_output',
        'outputs__console_output__console'
    ).order_by('name')
    
    if not devices:
        story.append(Paragraph("No devices found in this project", styles.get_normal_style()))
    else:
        for idx, device in enumerate(devices):
            if idx > 0:  # Add page break between devices (except first)
                story.append(PageBreak())
            
            # Device Title
            device_title = f"<b>Device: {device.name}</b>"
            if device.location:
                device_title += f" - Location: {device.location.name}"
            story.append(Paragraph(device_title, styles.get_header_style()))
            story.append(Spacer(1, 0.2 * inch))
            
            # INPUTS SECTION
            story.append(Paragraph("<b>INPUTS</b>", styles.get_section_style()))
            story.append(Spacer(1, 0.1 * inch))
            
            # Get inputs ordered by input_number
            device_inputs = device.inputs.all().order_by('input_number')
            
            if device_inputs:
                # Build input table with grid format
                # Create header row
                input_data = [['Input', 'Signal Name', 'Source']]
                
                for inp in device_inputs:
                    # Build source description from console_input
                    source = ''
                    if inp.console_input and inp.console_input.console:
                        # ConsoleInput has 'input_ch' field (as shown in Django shell)
                        console_input_num = getattr(inp.console_input, 'input_ch', '')
                        source = f"{inp.console_input.console.name} - Input {console_input_num}"
                    
                    # Get the input assignment from console_input.source field
                    # The ConsoleInput.source field contains values like "wless", "podium", "Vid L", etc.
                    input_assignment = ''
                    if inp.console_input and hasattr(inp.console_input, 'source'):
                        input_assignment = inp.console_input.source or f"In {inp.input_number}"
                    else:
                        input_assignment = f"In {inp.input_number}"
                    
                    input_data.append([
                        input_assignment,  # Show "wless", "podium", etc.
                        inp.signal_name or '',
                        source
                    ])
                
                # Create input table with grid styling
                col_widths = [1*inch, 3*inch, 4*inch]
                input_table = Table(input_data, colWidths=col_widths)
                input_table.setStyle([
                    # Header row styling
                    ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    
                    # Data rows styling
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Center input numbers
                    ('ALIGN', (1, 0), (-1, -1), 'LEFT'),   # Left align text
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    
                    # Grid and alternating colors
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ])
                story.append(input_table)
            else:
                story.append(Paragraph("No inputs configured", styles.get_normal_style()))
            
            story.append(Spacer(1, 0.2 * inch))
            
            # OUTPUTS SECTION
            story.append(Paragraph("<b>OUTPUTS</b>", styles.get_section_style()))
            story.append(Spacer(1, 0.1 * inch))
            
            # Get outputs ordered by output_number
            device_outputs = device.outputs.all().order_by('output_number')
            
            if device_outputs:
                # Build output table with grid format
                output_data = [['Output', 'Destination']]
                
                for out in device_outputs:
                    # Build destination from console_output
                    destination = ''
                    if out.console_output and out.console_output.console:
                        # Determine output type - check for different field names
                        output_type = 'Output'
                        if hasattr(out.console_output, 'aux_number'):
                            output_type = f"Aux {out.console_output.aux_number}"
                        elif hasattr(out.console_output, 'matrix_number'):
                            output_type = f"Matrix {out.console_output.matrix_number}"
                        elif hasattr(out.console_output, 'output_number'):
                            output_type = f"Output {out.console_output.output_number}"
                        elif hasattr(out.console_output, 'number'):
                            output_type = f"Output {out.console_output.number}"
                        
                        destination = f"{out.console_output.console.name} - {output_type}"
                    
                    # For outputs, show the signal name in the first column
                    # Based on your screenshot, signal_name contains "FB", "Lobby", "Left", etc.
                    output_label = ''
                    if out.signal_name:
                        output_label = out.signal_name
                    else:
                        # Fall back to output number if no signal name
                        output_label = f"Out {out.output_number}"
                    
                    output_data.append([
                        output_label,  # Show signal name like "FB", "Lobby", "Left"
                        destination
                    ])
                
                # Create output table with grid styling (2 columns now)
                col_widths = [2*inch, 6*inch]
                output_table = Table(output_data, colWidths=col_widths)
                output_table.setStyle([
                    # Header row styling
                    ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    
                    # Data rows styling
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Center output numbers
                    ('ALIGN', (1, 0), (-1, -1), 'LEFT'),   # Left align text
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    
                    # Grid and alternating colors
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ])
                story.append(output_table)
            else:
                story.append(Paragraph("No outputs configured", styles.get_normal_style()))
    
    # Build PDF with page numbers
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Devices_{current_project.name}.pdf"'
    
    return response


def export_device_pdf(device):
    """
    Generate PDF export for a SINGLE device
    
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
        title=f"Device - {device.name}"
    )
    
    story = []
    styles = PDFStyles()
    
    # Device Title
    device_title = f"<b>Device I/O Configuration - {device.name}</b>"
    if device.location:
        device_title += f" - Location: {device.location.name}"
    story.append(Paragraph(device_title, styles.get_header_style()))
    story.append(Spacer(1, 0.3 * inch))
    
    # INPUTS SECTION - Using correct field names
    story.append(Paragraph("<b>INPUTS</b>", styles.get_section_style()))
    story.append(Spacer(1, 0.1 * inch))
    
    device_inputs = device.inputs.all().order_by('input_number')
    
    if device_inputs:
        input_data = [['Input', 'Signal Name', 'Source']]
        
        for inp in device_inputs:
            # Build source from console_input
            source = ''
            if inp.console_input and inp.console_input.console:
                # ConsoleInput has 'input_ch' field (as shown in Django shell)
                console_input_num = getattr(inp.console_input, 'input_ch', '')
                source = f"{inp.console_input.console.name} - Input {console_input_num}"
            
            # Get the input assignment from console_input.source field
            # The ConsoleInput.source field contains values like "wless", "podium", "Vid L", etc.
            input_assignment = ''
            if inp.console_input and hasattr(inp.console_input, 'source'):
                input_assignment = inp.console_input.source or f"In {inp.input_number}"
            else:
                input_assignment = f"In {inp.input_number}"
            
            input_data.append([
                input_assignment,  # Show "wless", "podium", etc.
                inp.signal_name or '',
                source
            ])
        
        col_widths = [1*inch, 3*inch, 4*inch]
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
            ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ])
        story.append(input_table)
    else:
        story.append(Paragraph("No inputs configured", styles.get_normal_style()))
    
    story.append(Spacer(1, 0.2 * inch))
    
    # OUTPUTS SECTION - Using correct field names
    story.append(Paragraph("<b>OUTPUTS</b>", styles.get_section_style()))
    story.append(Spacer(1, 0.1 * inch))
    
    device_outputs = device.outputs.all().order_by('output_number')
    
    if device_outputs:
        output_data = [['Output', 'Destination']]
        
        for out in device_outputs:
            # Build destination from console_output
            destination = ''
            if out.console_output and out.console_output.console:
                # Check for different field names
                output_type = 'Output'
                if hasattr(out.console_output, 'aux_number'):
                    output_type = f"Aux {out.console_output.aux_number}"
                elif hasattr(out.console_output, 'matrix_number'):
                    output_type = f"Matrix {out.console_output.matrix_number}"
                elif hasattr(out.console_output, 'output_number'):
                    output_type = f"Output {out.console_output.output_number}"
                elif hasattr(out.console_output, 'number'):
                    output_type = f"Output {out.console_output.number}"
                
                destination = f"{out.console_output.console.name} - {output_type}"
            
            # For outputs, show the signal name in the first column
            output_label = ''
            if out.signal_name:
                output_label = out.signal_name
            else:
                # Fall back to output number if no signal name
                output_label = f"Out {out.output_number}"
            
            output_data.append([
                output_label,  # Show signal name like "FB", "Lobby", "Left"
                destination
            ])
        
        col_widths = [2*inch, 6*inch]
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
            ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ])
        story.append(output_table)
    else:
        story.append(Paragraph("No outputs configured", styles.get_normal_style()))
    
    # Build PDF
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Device_{device.name}.pdf"'
    
    return response# Deployed Sat Nov 15 10:37:25 EST 2025
