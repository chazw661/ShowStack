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
        
        # Table data
        data = [['LABEL', 'DESTINATION', 'COUNT', 'LENGTH', 'CABLE TYPE', 'NOTES', 'DRAWING REF']]
        
        for cable in queryset.order_by('id'):
            data.append([
                cable.label or '',
                cable.destination or '',
                str(cable.count) if cable.count else '',
                f"{cable.length}'" if cable.length else '',
                cable.get_cable_display() if cable.cable else '',
                cable.notes or '',
                cable.drawing_ref or '',
            ])
        
        # Create table
        col_widths = [1.8*inch, 1.6*inch, 0.5*inch, 0.6*inch, 1.2*inch, 2.0*inch, 0.8*inch]
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
            
            for cable in queryset.order_by('id'):
                for fan_out in cable.fan_outs.all():
                    fan_data.append([
                        cable.label or f"Cable #{cable.id}",
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
    
    # Calculate cable summary (replicate the logic from changelist_view)
    from planner.models import PACableSchedule
    
    cable_summary = {}
    for cable_type in PACableSchedule.CABLE_TYPE_CHOICES:
        cables = queryset.filter(cable=cable_type[0])
        if cables.exists():
            total_length = sum(c.total_cable_length for c in cables)
            if total_length > 0:
                # Calculate standard cable quantities needed
                hundreds = int(total_length / 100)
                remaining = total_length % 100
                
                # Round up remaining to next standard length
                fifties = 0
                twenty_fives = 0
                tens = 0
                fives = 0
                
                if remaining > 0:
                    if remaining > 50:
                        hundreds += 1
                    elif remaining > 25:
                        fifties = 1
                    elif remaining > 10:
                        twenty_fives = 1
                    elif remaining > 5:
                        tens = 1
                    elif remaining > 0:
                        fives = 1
                
                cable_summary[cable_type[1]] = {
                    'total_runs': cables.aggregate(Sum('count'))['count__sum'] or 0,
                    'total_length': total_length,
                    'hundreds': hundreds,
                    'hundreds_with_safety': math.ceil(hundreds * 1.2),
                    'fifties': fifties,
                    'fifties_with_safety': math.ceil(fifties * 1.2),
                    'twenty_fives': twenty_fives,
                    'twenty_fives_with_safety': math.ceil(twenty_fives * 1.2),
                    'tens': tens,
                    'tens_with_safety': math.ceil(tens * 1.2),
                    'fives': fives,
                    'fives_with_safety': math.ceil(fives * 1.2),
                    'couplers': hundreds - 1 if hundreds > 1 else 0,
                }
    
    # Cable Summary Table
    if cable_summary:
        sec_header = Paragraph("Cable Orders (with 20% safety margin)", section_style)
        elements.append(sec_header)
        elements.append(Spacer(1, 0.1*inch))
        
        cable_data = [['CABLE TYPE', '100\' QTY', '50\' QTY', '25\' QTY', '10\' QTY', '5\' QTY', 'COUPLERS']]
        
        for cable_type, data in cable_summary.items():
            cable_data.append([
                cable_type,
                str(data['hundreds_with_safety']) if data['hundreds_with_safety'] > 0 else '-',
                str(data['fifties_with_safety']) if data['fifties_with_safety'] > 0 else '-',
                str(data['twenty_fives_with_safety']) if data['twenty_fives_with_safety'] > 0 else '-',
                str(data['tens_with_safety']) if data['tens_with_safety'] > 0 else '-',
                str(data['fives_with_safety']) if data['fives_with_safety'] > 0 else '-',
                str(data['couplers']) if data['couplers'] > 0 else '-',
            ])
        
        cable_col_widths = [1.5*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch]
        ct = Table(cable_data, colWidths=cable_col_widths, repeatRows=1)
        ct.setStyle(table_style)
        
        elements.append(ct)
        elements.append(Spacer(1, 0.3*inch))
    
    # Calculate fan out summary
    fan_out_summary = {}
    for cable in queryset.prefetch_related('fan_outs'):
        for fan_out in cable.fan_outs.all():
            fan_out_name = fan_out.get_fan_out_type_display()
            if fan_out_name not in fan_out_summary:
                fan_out_summary[fan_out_name] = {
                    'total_quantity': 0,
                    'with_overage': 0
                }
            fan_out_summary[fan_out_name]['total_quantity'] += fan_out.quantity
    
    # Calculate 20% overage for each fan out type
    for fan_out_type in fan_out_summary:
        total = fan_out_summary[fan_out_type]['total_quantity']
        fan_out_summary[fan_out_type]['with_overage'] = math.ceil(total * 1.2)
    
    # Fan Out Summary Table
    if fan_out_summary:
        sec_header = Paragraph("Fan Out Orders (with 20% safety margin)", section_style)
        elements.append(sec_header)
        elements.append(Spacer(1, 0.1*inch))
        
        fan_data = [['FAN OUT TYPE', 'ORDER QTY']]
        
        for fan_out_type, data in fan_out_summary.items():
            fan_data.append([
                fan_out_type,
                str(data['with_overage']),
            ])
        
        fan_col_widths = [2*inch, 1*inch]
        ft = Table(fan_data, colWidths=fan_col_widths, repeatRows=1)
        ft.setStyle(table_style)
        
        elements.append(ft)
        elements.append(Spacer(1, 0.2*inch))
    
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