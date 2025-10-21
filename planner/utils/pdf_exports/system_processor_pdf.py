"""
System Processor PDF Export
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


def generate_system_processor_pdf():
    """Generate PDF with one processor per page showing full configuration."""
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
    
    # Get all system processors ordered by location, then name
    processors = SystemProcessor.objects.select_related('location').order_by(
        'location__name', 'name'
    )
    
    if not processors.exists():
        no_data = Paragraph("No system processors found.", cell_style)
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
        p1_proc = proc.p1processor
        # Get all inputs and outputs
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
    elements.append(_create_input_table(avb_inputs, "AVB Inputs (1-8)", 
                                       header_style, cell_style, 8))
    elements.append(Spacer(1, 0.05*inch))
    
    # OUTPUTS SECTION
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
    """Generate GALAXY processor configuration grids."""
    elements = []
    
    # Try to get the GalaxyProcessor config
    try:
        galaxy_proc = proc.galaxyprocessor
        # Get all inputs and outputs
        analog_inputs = list(galaxy_proc.inputs.filter(input_type='ANALOG').order_by('channel_number'))
        aes_inputs = list(galaxy_proc.inputs.filter(input_type='AES').order_by('channel_number'))
        avb_inputs = list(galaxy_proc.inputs.filter(input_type='AVB').order_by('channel_number'))
        
        analog_outputs = list(galaxy_proc.outputs.filter(output_type='ANALOG').order_by('channel_number'))
        aes_outputs = list(galaxy_proc.outputs.filter(output_type='AES').order_by('channel_number'))
        avb_outputs = list(galaxy_proc.outputs.filter(output_type='AVB').order_by('channel_number'))
    except:
        # If no GalaxyProcessor config exists, create empty lists
        analog_inputs = []
        aes_inputs = []
        avb_inputs = []
        analog_outputs = []
        aes_outputs = []
        avb_outputs = []
    
    # INPUTS SECTION
    elements.append(Spacer(1, 0.05*inch))
    inputs_header = Table([[Paragraph("GALAXY INPUTS - MEYER GALAXY CONFIGURATION", section_style)]], 
                          colWidths=[10*inch])
    inputs_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_BLUE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(inputs_header)
    elements.append(Spacer(1, 0.02*inch))
    
    # Analog Inputs (8 channels) - always show
    elements.append(_create_input_table(analog_inputs, "Analog Inputs (1-8)", 
                                       header_style, cell_style, 8))
    elements.append(Spacer(1, 0.02*inch))
    
    # AES/EBU Inputs (8 channels) - always show
    elements.append(_create_input_table(aes_inputs, "AES/EBU Digital Inputs (1-8)", 
                                       header_style, cell_style, 8))
    elements.append(Spacer(1, 0.02*inch))
    
    # AVB/Milan Inputs (1-8) - always show
    avb_inputs_1_8 = [inp for inp in avb_inputs if inp.channel_number <= 8] if avb_inputs else []
    elements.append(_create_input_table_range(avb_inputs_1_8, "AVB/Milan Network Inputs (1-8)", 
                                       header_style, cell_style, 1, 8))
    elements.append(Spacer(1, 0.02*inch))
    
    # AVB/Milan Inputs (9-16) - always show
    avb_inputs_9_16 = [inp for inp in avb_inputs if inp.channel_number > 8] if avb_inputs else []
    elements.append(_create_input_table_range(avb_inputs_9_16, "AVB/Milan Network Inputs (9-16)", 
                                       header_style, cell_style, 9, 16))
    elements.append(Spacer(1, 0.05*inch))
    
    # OUTPUTS SECTION
    outputs_header = Table([[Paragraph("GALAXY OUTPUTS - MEYER GALAXY CONFIGURATION", section_style)]], 
                           colWidths=[10*inch])
    outputs_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_BLUE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(outputs_header)
    elements.append(Spacer(1, 0.02*inch))
    
    # Analog Outputs (8 channels) - always show
    elements.append(_create_output_table(analog_outputs, "Analog Outputs (1-8)", 
                                        header_style, cell_style, 8))
    elements.append(Spacer(1, 0.02*inch))
    
    # AES/EBU Outputs (8 channels) - always show
    elements.append(_create_output_table(aes_outputs, "AES/EBU Digital Outputs (1-8)", 
                                        header_style, cell_style, 8))
    elements.append(Spacer(1, 0.02*inch))
    
    # AVB/Milan Outputs (1-8) - always show
    avb_outputs_1_8 = [out for out in avb_outputs if out.channel_number <= 8] if avb_outputs else []
    elements.append(_create_output_table_range(avb_outputs_1_8, "AVB/Milan Network Outputs (1-8)", 
                                        header_style, cell_style, 1, 8))
    elements.append(Spacer(1, 0.02*inch))
    
    # AVB/Milan Outputs (9-16) - always show
    avb_outputs_9_16 = [out for out in avb_outputs if out.channel_number > 8] if avb_outputs else []
    elements.append(_create_output_table_range(avb_outputs_9_16, "AVB/Milan Network Outputs (9-16)", 
                                        header_style, cell_style, 9, 16))
    
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
        label = inp.label if inp else ''
        label_row.append(Paragraph(label or '', cell_style))
    table_data.append(label_row)
    
    # Source/Origin row (for Analog and AES)
    source_row = []
    for ch_num in range(1, num_channels + 1):
        inp = inputs_dict.get(ch_num)
        if inp:
            if inp.input_type in ['ANALOG', 'AES'] and inp.origin_device_output:
                source = str(inp.origin_device_output)
            else:
                source = 'Network Stream' if inp.input_type == 'AVB' else ''
        else:
            source = ''
        source_row.append(Paragraph(source, cell_style))
    table_data.append(source_row)
    
    # Calculate column widths (divide available width evenly)
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 2),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        
        # Header row
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
        
        # Data rows
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 5),
        ('TOPPADDING', (0, 2), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 2), (-1, -1), 2),
        ('LEFTPADDING', (0, 2), (-1, -1), 2),
        ('RIGHTPADDING', (0, 2), (-1, -1), 2),
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table


def _create_input_table_range(inputs, title, header_style, cell_style, start_ch, end_ch):
    """Create a table for input channels with specific channel number range - shows all channels even if blank."""
    # Convert inputs list to dictionary keyed by channel number for easy lookup
    inputs_dict = {inp.channel_number: inp for inp in inputs} if inputs else {}
    
    # Section title row
    table_data = [
        [Paragraph(f"<b>{title}</b>", header_style)]
    ]
    
    # Channel headers (create columns for each channel from start_ch to end_ch)
    channel_headers = []
    for ch_num in range(start_ch, end_ch + 1):
        channel_headers.append(Paragraph(f"<b>Ch {ch_num}</b>", header_style))
    table_data.append(channel_headers)
    
    # Label row
    label_row = []
    for ch_num in range(start_ch, end_ch + 1):
        inp = inputs_dict.get(ch_num)
        label = inp.label if inp else ''
        label_row.append(Paragraph(label or '', cell_style))
    table_data.append(label_row)
    
    # Source/Origin row (for Analog and AES)
    source_row = []
    for ch_num in range(start_ch, end_ch + 1):
        inp = inputs_dict.get(ch_num)
        if inp:
            if inp.input_type in ['ANALOG', 'AES'] and inp.origin_device_output:
                source = str(inp.origin_device_output)
            else:
                source = 'Network Stream' if inp.input_type == 'AVB' else ''
        else:
            source = ''
        source_row.append(Paragraph(source, cell_style))
    table_data.append(source_row)
    
    # Calculate column widths (divide available width evenly)
    num_channels = end_ch - start_ch + 1
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 2),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        
        # Header row
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
        
        # Data rows
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 5),
        ('TOPPADDING', (0, 2), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 2), (-1, -1), 2),
        ('LEFTPADDING', (0, 2), (-1, -1), 2),
        ('RIGHTPADDING', (0, 2), (-1, -1), 2),
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table


def _create_output_table_range(outputs, title, header_style, cell_style, start_ch, end_ch):
    """Create a table for output channels with specific channel number range - shows all channels even if blank."""
    # Convert outputs list to dictionary keyed by channel number for easy lookup
    outputs_dict = {out.channel_number: out for out in outputs} if outputs else {}
    
    # Section title row
    table_data = [
        [Paragraph(f"<b>{title}</b>", header_style)]
    ]
    
    # Channel headers (create columns for each channel from start_ch to end_ch)
    channel_headers = []
    for ch_num in range(start_ch, end_ch + 1):
        channel_headers.append(Paragraph(f"<b>Ch {ch_num}</b>", header_style))
    table_data.append(channel_headers)
    
    # Label row
    label_row = []
    for ch_num in range(start_ch, end_ch + 1):
        out = outputs_dict.get(ch_num)
        label = out.label if out else ''
        label_row.append(Paragraph(label or '', cell_style))
    table_data.append(label_row)
    
    # Bus assignment row (for outputs)
    bus_row = []
    for ch_num in range(start_ch, end_ch + 1):
        out = outputs_dict.get(ch_num)
        if out and out.assigned_bus:
            bus_text = f"Bus {out.assigned_bus}"
        else:
            bus_text = ''
        bus_row.append(Paragraph(bus_text, cell_style))
    table_data.append(bus_row)
    
    # Destination row
    dest_row = []
    for ch_num in range(start_ch, end_ch + 1):
        out = outputs_dict.get(ch_num)
        if out:
            dest = out.destination or ('Network Stream' if out.output_type == 'AVB' else '')
        else:
            dest = ''
        dest_row.append(Paragraph(dest, cell_style))
    table_data.append(dest_row)
    
    # Calculate column widths
    num_channels = end_ch - start_ch + 1
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 2),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        
        # Header row
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 6),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
        
        # Data rows
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 5),
        ('TOPPADDING', (0, 2), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 2), (-1, -1), 2),
        ('LEFTPADDING', (0, 2), (-1, -1), 2),
        ('RIGHTPADDING', (0, 2), (-1, -1), 2),
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table


def _create_output_table(outputs, title, header_style, cell_style, num_channels):
    """Create a table for output channels - shows all channels even if blank."""
    # Convert outputs list to dictionary keyed by channel number for easy lookup
    outputs_dict = {out.channel_number: out for out in outputs} if outputs else {}
    
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
        out = outputs_dict.get(ch_num)
        label = out.label if out else ''
        label_row.append(Paragraph(label or '', cell_style))
    table_data.append(label_row)
    
    # Bus assignment row (for outputs)
    bus_row = []
    for ch_num in range(1, num_channels + 1):
        out = outputs_dict.get(ch_num)
        if out and out.assigned_bus:
            bus_text = f"Bus {out.assigned_bus}"
        else:
            bus_text = ''
        bus_row.append(Paragraph(bus_text, cell_style))
    table_data.append(bus_row)
    
    # Destination row
    dest_row = []
    for ch_num in range(1, num_channels + 1):
        out = outputs_dict.get(ch_num)
        if out:
            dest = out.destination or ('Network Stream' if out.output_type == 'AVB' else '')
        else:
            dest = ''
        dest_row.append(Paragraph(dest, cell_style))
    table_data.append(dest_row)
    
    # Calculate column widths
    col_width = 10.0*inch / num_channels
    col_widths = [col_width] * num_channels
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Title row
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('SPAN', (0, 0), (-1, 0)),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        
        # Header row
        ('BACKGROUND', (0, 1), (-1, 1), BRAND_BLUE),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
        ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, 1), 7),
        
        # Data rows
        ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, -1), DARK_GRAY),
        ('ALIGN', (0, 2), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 2), (-1, -1), 6),
        ('TOPPADDING', (0, 2), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 2), (-1, -1), 3),
        ('LEFTPADDING', (0, 2), (-1, -1), 3),
        ('RIGHTPADDING', (0, 2), (-1, -1), 3),
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    return table