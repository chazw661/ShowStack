# planner/utils/pdf_exports/pa_cable_pdf.py

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
import math

try:
    from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN, BRAND_BLUE, DARK_GRAY
except ImportError:
    MARGIN = 0.5 * inch
    BRAND_BLUE = colors.HexColor('#4a9eff')
    DARK_GRAY = colors.HexColor('#333333')


def generate_pa_cable_pdf(queryset):
    """Generate PDF for PA Cable Schedule matching the admin list view layout."""
    
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN + 0.3*inch,
        bottomMargin=MARGIN + 0.3*inch,
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=BRAND_BLUE,
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    section_style = ParagraphStyle(
        'CustomSection',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=BRAND_BLUE,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
        fontName='Helvetica'
    )
    
    cell_style_bold = ParagraphStyle(
        'CellStyleBold',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
        fontName='Helvetica-Bold'
    )
    
    note_style = ParagraphStyle(
        'Note',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        fontName='Helvetica-Oblique'
    )
    
    elements = []
    
    # ==================== CABLE LIST ====================
    title = Paragraph("PA CABLE SCHEDULE", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.2*inch))
    
    if queryset.exists():
        # Header row matching admin list view
        data = [['LABEL', 'DESTINATION', 'COUNT', 'LENGTH', 'CABLE', 'FAN OUTS', 'NOTES', 'DWG REF', 'COLOR']]
        
        # Track colors for row styling
        row_colors = [None]  # None for header row
        
        for cable in queryset.prefetch_related('fan_outs'):
            label_text = str(cable.label) if cable.label else '-'
            destination = cable.destination or '-'
            count = str(cable.count) if cable.count else '1'
            length = f"{cable.length}'" if cable.length else '-'
            cable_type = cable.get_cable_display() if cable.cable else '-'
            fan_out = cable.fan_out_summary or '-'
            notes = cable.notes or '-'
            drawing_ref = cable.drawing_ref or '-'
            
            data.append([
                Paragraph(label_text, cell_style_bold),
                Paragraph(destination, cell_style),
                count,
                length,
                cable_type,
                Paragraph(fan_out, cell_style),
                Paragraph(notes, cell_style),
                Paragraph(drawing_ref, cell_style),
                '',  # Color column - filled by cell background
            ])
            
            row_colors.append(cable.color if cable.color else None)
        
        # Column widths matching admin layout proportions
        col_widths = [1.1*inch, 1.3*inch, 0.5*inch, 0.6*inch, 0.8*inch, 1.4*inch, 2.2*inch, 0.7*inch, 0.4*inch]
        
        t = Table(data, colWidths=col_widths, repeatRows=1)
        
        # Base table style
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),   # Label left
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),   # Destination left
            ('ALIGN', (5, 1), (5, -1), 'LEFT'),   # Fan outs left
            ('ALIGN', (6, 1), (6, -1), 'LEFT'),   # Notes left
            ('ALIGN', (7, 1), (7, -1), 'LEFT'),   # Drawing ref left
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, DARK_GRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # Alternating row colors
        ]
        
        # Add alternating row backgrounds and color column fills
        for i in range(1, len(data)):
            # Alternating base color
            if i % 2 == 0:
                style_commands.append(('BACKGROUND', (0, i), (-2, i), colors.HexColor('#f5f5f5')))
            else:
                style_commands.append(('BACKGROUND', (0, i), (-2, i), colors.white))
            
            # Color swatch in last column
            if row_colors[i]:
                try:
                    style_commands.append(('BACKGROUND', (-1, i), (-1, i), colors.HexColor(row_colors[i])))
                except ValueError:
                    pass
        
        t.setStyle(TableStyle(style_commands))
        elements.append(t)
    
    # ==================== QUICK ORDER LIST ====================
    elements.append(Spacer(1, 0.4*inch))
    
    header = Paragraph("QUICK ORDER LIST", section_style)
    elements.append(header)
    elements.append(Spacer(1, 0.1*inch))
    
    quick_order_data = [['ITEM TYPE', 'LENGTH', 'ORDER QTY']]
    
    from planner.models import PACableSchedule
    
    for cable_type in PACableSchedule.CABLE_TYPE_CHOICES:
        cables = queryset.filter(cable=cable_type[0])
        if cables.exists():
            hundreds = 0
            fifties = 0
            twenty_fives = 0
            tens = 0
            fives = 0
            
            for cable in cables:
                cable_length = cable.length or 0
                cable_count = cable.count or 0
                
                for _ in range(cable_count):
                    remaining = cable_length
                    while remaining > 0:
                        if remaining > 50:
                            hundreds += 1
                            remaining -= 100
                        elif remaining > 25:
                            fifties += 1
                            remaining -= 50
                        elif remaining > 10:
                            twenty_fives += 1
                            remaining -= 25
                        elif remaining > 5:
                            tens += 1
                            remaining -= 10
                        elif remaining > 0:
                            fives += 1
                            remaining -= 5
            
            hundreds_safe = math.ceil(hundreds * 1.2) if hundreds > 0 else 0
            fifties_safe = math.ceil(fifties * 1.2) if fifties > 0 else 0
            twenty_fives_safe = math.ceil(twenty_fives * 1.2) if twenty_fives > 0 else 0
            tens_safe = math.ceil(tens * 1.2) if tens > 0 else 0
            fives_safe = math.ceil(fives * 1.2) if fives > 0 else 0
            
            cable_name = cable_type[1]
            
            if hundreds_safe > 0:
                quick_order_data.append([cable_name, "100'", str(hundreds_safe)])
            if fifties_safe > 0:
                quick_order_data.append([cable_name, "50'", str(fifties_safe)])
            if twenty_fives_safe > 0:
                quick_order_data.append([cable_name, "25'", str(twenty_fives_safe)])
            if tens_safe > 0:
                quick_order_data.append([cable_name, "10'", str(tens_safe)])
            if fives_safe > 0:
                quick_order_data.append([cable_name, "5'", str(fives_safe)])

    # Add extension cables to quick order totals
    for cable in queryset.prefetch_related('fan_outs'):
        for fan_out in cable.fan_outs.all():
            if fan_out.extension_cable and fan_out.extension_length:
                ext_cable_map = {
                    'NL4': 'NL 4',
                    'NL8': 'NL 8',
                }
                cable_name = ext_cable_map.get(fan_out.extension_cable, fan_out.extension_cable)
                ext_length = fan_out.extension_length
                ext_qty = fan_out.quantity
                
                length_label = f"{ext_length}'"
                safe_qty = math.ceil(ext_qty * 1.2)
                
                # Check if this cable+length already exists in quick_order_data
                found = False
                for row in quick_order_data[1:]:  # Skip header
                    if row[0] == cable_name and row[1] == length_label:
                        row[2] = str(int(row[2]) + safe_qty)
                        found = True
                        break
                if not found:
                    quick_order_data.append([cable_name, length_label, str(safe_qty)])            
    
    # Add fan outs to Quick Order List
    fan_out_summary = {}
    for cable in queryset.prefetch_related('fan_outs'):
        for fan_out in cable.fan_outs.all():
            fan_out_name = fan_out.get_fan_out_type_display()
            if fan_out_name not in fan_out_summary:
                fan_out_summary[fan_out_name] = 0
            fan_out_summary[fan_out_name] += fan_out.quantity
    
    for fan_out_type, total_qty in fan_out_summary.items():
        qty_with_safety = math.ceil(total_qty * 1.2)
        quick_order_data.append([fan_out_type, "Fan Out", str(qty_with_safety)])
    
    if len(quick_order_data) > 1:
        # Quick order table style
        qo_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, DARK_GRAY),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # Green highlight for order qty column
            ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#e8f5e9')),
            ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#2e7d32')),
            ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
        ])
        
        # Alternating rows
        for i in range(1, len(quick_order_data)):
            if i % 2 == 0:
                qo_style.add('BACKGROUND', (0, i), (1, i), colors.HexColor('#f5f5f5'))
            else:
                qo_style.add('BACKGROUND', (0, i), (1, i), colors.white)
        
        col_widths = [3*inch, 1.5*inch, 1.5*inch]
        qt = Table(quick_order_data, colWidths=col_widths, repeatRows=1)
        qt.setStyle(qo_style)
        
        elements.append(qt)
        elements.append(Spacer(1, 0.3*inch))
    
    note = Paragraph(
        "<i>Note: All quantities include a 20% safety margin for temporary installations.</i>",
        note_style
    )
    elements.append(note)
    
    # Build PDF
    doc.build(elements)
    
    pdf = buf.getvalue()
    buf.close()
    return pdf