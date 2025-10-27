# planner/utils/pdf_exports/device_pdf.py
"""
Device I/O PDF Export - Grid layout matching admin interface
Uses queryset order (by ID) instead of input_number/output_number fields
"""

from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
from reportlab.lib import colors
from io import BytesIO
from django.http import HttpResponse

from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN, BRAND_BLUE


def export_device_pdf(device):
    """
    Generate PDF export for a single Device with grid layout
    
    Args:
        device: Device model instance
    
    Returns:
        HttpResponse with PDF content
    """
    buffer = BytesIO()
    
    # Use landscape for grid layout
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"{device.name} - Device I/O Configuration"
    )
    
    story = []
    styles = PDFStyles()
    
    # Header
    header_text = f"<b>Device I/O Configuration - {device.name}</b>"
    story.append(Paragraph(header_text, styles.get_header_style()))
    story.append(Spacer(1, 0.2 * inch))
    
    # Device Inputs Grid
    if device.input_count > 0:
        story.append(Paragraph("Device Inputs", styles.get_section_style()))
        story.append(Spacer(1, 0.1 * inch))
        
        # Get inputs ordered by ID - position in list = grid position
        inputs_list = list(device.inputs.all().order_by('id'))
        
        # Build grid data (8 columns)
        data = []
        cols_per_row = 8
        
        for row_start in range(0, device.input_count, cols_per_row):
            # Header row
            header_row = []
            for i in range(cols_per_row):
                position = row_start + i
                if position < device.input_count:
                    header_row.append(f"In {position + 1}")
                else:
                    header_row.append('')
            data.append(header_row)
            
            # Data row
            data_row = []
            for i in range(cols_per_row):
                position = row_start + i
                if position < device.input_count:
                    # Get input at this position (if exists)
                    inp = inputs_list[position] if position < len(inputs_list) else None
                    
                    if inp and inp.console_input:
                        # Format: "Ch 1" or just the input reference
                        if inp.console_input.input_ch:
                            cell_text = f"Ch {inp.console_input.input_ch}"
                        elif inp.signal_name:
                            cell_text = inp.signal_name
                        else:
                            cell_text = str(inp.console_input)
                    else:
                        cell_text = "----------"
                    data_row.append(cell_text)
                else:
                    data_row.append('')
            data.append(data_row)
        
        # Calculate column widths
        available_width = LANDSCAPE_PAGE[0] - (2 * MARGIN)
        col_width = available_width / cols_per_row
        col_widths = [col_width] * cols_per_row
        
        # Create table
        t = Table(data, colWidths=col_widths)
        
        # Style the grid
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        
        # Alternate header row backgrounds
        for i in range(0, len(data), 2):
            style_commands.append(('BACKGROUND', (0, i), (-1, i), BRAND_BLUE))
            style_commands.append(('TEXTCOLOR', (0, i), (-1, i), colors.white))
        
        t.setStyle(style_commands)
        story.append(t)
        story.append(Spacer(1, 0.3 * inch))
    
    # Device Outputs Grid
    if device.output_count > 0:
        story.append(Paragraph("Device Outputs", styles.get_section_style()))
        story.append(Spacer(1, 0.1 * inch))
        
        # Get outputs ordered by ID - position in list = grid position
        outputs_list = list(device.outputs.all().order_by('id'))
        
        # Build grid data (8 columns)
        data = []
        cols_per_row = 8
        
        for row_start in range(0, device.output_count, cols_per_row):
            # Header row
            header_row = []
            for i in range(cols_per_row):
                position = row_start + i
                if position < device.output_count:
                    header_row.append(f"Out {position + 1}")
                else:
                    header_row.append('')
            data.append(header_row)
            
            # Data row
            data_row = []
            for i in range(cols_per_row):
                position = row_start + i
                if position < device.output_count:
                    # Get output at this position (if exists)
                    out = outputs_list[position] if position < len(outputs_list) else None
                    
                    if out and out.console_output:
                        # Format: "Aux 1: DPA" or "Matrix 1: Left"
                        if hasattr(out.console_output, 'aux_number'):
                            prefix = f"Aux {out.console_output.aux_number}"
                        elif hasattr(out.console_output, 'matrix_number'):
                            prefix = f"Mat {out.console_output.matrix_number}"
                        else:
                            prefix = "Out"
                        
                        signal = out.signal_name or ""
                        cell_text = f"{prefix}: {signal}" if signal else prefix
                    else:
                        cell_text = "----------"
                    data_row.append(cell_text)
                else:
                    data_row.append('')
            data.append(data_row)
        
        # Calculate column widths
        available_width = LANDSCAPE_PAGE[0] - (2 * MARGIN)
        col_width = available_width / cols_per_row
        col_widths = [col_width] * cols_per_row
        
        # Create table
        t = Table(data, colWidths=col_widths)
        
        # Style the grid
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        
        # Alternate header row backgrounds
        for i in range(0, len(data), 2):
            style_commands.append(('BACKGROUND', (0, i), (-1, i), BRAND_BLUE))
            style_commands.append(('TEXTCOLOR', (0, i), (-1, i), colors.white))
        
        t.setStyle(style_commands)
        story.append(t)
    
    # Build PDF
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    # Return PDF response
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{device.name}_IO_Configuration.pdf"'
    
    return response


def export_all_devices_pdf(show_day=None):
    """
    Generate PDF export for ALL devices (one device per page)
    
    Args:
        show_day: Optional ShowDay to filter devices
    
    Returns:
        HttpResponse with PDF content
    """
    from planner.models import Device
    
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="All Devices - I/O Configuration"
    )
    
    story = []
    styles = PDFStyles()
    
    # Get all devices
    devices = Device.objects.all().order_by('name')
    
    # Loop through each device
    for device_idx, device in enumerate(devices):
        # Header for this device
        header_text = f"<b>Device I/O Configuration - {device.name}</b>"
        story.append(Paragraph(header_text, styles.get_header_style()))
        story.append(Spacer(1, 0.2 * inch))
        
        # Device Inputs Grid
        if device.input_count > 0:
            story.append(Paragraph("Device Inputs", styles.get_section_style()))
            story.append(Spacer(1, 0.1 * inch))
            
            # Get inputs ordered by ID
            inputs_list = list(device.inputs.all().order_by('id'))
            
            data = []
            cols_per_row = 8
            
            for row_start in range(0, device.input_count, cols_per_row):
                header_row = []
                for i in range(cols_per_row):
                    position = row_start + i
                    if position < device.input_count:
                        header_row.append(f"In {position + 1}")
                    else:
                        header_row.append('')
                data.append(header_row)
                
                data_row = []
                for i in range(cols_per_row):
                    position = row_start + i
                    if position < device.input_count:
                        inp = inputs_list[position] if position < len(inputs_list) else None
                        
                        if inp and inp.console_input:
                            if inp.console_input.input_ch:
                                cell_text = f"Ch {inp.console_input.input_ch}"
                            elif inp.signal_name:
                                cell_text = inp.signal_name
                            else:
                                cell_text = str(inp.console_input)
                        else:
                            cell_text = "----------"
                        data_row.append(cell_text)
                    else:
                        data_row.append('')
                data.append(data_row)
            
            available_width = LANDSCAPE_PAGE[0] - (2 * MARGIN)
            col_width = available_width / cols_per_row
            col_widths = [col_width] * cols_per_row
            
            t = Table(data, colWidths=col_widths)
            
            style_commands = [
                ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]
            
            for i in range(0, len(data), 2):
                style_commands.append(('BACKGROUND', (0, i), (-1, i), BRAND_BLUE))
                style_commands.append(('TEXTCOLOR', (0, i), (-1, i), colors.white))
            
            t.setStyle(style_commands)
            story.append(t)
            story.append(Spacer(1, 0.3 * inch))
        
        # Device Outputs Grid
        if device.output_count > 0:
            story.append(Paragraph("Device Outputs", styles.get_section_style()))
            story.append(Spacer(1, 0.1 * inch))
            
            # Get outputs ordered by ID
            outputs_list = list(device.outputs.all().order_by('id'))
            
            data = []
            cols_per_row = 8
            
            for row_start in range(0, device.output_count, cols_per_row):
                header_row = []
                for i in range(cols_per_row):
                    position = row_start + i
                    if position < device.output_count:
                        header_row.append(f"Out {position + 1}")
                    else:
                        header_row.append('')
                data.append(header_row)
                
                data_row = []
                for i in range(cols_per_row):
                    position = row_start + i
                    if position < device.output_count:
                        out = outputs_list[position] if position < len(outputs_list) else None
                        
                        if out and out.console_output:
                            if hasattr(out.console_output, 'aux_number'):
                                prefix = f"Aux {out.console_output.aux_number}"
                            elif hasattr(out.console_output, 'matrix_number'):
                                prefix = f"Mat {out.console_output.matrix_number}"
                            else:
                                prefix = "Out"
                            
                            signal = out.signal_name or ""
                            cell_text = f"{prefix}: {signal}" if signal else prefix
                        else:
                            cell_text = "----------"
                        data_row.append(cell_text)
                    else:
                        data_row.append('')
                data.append(data_row)
            
            available_width = LANDSCAPE_PAGE[0] - (2 * MARGIN)
            col_width = available_width / cols_per_row
            col_widths = [col_width] * cols_per_row
            
            t = Table(data, colWidths=col_widths)
            
            style_commands = [
                ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]
            
            for i in range(0, len(data), 2):
                style_commands.append(('BACKGROUND', (0, i), (-1, i), BRAND_BLUE))
                style_commands.append(('TEXTCOLOR', (0, i), (-1, i), colors.white))
            
            t.setStyle(style_commands)
            story.append(t)
        
        # Page break after each device (except the last one)
            story.append(PageBreak())
    
    # Build PDF
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="All_Devices_IO_Configuration.pdf"'
    
    return response