# planner/utils/pdf_exports/soundvision_pdf.py

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from decimal import Decimal

try:
    from .pdf_styles import PDFStyles, MARGIN, BRAND_BLUE, DARK_GRAY
except ImportError:
    # Fallback values if pdf_styles doesn't exist
    MARGIN = 0.5 * inch
    BRAND_BLUE = colors.HexColor('#4a9eff')
    DARK_GRAY = colors.HexColor('#333333')


def generate_soundvision_pdf(prediction):
    """
    Generate PDF for Soundvision Prediction with all arrays and cabinets.
    
    Args:
        prediction: SoundvisionPrediction model instance
        
    Returns:
        BytesIO buffer containing the PDF
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN + 0.3*inch,
        bottomMargin=MARGIN + 0.3*inch,
    )
    
    styles = getSampleStyleSheet()
    elements = []
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=DARK_GRAY,
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=DARK_GRAY,
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    array_header_style = ParagraphStyle(
        'ArrayHeader',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.white,
        spaceAfter=4,
        spaceBefore=12,
        fontName='Helvetica-Bold',
        backColor=BRAND_BLUE,
        leftIndent=6,
        rightIndent=6,
    )
    
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=DARK_GRAY,
        spaceAfter=2,
        leftIndent=12,
    )
    
    # Table style for cabinets
    cabinet_table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
    ])
    
    # Main Title
    title_parts = []
    if prediction.show_day:
        title_parts.append(prediction.show_day.name)
    title_parts.append(prediction.file_name)
    title_text = " - ".join(title_parts)
    
    title = Paragraph(f"SOUNDVISION PREDICTION<br/>{title_text}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.1*inch))
    
    # Subtitle with file info
    subtitle_parts = []
    subtitle_parts.append(f"File: {prediction.file_name}")
    if prediction.version:
        subtitle_parts.append(f"Version: {prediction.version}")
    if prediction.date_generated:
        subtitle_parts.append(f"Generated: {prediction.date_generated.strftime('%b. %d, %Y')}")
    
    subtitle_text = " | ".join(subtitle_parts)
    subtitle = Paragraph(subtitle_text, subtitle_style)
    elements.append(subtitle)
    
    # Notes if any
    if prediction.notes:
        notes_para = Paragraph(f"<b>Notes:</b> {prediction.notes}", info_style)
        elements.append(notes_para)
        elements.append(Spacer(1, 0.05*inch))
    
    elements.append(Spacer(1, 0.15*inch))
    
    # Get all arrays ordered by source name
    arrays = prediction.speaker_arrays.all().order_by('source_name')
    
    if not arrays.exists():
        no_arrays = Paragraph("No speaker arrays found in this prediction.", info_style)
        elements.append(no_arrays)
    else:
        # System Summary
        total_arrays = arrays.count()
        total_cabinets = sum(array.cabinets.count() for array in arrays)
        
        summary_data = [
            ['TOTAL ARRAYS', 'TOTAL CABINETS'],
            [str(total_arrays), str(total_cabinets)]
        ]
        
        summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, 1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Process each array
        for idx, array in enumerate(arrays):
            # Array Header with name
            array_name = array.source_name or f"Array {idx + 1}"
            array_header = Paragraph(f" {array_name}", array_header_style)
            elements.append(array_header)
            elements.append(Spacer(1, 0.05*inch))
            
            # Array Information
            info_lines = []
            
            if array.array_base_name:
                info_lines.append(f"<b>Base Name:</b> {array.array_base_name}")
            
            if array.symmetry_type:
                info_lines.append(f"<b>Symmetry:</b> {array.symmetry_type}")
            
            if array.group_context:
                info_lines.append(f"<b>Group:</b> {array.group_context}")
            
            if array.configuration:
                config_display = array.get_configuration_display() if hasattr(array, 'get_configuration_display') else array.configuration
                info_lines.append(f"<b>Configuration:</b> {config_display}")
            
            if array.bumper_type and array.bumper_type != 'NONE':
                bumper_display = array.get_bumper_type_display() if hasattr(array, 'get_bumper_type_display') else array.bumper_type
                info_lines.append(f"<b>Bumper:</b> {bumper_display}")
            
            # Position data
            position_parts = []
            if array.position_x is not None:
                position_parts.append(f"X: {array.position_x}")
            if array.position_y is not None:
                position_parts.append(f"Y: {array.position_y}")
            if array.position_z is not None:
                position_parts.append(f"Z: {array.position_z}")
            if position_parts:
                info_lines.append(f"<b>Position:</b> {', '.join(position_parts)}")
            
            # Bottom trim height
            if array.bottom_elevation is not None:
                feet = int(array.bottom_elevation)
                inches = int((float(array.bottom_elevation) - feet) * 12)
                info_lines.append(f"<b>Bottom Trim Height:</b> {feet}' {inches}\"")
            
            # Display array info
            for line in info_lines:
                elements.append(Paragraph(line, info_style))
            
            elements.append(Spacer(1, 0.08*inch))
            
            # Get cabinets for this array
            cabinets = array.cabinets.all().order_by('id')
            
            if cabinets.exists():
                # Determine which columns to include
                first_cabinet = cabinets[0]
                
                # Start with cabinet number
                headers = ['#']
                fields = []
                
                # Check for model field (could be speaker_model, cabinet_model, or model)
                if hasattr(first_cabinet, 'speaker_model') and first_cabinet.speaker_model:
                    headers.append('Model')
                    fields.append('speaker_model')
                elif hasattr(first_cabinet, 'cabinet_model') and first_cabinet.cabinet_model:
                    headers.append('Model')
                    fields.append('cabinet_model')
                elif hasattr(first_cabinet, 'model') and first_cabinet.model:
                    headers.append('Model')
                    fields.append('model')
                
                # Check for angle fields - ADD THIS FIRST
                if hasattr(first_cabinet, 'angle_to_next'):
                    headers.append('Angle')
                    fields.append('angle_to_next')
                elif hasattr(first_cabinet, 'site_angle'):
                    headers.append('Site Angle')
                    fields.append('site_angle')
                elif hasattr(first_cabinet, 'inter_cabinet_angle'):
                    headers.append('Angle')
                    fields.append('inter_cabinet_angle')
                elif hasattr(first_cabinet, 'angle'):
                    headers.append('Angle')
                    fields.append('angle')
                
                # Check for panflex - BEFORE distance
                if hasattr(first_cabinet, 'panflex_setting'):
                    headers.append('Panflex')
                    fields.append('panflex_setting')
                elif hasattr(first_cabinet, 'panflex'):
                    headers.append('Panflex')
                    fields.append('panflex')
                
                # Check for distance
                if hasattr(first_cabinet, 'distance'):
                    headers.append('Distance')
                    fields.append('distance')
                
                # Build table data
                table_data = [headers]
                
                for cab_idx, cabinet in enumerate(cabinets, 1):
                    row = [str(cab_idx)]
                    for field_name in fields:
                        value = getattr(cabinet, field_name, '')
                        
                        # Handle choice fields with get_FOO_display()
                        get_display_method = f'get_{field_name}_display'
                        if hasattr(cabinet, get_display_method):
                            display_value = getattr(cabinet, get_display_method)()
                            value = display_value if display_value else value
                        
                        # Format numeric values - handle Decimal, int, float
                        if value is not None and field_name in ['inter_cabinet_angle', 'angle', 'angle_to_next', 'site_angle']:
                            row.append(f"{value}°")
                        elif isinstance(value, (int, float, Decimal)) and value is not None:
                            row.append(str(value))
                        else:
                            row.append(str(value) if value else '')
                    
                    table_data.append(row)
                
                # Calculate column widths based on number of columns
                num_cols = len(headers)
                if num_cols == 2:  # # and Model only
                    col_widths = [0.5*inch, 6.5*inch]
                elif num_cols == 3:  # #, Model, Angle or Panflex
                    col_widths = [0.5*inch, 4*inch, 2*inch]
                elif num_cols == 4:  # #, Model, Angle, Panflex
                    col_widths = [0.5*inch, 3*inch, 1*inch, 2.5*inch]
                elif num_cols == 5:  # #, Model, Angle, Panflex, Distance
                    col_widths = [0.5*inch, 2.5*inch, 1*inch, 2*inch, 1*inch]
                else:
                    # Fallback for any other combination
                    first_col = 0.5*inch
                    remaining = 6.5*inch
                    other_cols = remaining / (num_cols - 1)
                    col_widths = [first_col] + [other_cols] * (num_cols - 1)
                
                # Create and style table
                cabinet_table = Table(table_data, colWidths=col_widths, repeatRows=1)
                cabinet_table.setStyle(cabinet_table_style)
                
                elements.append(cabinet_table)
            else:
                no_cabs = Paragraph("<i>No cabinets defined for this array</i>", info_style)
                elements.append(no_cabs)
            
            # Spacing between arrays
            if idx < len(arrays) - 1:
                elements.append(Spacer(1, 0.2*inch))
                
                # Page break every 4 arrays for better readability
                if (idx + 1) % 4 == 0:
                    elements.append(PageBreak())
    
    # Build PDF
    doc.build(elements)
    
    buf.seek(0)
    return buf