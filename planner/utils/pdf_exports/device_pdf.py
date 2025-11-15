# planner/utils/pdf_exports/device_pdf.py
"""
Device I/O PDF Export - Fixed version that handles NULL input_number/output_number
"""

from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from django.http import HttpResponse

# Define defaults
LANDSCAPE_PAGE = landscape(letter)
MARGIN = 0.5 * inch
BRAND_BLUE = colors.HexColor('#4a9eff')
DARK_GRAY = colors.HexColor('#333333')


def export_all_devices_pdf(current_project):
    """
    Generate PDF export for ALL devices - filtered by current project
    """
    from planner.models import Device
    
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
    styles = getSampleStyleSheet()
    
    header_style = ParagraphStyle(
        'DeviceHeader',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=BRAND_BLUE,
        spaceAfter=12,
    )
    
    # Page header
    story.append(Paragraph(f"<b>All I/O Devices - {current_project.name}</b>", header_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Get devices with relationships
    devices = Device.objects.filter(
        project=current_project
    ).select_related(
        'location'
    ).prefetch_related(
        'inputs',
        'outputs',
        'inputs__console_input',
        'outputs__console_output'
    ).order_by('name')
    
    if not devices:
        story.append(Paragraph("No devices found in this project", styles['Normal']))
    else:
        for idx, device in enumerate(devices):
            if idx > 0:
                story.append(PageBreak())
            
            # Device Title
            device_title = f"<b>Device: {device.name}</b>"
            if device.location:
                device_title += f" - Location: {device.location.name}"
            story.append(Paragraph(device_title, header_style))
            story.append(Spacer(1, 0.15 * inch))
            
            # Get inputs and outputs
            device_inputs = list(device.inputs.all())  # Don't order by input_number since it's NULL
            device_outputs = list(device.outputs.all())
            
            # Determine max rows needed
            max_rows = max(len(device_inputs), len(device_outputs))
            
            if max_rows > 0:
                combined_data = []
                
                # Header row
                combined_data.append([
                    Paragraph("<b>INPUTS</b>", styles['Heading3']),
                    '',
                    '',  # Spacer column
                    Paragraph("<b>OUTPUTS</b>", styles['Heading3']),
                    ''
                ])
                
                # Sub-header row
                combined_data.append([
                    Paragraph("<b>Input</b>", styles['Normal']),
                    Paragraph("<b>Assignment</b>", styles['Normal']),
                    '',  # Spacer column
                    Paragraph("<b>Output</b>", styles['Normal']),
                    Paragraph("<b>Assignment</b>", styles['Normal'])
                ])
                
                # Data rows
                for i in range(max_rows):
                    row = []
                    
                    # Input columns
                    if i < len(device_inputs):
                        inp = device_inputs[i]
                        # Since input_number is NULL, use position (i+1)
                        input_num = f"In {i + 1}"
                        
                        # Get the assignment from console_input.source
                        input_assignment = ''
                        if inp.console_input and hasattr(inp.console_input, 'source'):
                            input_assignment = inp.console_input.source or ''
                        
                        row.append(input_num)
                        row.append(input_assignment)
                    else:
                        row.append('')
                        row.append('')
                    
                    # Spacer column
                    row.append('')
                    
                    # Output columns
                    if i < len(device_outputs):
                        out = device_outputs[i]
                        # Since output_number is NULL, use position (i+1)
                        output_num = f"Out {i + 1}"
                        
                        # Get the assignment from signal_name
                        output_assignment = out.signal_name or ''
                        
                        row.append(output_num)
                        row.append(output_assignment)
                    else:
                        row.append('')
                        row.append('')
                    
                    combined_data.append(row)
                
                # Create the combined table
                col_widths = [1.2*inch, 2.3*inch, 0.5*inch, 1.2*inch, 2.3*inch]
                combined_table = Table(combined_data, colWidths=col_widths)
                
                # Style the table
                table_style = [
                    # Main headers
                    ('BACKGROUND', (0, 0), (1, 0), BRAND_BLUE),
                    ('BACKGROUND', (3, 0), (4, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                    ('TEXTCOLOR', (3, 0), (4, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 11),
                    
                    # Sub-headers
                    ('BACKGROUND', (0, 1), (1, 1), colors.HexColor('#e0e0e0')),
                    ('BACKGROUND', (3, 1), (4, 1), colors.HexColor('#e0e0e0')),
                    ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 1), (-1, 1), 9),
                    
                    # Data rows
                    ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 2), (-1, -1), 9),
                    
                    # Alignment
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                    ('ALIGN', (4, 0), (4, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    
                    # Grid for input and output sections only
                    ('GRID', (0, 1), (1, -1), 0.5, colors.grey),
                    ('GRID', (3, 1), (4, -1), 0.5, colors.grey),
                    
                    # Padding
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]
                
                # Add alternating row colors
                for i in range(2, len(combined_data)):
                    if i % 2 == 0:
                        table_style.append(('BACKGROUND', (0, i), (1, i), colors.white))
                        table_style.append(('BACKGROUND', (3, i), (4, i), colors.white))
                    else:
                        table_style.append(('BACKGROUND', (0, i), (1, i), colors.HexColor('#f5f5f5')))
                        table_style.append(('BACKGROUND', (3, i), (4, i), colors.HexColor('#f5f5f5')))
                
                combined_table.setStyle(table_style)
                story.append(combined_table)
            else:
                story.append(Paragraph("No inputs or outputs configured", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Devices_{current_project.name}.pdf"'
    
    return response


def export_device_pdf(device):
    """
    Generate PDF export for a SINGLE device
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
    styles = getSampleStyleSheet()
    
    header_style = ParagraphStyle(
        'DeviceHeader',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=BRAND_BLUE,
        spaceAfter=12,
    )
    
    # Device Title
    device_title = f"<b>Device I/O Configuration - {device.name}</b>"
    if device.location:
        device_title += f" - Location: {device.location.name}"
    story.append(Paragraph(device_title, header_style))
    story.append(Spacer(1, 0.15 * inch))
    
    # Get inputs and outputs
    device_inputs = list(device.inputs.all())
    device_outputs = list(device.outputs.all())
    
    max_rows = max(len(device_inputs), len(device_outputs))
    
    if max_rows > 0:
        combined_data = []
        
        # Header row
        combined_data.append([
            Paragraph("<b>INPUTS</b>", styles['Heading3']),
            '',
            '',  # Spacer column
            Paragraph("<b>OUTPUTS</b>", styles['Heading3']),
            ''
        ])
        
        # Sub-header row
        combined_data.append([
            Paragraph("<b>Input</b>", styles['Normal']),
            Paragraph("<b>Assignment</b>", styles['Normal']),
            '',  # Spacer column
            Paragraph("<b>Output</b>", styles['Normal']),
            Paragraph("<b>Assignment</b>", styles['Normal'])
        ])
        
        # Data rows
        for i in range(max_rows):
            row = []
            
            # Input columns
            if i < len(device_inputs):
                inp = device_inputs[i]
                # Since input_number is NULL, use position
                input_num = f"In {i + 1}"
                
                input_assignment = ''
                if inp.console_input and hasattr(inp.console_input, 'source'):
                    input_assignment = inp.console_input.source or ''
                
                row.append(input_num)
                row.append(input_assignment)
            else:
                row.append('')
                row.append('')
            
            # Spacer column
            row.append('')
            
            # Output columns
            if i < len(device_outputs):
                out = device_outputs[i]
                # Since output_number is NULL, use position
                output_num = f"Out {i + 1}"
                output_assignment = out.signal_name or ''
                
                row.append(output_num)
                row.append(output_assignment)
            else:
                row.append('')
                row.append('')
            
            combined_data.append(row)
        
        # Create table
        col_widths = [1.2*inch, 2.3*inch, 0.5*inch, 1.2*inch, 2.3*inch]
        combined_table = Table(combined_data, colWidths=col_widths)
        
        # Style the table
        table_style = [
            # Headers
            ('BACKGROUND', (0, 0), (1, 0), BRAND_BLUE),
            ('BACKGROUND', (3, 0), (4, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('TEXTCOLOR', (3, 0), (4, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            
            # Sub-headers
            ('BACKGROUND', (0, 1), (1, 1), colors.HexColor('#e0e0e0')),
            ('BACKGROUND', (3, 1), (4, 1), colors.HexColor('#e0e0e0')),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, 1), 9),
            
            # Data
            ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 2), (-1, -1), 9),
            
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (4, 0), (4, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid
            ('GRID', (0, 1), (1, -1), 0.5, colors.grey),
            ('GRID', (3, 1), (4, -1), 0.5, colors.grey),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        
        # Alternating row colors
        for i in range(2, len(combined_data)):
            if i % 2 == 0:
                table_style.append(('BACKGROUND', (0, i), (1, i), colors.white))
                table_style.append(('BACKGROUND', (3, i), (4, i), colors.white))
            else:
                table_style.append(('BACKGROUND', (0, i), (1, i), colors.HexColor('#f5f5f5')))
                table_style.append(('BACKGROUND', (3, i), (4, i), colors.HexColor('#f5f5f5')))
        
        combined_table.setStyle(table_style)
        story.append(combined_table)
    else:
        story.append(Paragraph("No inputs or outputs configured", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Device_{device.name}.pdf"'
    
    return response