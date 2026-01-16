# planner/utils/pdf_exports/pa_cable_pdf.py

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
import math
from django.db.models import Sum

try:
    from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN, BRAND_BLUE, DARK_GRAY
except ImportError:
    # Fallback values if pdf_styles doesn't exist
    MARGIN = 0.5 * inch
    BRAND_BLUE = colors.HexColor('#4a9eff')
    DARK_GRAY = colors.HexColor('#333333')


def generate_pa_cable_pdf(queryset):
    """Generate PDF for PA Cable Schedule with cable runs and ordering summary."""
    
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN + 0.3*inch,
        bottomMargin=MARGIN + 0.3*inch,
    )
    
    # Create styles
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=BRAND_BLUE,
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Section header style
    section_style = ParagraphStyle(
        'CustomSection',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=BRAND_BLUE,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    
    # Table style
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # First column left-aligned
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, DARK_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    
    elements = []
    
    # Title
    title = Paragraph("PA CABLE SCHEDULE", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.2*inch))
    
    # Cable Runs Section
    if queryset.exists():
        # Section header
        header = Paragraph("Cable Runs", section_style)
        elements.append(header)
        elements.append(Spacer(1, 0.1*inch))
        
        # Cell style for wrapping text
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            fontName='Helvetica'
        )
        
        # Table data
        data = [['LABEL', 'DESTINATION', 'COUNT', 'LENGTH', 'CABLE TYPE', 'NOTES']]
        
        for cable in queryset:
            # Convert label (PAZone ForeignKey) to string
            label_text = str(cable.label) if cable.label else ''
            
            data.append([
                Paragraph(label_text, cell_style),
                Paragraph(cable.destination or '', cell_style),
                str(cable.count) if cable.count else '',
                f"{cable.length}'" if cable.length else '',
                cable.get_cable_display() if cable.cable else '',
                Paragraph(cable.notes or '', cell_style),
            ])
        
        # Create table
        col_widths = [2.2*inch, 1.8*inch, 0.5*inch, 0.6*inch, 1.0*inch, 2.4*inch]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(table_style)
        
        elements.append(t)
        elements.append(Spacer(1, 0.2*inch))
        
        # Fan Outs section (if any exist)
        fan_outs_exist = False
        for cable in queryset:
            if cable.fan_outs.exists():
                fan_outs_exist = True
                break
        
        if fan_outs_exist:
            header = Paragraph("Fan Outs by Cable", section_style)
            elements.append(header)
            elements.append(Spacer(1, 0.1*inch))
            
            fan_data = [['CABLE', 'FAN OUT TYPE', 'QUANTITY']]
            
            for cable in queryset:
                for fan_out in cable.fan_outs.all():
                    label_text = str(cable.label) if cable.label else f"Cable #{cable.id}"
                    fan_data.append([
                        label_text,
                        fan_out.get_fan_out_type_display(),
                        str(fan_out.quantity),
                    ])
            
            fan_col_widths = [2*inch, 2*inch, 1*inch]
            ft = Table(fan_data, colWidths=fan_col_widths, repeatRows=1)
            ft.setStyle(table_style)
            
            elements.append(ft)
    
    # Page break before Quick Order List
    elements.append(PageBreak())
    
    # Quick Order List Section
    header = Paragraph("QUICK ORDER LIST", title_style)
    elements.append(header)
    elements.append(Spacer(1, 0.2*inch))
    
    # Calculate cable summary using the same logic as changelist_view
    from planner.models import PACableSchedule
    
    # Build Quick Order List data (simple 3-column format matching web page)
    quick_order_data = [['ITEM TYPE', 'LENGTH', 'ORDER QTY']]
    
    # Process cables by type
    for cable_type in PACableSchedule.CABLE_TYPE_CHOICES:
        cables = queryset.filter(cable=cable_type[0])
        if cables.exists():
            # Calculate cables needed at each standard length
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
            
            # Apply 20% safety margin
            hundreds_safe = math.ceil(hundreds * 1.2) if hundreds > 0 else 0
            fifties_safe = math.ceil(fifties * 1.2) if fifties > 0 else 0
            twenty_fives_safe = math.ceil(twenty_fives * 1.2) if twenty_fives > 0 else 0
            tens_safe = math.ceil(tens * 1.2) if tens > 0 else 0
            fives_safe = math.ceil(fives * 1.2) if fives > 0 else 0
            
            cable_name = cable_type[1]  # Display name
            
            # Add rows for each length that has quantities
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
    
    # Add fan outs to Quick Order List
    fan_out_summary = {}
    for cable in queryset.prefetch_related('fan_outs'):
        for fan_out in cable.fan_outs.all():
            fan_out_name = fan_out.get_fan_out_type_display()
            if fan_out_name not in fan_out_summary:
                fan_out_summary[fan_out_name] = 0
            fan_out_summary[fan_out_name] += fan_out.quantity
    
    # Add fan outs with 20% safety
    for fan_out_type, total_qty in fan_out_summary.items():
        qty_with_safety = math.ceil(total_qty * 1.2)
        quick_order_data.append([fan_out_type, "Fan Out", str(qty_with_safety)])
    
    # Create table if we have data
    if len(quick_order_data) > 1:
        col_widths = [3*inch, 1.5*inch, 1.5*inch]
        qt = Table(quick_order_data, colWidths=col_widths, repeatRows=1)
        qt.setStyle(table_style)
        
        elements.append(qt)
        elements.append(Spacer(1, 0.3*inch))
    
    # Add note about safety margin
    note_style = ParagraphStyle(
        'Note',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        fontName='Helvetica-Oblique'
    )
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