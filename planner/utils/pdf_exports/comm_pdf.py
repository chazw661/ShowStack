# planner/utils/pdf_exports/comm_pdf.py

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from io import BytesIO

from .pdf_styles import PDFStyles, MARGIN, BRAND_BLUE, DARK_GRAY


def get_channel_abbrev(channel):
    """Helper function to extract abbreviation from channel name."""
    if not channel:
        return ''
    # Try to get bp_number first
    if hasattr(channel, 'bp_number') and channel.bp_number:
        return str(channel.bp_number)
    # Extract abbreviation from parentheses
    channel_str = str(channel)
    # Find text between parentheses
    if '(' in channel_str and ')' in channel_str:
        start = channel_str.find('(')
        end = channel_str.find(')')
        abbrev = channel_str[start+1:end].strip()
        return abbrev  # Returns "PROD", "GFX", etc.
    # Fallback
    return channel_str[:4]


def generate_comm_beltpacks_pdf():
    """Generate PDF for all Comm Belt Packs grouped by system type."""
    from planner.models import CommBeltPack
    
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,  # Portrait
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN + 0.3*inch,
        bottomMargin=MARGIN + 0.3*inch,
    )
    
    styles = PDFStyles()
    elements = []
    
    # Title
    title = Paragraph("COMM BELT PACKS", styles.get_section_style())
    elements.append(title)
    elements.append(Spacer(1, 0.2*inch))
    
    # Compact table style
    compact_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, DARK_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])
    
    # Process Hardwired and Wireless separately
    for system_type, type_name in [('HARDWIRED', 'Hardwired'), ('WIRELESS', 'Wireless')]:
        # Section header
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles.styles['Heading2'],
            fontSize=14,
            textColor=BRAND_BLUE,
            spaceAfter=8,
            fontName='Helvetica-Bold'
        )
        section_header = Paragraph(f"<b>{type_name}</b>", section_style)
        elements.append(section_header)
        elements.append(Spacer(1, 0.1*inch))
        
        # Get belt packs for this type
        bps = CommBeltPack.objects.filter(system_type=system_type).order_by('unit_location', 'position')
        
        if bps.exists():
            # Create paragraph styles for cell text
            cell_style = ParagraphStyle(
                'CellText',
                parent=styles.styles['Normal'],
                fontSize=7,
                leading=9,
                alignment=TA_LEFT
            )
            
            cell_style_center = ParagraphStyle(
                'CellTextCenter',
                parent=styles.styles['Normal'],
                fontSize=7,
                leading=9,
                alignment=TA_CENTER
            )
            
                        # Table headers
            data = [[
                'BP #',      # Changed from 'UNIT'
                'POSITION',
                'NAME',
                'HEADSET',
                'CH A',
                'CH B',
                'CH C',
                'CH D',
                'GROUP',
            ]]
            
            # Add data rows with Paragraph objects for text wrapping
            for bp in bps:
                data.append([
                    Paragraph(str(bp.bp_number) if bp.bp_number else '', cell_style_center),
                    Paragraph(bp.position or '', cell_style),
                    Paragraph(bp.name or '', cell_style),
                    Paragraph(bp.get_headset_display() if bp.headset else '', cell_style_center),
                    Paragraph(get_channel_abbrev(bp.channel_a), cell_style_center),
                    Paragraph(get_channel_abbrev(bp.channel_b), cell_style_center),
                    Paragraph(get_channel_abbrev(bp.channel_c), cell_style_center),
                    Paragraph(get_channel_abbrev(bp.channel_d), cell_style_center),
                    Paragraph(bp.get_group_display() if bp.group else '', cell_style_center),
                ])
            
            # Column widths for portrait
            # Column widths for portrait
                col_widths = [
                    0.5*inch,   # UNIT
                    1.0*inch,   # POSITION
                    1.8*inch,   # NAME (reduced from 2.5)
                    0.8*inch,   # HEADSET
                    0.6*inch,   # CH A (wider from 0.4)
                    0.6*inch,   # CH B (wider from 0.4)
                    0.6*inch,   # CH C (wider from 0.4)
                    0.6*inch,   # CH D (wider from 0.4)
                    0.7*inch,   # GROUP
                ]
# Total = 7.6 inches (fits well in 8" available portrait width)
            
            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(compact_style)
            
            elements.append(t)
            elements.append(Spacer(1, 0.3*inch))
        else:
            # No belt packs for this type
            no_data = Paragraph(f"<i>No {type_name.lower()} belt packs configured</i>", styles.styles['Normal'])
            elements.append(no_data)
            elements.append(Spacer(1, 0.3*inch))
    
    # Build PDF
    doc.build(
        elements,
        onFirstPage=styles.add_page_number,
        onLaterPages=styles.add_page_number
    )
    
    pdf = buf.getvalue()
    buf.close()
    return pdf