"""
System Processor PDF Export - FIXED
Generates a PDF with one processor per page showing full channel configuration grids.
"""

from io import BytesIO
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from django.utils import timezone

from planner.models import SystemProcessor
from .pdf_styles import BRAND_BLUE, DARK_GRAY, MARGIN, PDFStyles


def generate_system_processor_pdf(current_project):
    """
    Generate PDF with one processor per page showing full configuration.
    
    Args:
        current_project: The project to filter by (REQUIRED for multi-tenancy)
    """
    buffer = BytesIO()
    
    # Create PDF document (LANDSCAPE for wide channel grids)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )
    
    # Container for PDF elements
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=BRAND_BLUE,
        spaceAfter=2,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=DARK_GRAY,
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica',
    )
    
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=6,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=5,
        alignment=TA_LEFT,
    )
    
    # CRITICAL: Filter by current project for multi-tenancy
    if not current_project:
        no_project = Paragraph("ERROR: No project selected", title_style)
        elements.append(no_project)
    else:
        # Get processors filtered by current project, ordered by location then name
        processors = SystemProcessor.objects.filter(
            project=current_project
        ).select_related('location').order_by('location__name', 'name')
        
        if not processors.exists():
            no_data = Paragraph(f"No system processors found in project: {current_project.name}", cell_style)
            elements.append(no_data)
        else:
            for idx, proc in enumerate(processors):
                # Page heading: Device Type
                device_type_title = Paragraph(
                    proc.get_device_type_display() or "System Processor", 
                    title_style
                )
                elements.append(device_type_title)
                
                # Subtitle: Processor Name
                name_subtitle = Paragraph(proc.name or "Unnamed Processor", subtitle_style)
                elements.append(name_subtitle)
                
                # Add configuration based on processor type
                if proc.device_type == 'P1':
                    elements.extend(_generate_p1_config(proc, section_style, header_style, cell_style))
                elif proc.device_type == 'GALAXY':
                    elements.extend(_generate_galaxy_config(proc, section_style, header_style, cell_style))
                
                # Add page break if not the last processor
                if idx < len(processors) - 1:
                    elements.append(PageBreak())
    
    # Build PDF with page numbers
    doc.build(elements, onFirstPage=PDFStyles.add_page_number, 
              onLaterPages=PDFStyles.add_page_number)
    
    buffer.seek(0)
    return buffer


def _generate_basic_info(proc, header_style, cell_style):
    """Generate basic processor info when detailed configuration doesn't exist."""
    elements = []
    
    label_style = ParagraphStyle(
        'LabelStyle',
        parent=cell_style,
        fontSize=9,
        textColor=colors.white,
        fontName='Helvetica-Bold',
    )
    
    value_style = ParagraphStyle(
        'ValueStyle',
        parent=cell_style,
        fontSize=9,
        textColor=DARK_GRAY,
    )
    
    elements.append(Spacer(1, 0.2*inch))
    
    # Basic info message
    info_msg = Paragraph(
        "<i>Channel configuration not yet set up. Click 'Configure' to add input/output assignments.</i>",
        cell_style
    )
    elements.append(info_msg)
    elements.append(Spacer(1, 0.2*inch))
    
    # Basic details table
    config_data = [
        [Paragraph('<b>Device Type</b>', label_style), 
         Paragraph(proc.get_device_type_display() or '', value_style)],
        [Paragraph('<b>Name</b>', label_style), 
         Paragraph(proc.name or '', value_style)],
        [Paragraph('<b>Location</b>', label_style), 
         Paragraph(proc.location.name if proc.location else '', value_style)],
        [Paragraph('<b>IP Address</b>', label_style), 
         Paragraph(proc.ip_address or 'Not configured', value_style)],
        [Paragraph('<b>Notes</b>', label_style), 
         Paragraph(proc.notes or '', value_style)],
    ]
    
    col_widths = [2.5*inch, 5.0*inch]
    config_table = Table(config_data, colWidths=col_widths)
    config_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
        ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ('TEXTCOLOR', (1, 0), (1, -1), DARK_GRAY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(config_table)
    
    return elements


def _generate_p1_config(proc, section_style, header_style, cell_style):
    """Generate P1 processor configuration grids."""
    elements = []
    
    # Try to get the P1Processor config
    try:
        p1_proc = proc.p1_config
        # Get all inputs and outputs with proper ordering
        analog_inputs = list(p1_proc.inputs.filter(input_type='ANALOG').order_by('channel_number'))
        aes_inputs = list(p1_proc.inputs.filter(input_type='AES').order_by('channel_number'))
        avb_inputs = list(p1_proc.inputs.filter(input_type='AVB').order_by('channel_number'))
        
        analog_outputs = list(p1_proc.outputs.filter(output_type='ANALOG').order_by('channel_number'))
        aes_outputs = list(p1_proc.outputs.filter(output_type='AES').order_by('channel_number'))
        avb_outputs = list(p1_proc.outputs.filter(output_type='AVB').order_by('channel_number'))
    except:
        # If no P1Processor config exists, create empty lists
        analog_inputs = []
        aes_inputs = []
        avb_inputs = []
        analog_outputs = []
        aes_outputs = []
        avb_outputs = []
    
    # INPUTS SECTION
    elements.append(Spacer(1, 0.05*inch))
    inputs_header = Table([[Paragraph("P1 INPUTS", section_style)]], colWidths=[10*inch])
    inputs_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_BLUE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(inputs_header)
    elements.append(Spacer(1, 0.02*inch))
    
    # Analog Inputs (4 channels) - always show
    elements.append(_create_input_table(analog_inputs, "Analog Inputs (1-4)", 
                                       header_style, cell_style, 4))
    elements.append(Spacer(1, 0.02*inch))
    
    # AES Inputs (4 channels) - always show
    elements.append(_create_input_table(aes_inputs, "AES Inputs (1-4)", 
                                       header_style, cell_style, 4))
    elements.append(Spacer(1, 0.02*inch))
    
    # AVB Inputs (8 channels) - always show
    elements.append(_create_input_table(avb_inputs, "AVB (1-8)", 
                                       header_style, cell_style, 8))
    
    # OUTPUTS SECTION
    elements.append(Spacer(1, 0.1*inch))
    outputs_header = Table([[Paragraph("P1 OUTPUTS", section_style)]], colWidths=[10*inch])
    outputs_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_BLUE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(outputs_header)
    elements.append(Spacer(1, 0.02*inch))
    
    # Analog Outputs (4 channels) - always show
    elements.append(_create_output_table(analog_outputs, "Analog Outputs (1-4)", 
                                        header_style, cell_style, 4))
    elements.append(Spacer(1, 0.02*inch))
    
    # AES Outputs (4 channels) - always show
    elements.append(_create_output_table(aes_outputs, "AES Outputs (1-4)", 
                                        header_style, cell_style, 4))
    elements.append(Spacer(1, 0.02*inch))
    
    # AVB Outputs (8 channels) - always show
    elements.append(_create_output_table(avb_outputs, "AVB Outputs (1-8)", 
                                        header_style, cell_style, 8))
    
    return elements


def _generate_galaxy_config(proc, section_style, header_style, cell_style):
    """Generate Galaxy processor configuration grids."""
    elements = []
    
    # Try to get the GalaxyProcessor config
    try:
        galaxy_proc = proc.galaxy_config
        # Get inputs and outputs with proper ordering
        inputs = list(galaxy_proc.inputs.all().order_by('channel_number'))
        outputs = list(galaxy_proc.outputs.all().order_by('channel_number'))
    except:
        inputs = []
        outputs = []
    
    # INPUTS SECTION
    elements.append(Spacer(1, 0.05*inch))
    inputs_header = Table([[Paragraph("GALAXY INPUTS", section_style)]], colWidths=[10*inch])
    inputs_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_BLUE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(inputs_header)
    elements.append(Spacer(1, 0.02*inch))
    
    # All 16 Galaxy inputs in one row
    elements.append(_create_input_table_range(inputs, "Inputs (1-16)", 
                                              header_style, cell_style, 1, 16))
    
    # OUTPUTS SECTION  
    elements.append(Spacer(1, 0.1*inch))
    outputs_header = Table([[Paragraph("GALAXY OUTPUTS", section_style)]], colWidths=[10*inch])
    outputs_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_BLUE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(outputs_header)
    elements.append(Spacer(1, 0.02*inch))
    
    # All 16 Galaxy outputs in one row
    elements.append(_create_output_table_range(outputs, "Outputs (1-16)", 
                                               header_style, cell_style, 1, 16))
    
    return elements


def _create_input_table(inputs, title, header_style, cell_style, num_channels):
    """Create a table for input channels - shows all channels even if blank."""
    # Convert inputs list to dictionary keyed by channel number for easy lookup
    inputs_dict = {inp.channel_number: inp for inp in inputs} if inputs else {}
    
    # Section title row
    table_data = [
        [Paragraph(f"<b>{title}</b>", header_style)]
    ]
    
    # Channel headers (create columns for each channel 1 to num_channels)
    channel_headers = []
    for ch_num in range(1, num_channels + 1):
        channel_headers.append(Paragraph(f"<b>Ch {ch_num}</b>", header_style))
    table_data.append(channel_headers)
    
    # Label row
    label_row = []
    for ch_num in range(1, num_channels + 1):
        inp = inputs_dict.get(ch_num)
        label = inp.label if inp and inp.label else ''
        label_row.append(Paragraph(label, cell_style))
    table_data.append(label_row)
    
    # Source/Origin row
    source_row = []
    for ch_num in range(1, num_channels + 1):
        inp = inputs_dict.get(ch_num)
        if inp and inp.label:  # Only if channel is actually used
            # For Analog and AES, show origin_device_output
            if inp.input_type in ['ANALOG', 'AES'] and inp.origin_device_output:
                source = str(inp.origin_device_output)
            elif inp.input_type == 'AVB':
                source = 'Network Stream'
            else:
                source = ''
        else:
            source = ''
        source_row.append(Paragraph(source, cell_style))
    table_data.append(source_row)
    
    # Calculate column widths
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row - INCREASED PADDING
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 6),  # Increased from 4
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Increased from 4
        
        # Header row - INCREASED PADDING
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 7),
        ('TOPPADDING', (0, 1), (-1, 1), 5),  # Increased from 2
        ('BOTTOMPADDING', (0, 1), (-1, 1), 5),  # Increased from 2
        
        # Data rows - INCREASED PADDING
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 6),
        ('TOPPADDING', (0, 2), (-1, -1), 6),  # Increased from 3
        ('BOTTOMPADDING', (0, 2), (-1, -1), 6),  # Increased from 3
        ('LEFTPADDING', (0, 2), (-1, -1), 4),  # Increased from 3
        ('RIGHTPADDING', (0, 2), (-1, -1), 4),  # Increased from 3
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table


def _create_input_table_range(inputs, title, header_style, cell_style, start_ch, end_ch):
    """Create a table for input channels with specific channel number range."""
    # Convert inputs list to dictionary keyed by channel number
    inputs_dict = {inp.channel_number: inp for inp in inputs} if inputs else {}
    
    # Section title row
    table_data = [
        [Paragraph(f"<b>{title}</b>", header_style)]
    ]
    
    # Channel headers
    channel_headers = []
    for ch_num in range(start_ch, end_ch + 1):
        channel_headers.append(Paragraph(f"<b>Ch {ch_num}</b>", header_style))
    table_data.append(channel_headers)
    
    # Label row
    label_row = []
    for ch_num in range(start_ch, end_ch + 1):
        inp = inputs_dict.get(ch_num)
        label = inp.label if inp and inp.label else ''
        label_row.append(Paragraph(label, cell_style))
    table_data.append(label_row)
    
    # Source/Origin row
    source_row = []
    for ch_num in range(start_ch, end_ch + 1):
        inp = inputs_dict.get(ch_num)
        if inp and inp.label:  # Only if channel is actually used
            if inp.input_type in ['ANALOG', 'AES'] and inp.origin_device_output:
                source = str(inp.origin_device_output)
            elif inp.input_type == 'AVB':
                source = 'Network Stream'
            else:
                source = ''
        else:
            source = ''
        source_row.append(Paragraph(source, cell_style))
    table_data.append(source_row)
    
    # Calculate column widths
    num_channels = end_ch - start_ch + 1
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row - INCREASED PADDING
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 6),  # Increased
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Increased
        
        # Header row - INCREASED PADDING
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('TOPPADDING', (0, 1), (-1, 1), 5),  # Increased
        ('BOTTOMPADDING', (0, 1), (-1, 1), 5),  # Increased
        
        # Data rows - INCREASED PADDING
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 5),
        ('TOPPADDING', (0, 2), (-1, -1), 6),  # Increased
        ('BOTTOMPADDING', (0, 2), (-1, -1), 6),  # Increased
        ('LEFTPADDING', (0, 2), (-1, -1), 4),  # Increased
        ('RIGHTPADDING', (0, 2), (-1, -1), 4),  # Increased
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table


def _create_output_table(outputs, title, header_style, cell_style, num_channels):
    """Create a table for output channels - shows all channels even if blank."""
    # Convert outputs list to dictionary keyed by channel number
    outputs_dict = {out.channel_number: out for out in outputs} if outputs else {}
    
    # Section title row
    table_data = [
        [Paragraph(f"<b>{title}</b>", header_style)]
    ]
    
    # Channel headers
    channel_headers = []
    for ch_num in range(1, num_channels + 1):
        channel_headers.append(Paragraph(f"<b>Ch {ch_num}</b>", header_style))
    table_data.append(channel_headers)
    
    # Label row
    label_row = []
    for ch_num in range(1, num_channels + 1):
        out = outputs_dict.get(ch_num)
        label = out.label if out and out.label else ''
        label_row.append(Paragraph(label, cell_style))
    table_data.append(label_row)
    
    # Bus assignment row
    bus_row = []
    for ch_num in range(1, num_channels + 1):
        out = outputs_dict.get(ch_num)
        if out and out.label and out.assigned_bus:  # Only if channel is used AND has bus
            bus_text = f"Bus {out.assigned_bus}"
        else:
            bus_text = ''
        bus_row.append(Paragraph(bus_text, cell_style))
    table_data.append(bus_row)
    
    # Calculate column widths
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row - INCREASED PADDING
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 6),  # Increased
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Increased
        
        # Header row - INCREASED PADDING
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 7),
        ('TOPPADDING', (0, 1), (-1, 1), 5),  # Increased
        ('BOTTOMPADDING', (0, 1), (-1, 1), 5),  # Increased
        
        # Data rows - INCREASED PADDING
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 6),
        ('TOPPADDING', (0, 2), (-1, -1), 6),  # Increased
        ('BOTTOMPADDING', (0, 2), (-1, -1), 6),  # Increased
        ('LEFTPADDING', (0, 2), (-1, -1), 4),  # Increased
        ('RIGHTPADDING', (0, 2), (-1, -1), 4),  # Increased
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table


def _create_output_table_range(outputs, title, header_style, cell_style, start_ch, end_ch):
    """Create a table for output channels with specific channel number range."""
    # Convert outputs list to dictionary keyed by channel number
    outputs_dict = {out.channel_number: out for out in outputs} if outputs else {}
    
    # Section title row
    table_data = [
        [Paragraph(f"<b>{title}</b>", header_style)]
    ]
    
    # Channel headers
    channel_headers = []
    for ch_num in range(start_ch, end_ch + 1):
        channel_headers.append(Paragraph(f"<b>Ch {ch_num}</b>", header_style))
    table_data.append(channel_headers)
    
    # Label row
    label_row = []
    for ch_num in range(start_ch, end_ch + 1):
        out = outputs_dict.get(ch_num)
        label = out.label if out and out.label else ''
        label_row.append(Paragraph(label, cell_style))
    table_data.append(label_row)
    
    # Bus assignment row
    bus_row = []
    for ch_num in range(start_ch, end_ch + 1):
        out = outputs_dict.get(ch_num)
        if out and out.label and out.assigned_bus:  # Only if channel is used AND has bus
            bus_text = f"Bus {out.assigned_bus}"
        else:
            bus_text = ''
        bus_row.append(Paragraph(bus_text, cell_style))
    table_data.append(bus_row)
    
    # Calculate column widths
    num_channels = end_ch - start_ch + 1
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row - INCREASED PADDING
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 6),  # Increased
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Increased
        
        # Header row - INCREASED PADDING
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('TOPPADDING', (0, 1), (-1, 1), 5),  # Increased
        ('BOTTOMPADDING', (0, 1), (-1, 1), 5),  # Increased
        
        # Data rows - INCREASED PADDING
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 5),
        ('TOPPADDING', (0, 2), (-1, -1), 6),  # Increased
        ('BOTTOMPADDING', (0, 2), (-1, -1), 6),  # Increased
        ('LEFTPADDING', (0, 2), (-1, -1), 4),  # Increased
        ('RIGHTPADDING', (0, 2), (-1, -1), 4),  # Increased
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table