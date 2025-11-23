# planner/utils/pdf_exports/comm_pdf.py

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from io import BytesIO
from itertools import groupby

from .pdf_styles import PDFStyles, MARGIN, BRAND_BLUE, DARK_GRAY


def get_channel_abbrev(channel):
    """Helper function to extract abbreviation from channel name."""
    if not channel:
        return ''
    # Try to get abbreviation field first
    if hasattr(channel, 'abbreviation') and channel.abbreviation:
        return str(channel.abbreviation)
    # Extract abbreviation from parentheses
    channel_str = str(channel)
    # Find text between parentheses
    if '(' in channel_str and ')' in channel_str:
        start = channel_str.find('(')
        end = channel_str.find(')')
        abbrev = channel_str[start+1:end].strip()
        return abbrev  # Returns "PROD", "GFX", etc.
    # Fallback to first 4 characters
    return channel_str[:4].upper()


def generate_comm_beltpacks_pdf():
    """Generate PDF for all Comm Belt Packs grouped by system type and manufacturer."""
    from planner.models import CommBeltPack
    
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),  # Use landscape for more channel columns
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
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, DARK_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])
    
   # Cell styles
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles.styles['Normal'],
        fontSize=6,
        leading=8,
        alignment=TA_LEFT
    )
    
    cell_style_center = ParagraphStyle(
        'CellTextCenter',
        parent=styles.styles['Normal'],
        fontSize=6,
        leading=8,
        alignment=TA_CENTER
    )
    
    # NEW: Bold style for position
    cell_style_bold = ParagraphStyle(
        'CellTextBold',
        parent=styles.styles['Normal'],
        fontSize=7,  # Slightly larger
        leading=9,
        fontName='Helvetica-Bold',
        alignment=TA_LEFT
    )
    
    # Process by system type and manufacturer
    first_section = True
    for system_type, type_name in [('HARDWIRED', 'Hardwired'), ('WIRELESS', 'Wireless')]:
        # Get all belt packs for this type
        bps = CommBeltPack.objects.filter(
            system_type=system_type
        ).order_by('manufacturer', 'bp_number').prefetch_related('channels__channel')
        
        if not bps.exists():
            continue
        
        # Add page break before new section (except first)
        if not first_section:
            elements.append(PageBreak())
        first_section = False
            
        # Section header
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles.styles['Heading2'],
            fontSize=14,
            textColor=BRAND_BLUE,
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        section_header = Paragraph(f"<b>{type_name} Systems</b>", section_style)
        
        # Create a list to hold this section's content
        section_elements = [section_header, Spacer(1, 0.1*inch)]
        
        # Group by manufacturer - use Python grouping instead of multiple queries
        for manufacturer, group in groupby(bps, key=lambda x: x.manufacturer):
            manufacturer_bps = list(group)  # Convert iterator to list
            
            # Manufacturer subheader
            mfr_name = dict(CommBeltPack.MANUFACTURER_CHOICES).get(manufacturer, manufacturer)
            mfr_style = ParagraphStyle(
                'MfrHeader',
                parent=styles.styles['Heading3'],
                fontSize=11,
                textColor=BRAND_BLUE,
                spaceAfter=6,
                spaceBefore=8,
                fontName='Helvetica-Bold'
            )
            mfr_header = Paragraph(f"<b>{mfr_name}</b>", mfr_style)
            
            # Create list for this manufacturer's content
            mfr_elements = [mfr_header, Spacer(1, 0.05*inch)]
            
            # Determine max channels needed for this group
            max_channels = 0
            for bp in manufacturer_bps:
                channel_count = bp.channels.count()
                if channel_count > max_channels:
                    max_channels = channel_count
            
            # Cap at 10 channels for reasonable PDF width
            max_channels = min(max_channels, 10)
            
           # Build table headers - simplified for basic info only
            headers = ['BP#', 'SYSTEM', 'POS', 'NAME', 'HEADSET', 'CHANNELS', 'IP', 'GRP']
            
            data = [headers]
            
            # Track which belt packs need detailed channel sections
            detailed_bps = []
            
            # Add data rows
            for bp in manufacturer_bps:
                # Get all channels for this belt pack
                channels = list(bp.channels.all().order_by('channel_number'))
                
                # Create channel summary
                if len(channels) == 0:
                    channel_summary = '—'
                elif len(channels) <= 10:
                    # Show inline for simple belt packs (4 or fewer channels)
                    ch_list = []
                    for ch in channels:
                        if ch.channel:
                            abbrev = get_channel_abbrev(ch.channel)
                            ch_list.append(f"{ch.channel_number}:{abbrev}")
                    channel_summary = ' '.join(ch_list)
                else:
                    # Just show count for complex belt packs, details below
                    channel_summary = f"{len(channels)} channels (see below)"
                    detailed_bps.append(bp)
                
                row = [
                    Paragraph(str(bp.bp_number) if bp.bp_number else '', cell_style_center),
                    Paragraph(dict(CommBeltPack.MANUFACTURER_CHOICES).get(bp.manufacturer, '')[:12], cell_style),
                    Paragraph(str(bp.position) if bp.position else '', cell_style_bold),  # Changed to cell_style_bold
                    Paragraph(str(bp.name) if bp.name else '', cell_style),
                    Paragraph(bp.get_headset_display() if bp.headset else '', cell_style_center),
                    Paragraph(channel_summary, cell_style),
                    Paragraph(str(bp.ip_address) if bp.ip_address else '', cell_style_center),
                    Paragraph(bp.get_group_display() if bp.group else '', cell_style_center),
                ]
                
                data.append(row)
            
            # Calculate column widths
            col_widths = [
                0.4*inch,   # BP#
                0.9*inch,   # SYSTEM
                0.9*inch,   # POS
                1.5*inch,   # NAME
                0.6*inch,   # HEADSET
                2.5*inch,   # CHANNELS
                0.9*inch,   # IP
                0.5*inch,   # GRP
            ]
            
            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(compact_style)
            
            mfr_elements.append(t)
            
           # Add detailed channel listings for complex belt packs
            if detailed_bps:
                mfr_elements.append(Spacer(1, 0.2*inch))
                
                # Create a background box for the details section
                detail_box_data = []
                
                # Detail section header
                detail_style = ParagraphStyle(
                    'DetailHeader',
                    parent=styles.styles['Normal'],
                    fontSize=9,
                    textColor=colors.HexColor('#1a5490'),  # Darker blue
                    spaceAfter=6,
                    spaceBefore=4,
                    fontName='Helvetica-Bold'
                )
                detail_header = Paragraph("<b>Channel Details:</b>", detail_style)
                
                # Create detail style for channel lists
                channel_detail_style = ParagraphStyle(
                    'ChannelDetail',
                    parent=styles.styles['Normal'],
                    fontSize=7,
                    leading=10,
                    leftIndent=0.1*inch,
                    spaceAfter=6
                )
                
                # Collect all detail paragraphs
                detail_paragraphs = [detail_header, Spacer(1, 0.05*inch)]
                
                for bp in detailed_bps:
                    channels = list(bp.channels.all().order_by('channel_number'))
                    
                    # Belt pack identifier
                    bp_id = f"<b>BP #{bp.bp_number}</b>"
                    if bp.position:
                        bp_id += f" - <b>{bp.position}</b>"
                    if bp.name:
                        bp_id += f" - {bp.name}"
                    
                    bp_para = Paragraph(bp_id, channel_detail_style)
                    detail_paragraphs.append(bp_para)
                    
                    # Build channel list in rows of 10
                    channel_lines = []
                    for i in range(0, len(channels), 10):
                        row_channels = channels[i:i+10]
                        ch_parts = []
                        for ch in row_channels:
                            if ch.channel:
                                abbrev = get_channel_abbrev(ch.channel)
                                ch_parts.append(f"{ch.channel_number}:{abbrev}")
                        if ch_parts:
                            channel_lines.append("   " + "   ".join(ch_parts))
                    
                    channel_text = "<br/>".join(channel_lines)
                    channel_para = Paragraph(channel_text, channel_detail_style)
                    detail_paragraphs.append(channel_para)
                    detail_paragraphs.append(Spacer(1, 0.08*inch))
                
                # Create a table with single cell to add background
                detail_table = Table([[detail_paragraphs]], colWidths=[9*inch])
                detail_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),  # Light gray
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),  # Subtle border
                ]))
                
                mfr_elements.append(detail_table)
            
            # Keep manufacturer header and table together
            section_elements.append(KeepTogether(mfr_elements))
        
        # Add the entire section (keeps section header with at least first manufacturer)
        elements.extend(section_elements)
    
    # Build PDF
    doc.build(
        elements,
        onFirstPage=styles.add_page_number,
        onLaterPages=styles.add_page_number
    )
    
    pdf = buf.getvalue()
    buf.close()
    return pdf