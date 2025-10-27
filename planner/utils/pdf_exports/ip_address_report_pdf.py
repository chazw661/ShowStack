# planner/utils/pdf_exports/ip_address_report_pdf.py

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from io import BytesIO
from datetime import datetime

try:
    from .pdf_styles import MARGIN, BRAND_BLUE, DARK_GRAY
except ImportError:
    # Fallback values if pdf_styles doesn't exist
    MARGIN = 0.5 * inch
    BRAND_BLUE = colors.HexColor('#4a9eff')
    DARK_GRAY = colors.HexColor('#333333')


def generate_ip_address_report_pdf():
    """
    Generate comprehensive IP Address Report PDF for all modules.
    Lists all IP addresses organized by module type with summary.
    
    Returns:
        BytesIO buffer containing the PDF
    """
    from django.apps import apps
    
    # Get models
    Console = apps.get_model('planner', 'Console')
    Device = apps.get_model('planner', 'Device')
    Amp = apps.get_model('planner', 'Amp')
    SystemProcessor = apps.get_model('planner', 'SystemProcessor')
    CommBeltPack = apps.get_model('planner', 'CommBeltPack')
    
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
        fontSize=20,
        textColor=DARK_GRAY,
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    section_style = ParagraphStyle(
        'CustomSection',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=BRAND_BLUE,
        spaceAfter=8,
        spaceBefore=16,
        fontName='Helvetica-Bold'
    )
    
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    
    # Title
    title = Paragraph("IP ADDRESS REPORT", title_style)
    elements.append(title)
    
    # Generated timestamp
    timestamp = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    info = Paragraph(f"Generated: {timestamp}", info_style)
    elements.append(info)
    elements.append(Spacer(1, 0.3*inch))
    
    # Table style for IP listings
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
    ])
    
    # ==================== CONSOLES ====================
    section = Paragraph("MIXING CONSOLES", section_style)
    elements.append(section)
    
    consoles = Console.objects.all().order_by('name')
    
    if consoles.exists():
        console_data = [['Console Name', 'Primary IP Address', 'Secondary IP Address']]
        
        for console in consoles:
            primary_ip = console.primary_ip_address if console.primary_ip_address else '—'
            secondary_ip = console.secondary_ip_address if console.secondary_ip_address else '—'
            
            console_data.append([
                console.name,
                primary_ip,
                secondary_ip
            ])
        
        console_table = Table(console_data, colWidths=[2.5*inch, 2*inch, 2*inch])
        console_table.setStyle(table_style)
        elements.append(console_table)
    else:
        no_data = Paragraph("<i>No consoles defined</i>", info_style)
        elements.append(no_data)
    
    elements.append(Spacer(1, 0.2*inch))
    
    # ==================== I/O DEVICES ====================
    section = Paragraph("I/O DEVICES", section_style)
    elements.append(section)
    
    devices = Device.objects.all().order_by('name')
    
    if devices.exists():
        device_data = [['Device Name', 'Primary IP Address', 'Secondary IP Address']]
        
        for device in devices:
            primary_ip = device.primary_ip_address if device.primary_ip_address else '—'
            secondary_ip = device.secondary_ip_address if device.secondary_ip_address else '—'
            
            device_data.append([
                device.name,
                primary_ip,
                secondary_ip
            ])
        
        device_table = Table(device_data, colWidths=[2.5*inch, 2*inch, 2*inch])
        device_table.setStyle(table_style)
        elements.append(device_table)
    else:
        no_data = Paragraph("<i>No I/O devices defined</i>", info_style)
        elements.append(no_data)
    
    elements.append(Spacer(1, 0.2*inch))
    
    # ==================== AMPLIFIERS ====================
    section = Paragraph("AMPLIFIERS", section_style)
    elements.append(section)
    
    amps = Amp.objects.all().order_by('location__name', 'name')
    
    if amps.exists():
        amp_data = [['Amplifier Name', 'Location', 'IP Address (AVB Network)']]
        
        for amp in amps:
            ip = amp.ip_address if hasattr(amp, 'ip_address') and amp.ip_address else '—'
            location = amp.location.name if amp.location else 'No Location'
            
            amp_data.append([
                amp.name,
                location,
                ip
            ])
        
        amp_table = Table(amp_data, colWidths=[2.5*inch, 2*inch, 2*inch])
        amp_table.setStyle(table_style)
        elements.append(amp_table)
    else:
        no_data = Paragraph("<i>No amplifiers defined</i>", info_style)
        elements.append(no_data)
    
    elements.append(Spacer(1, 0.2*inch))
    
    # ==================== SYSTEM PROCESSORS ====================
    section = Paragraph("SYSTEM PROCESSORS", section_style)
    elements.append(section)
    
    processors = SystemProcessor.objects.all().order_by('device_type', 'name')
    
    if processors.exists():
        processor_data = [['Processor Name', 'Type', 'IP Address (AVB Network)']]
        
        for processor in processors:
            ip = processor.ip_address if hasattr(processor, 'ip_address') and processor.ip_address else '—'
            device_type = processor.get_device_type_display() if hasattr(processor, 'get_device_type_display') else processor.device_type
            
            processor_data.append([
                processor.name,
                device_type,
                ip
            ])
        
        processor_table = Table(processor_data, colWidths=[2.5*inch, 2*inch, 2*inch])
        processor_table.setStyle(table_style)
        elements.append(processor_table)
    else:
        no_data = Paragraph("<i>No system processors defined</i>", info_style)
        elements.append(no_data)
    
    elements.append(Spacer(1, 0.2*inch))
    
    # ==================== COMM BELT PACKS (HARDWIRED) ====================
    section = Paragraph("COMM BELT PACKS (HARDWIRED)", section_style)
    elements.append(section)
    
    belt_packs = CommBeltPack.objects.filter(system_type='HARDWIRED').order_by('bp_number')
    
    if belt_packs.exists():
        bp_data = [['BP #', 'Position', 'Name', 'IP Address']]
        
        for bp in belt_packs:
            ip = bp.ip_address if hasattr(bp, 'ip_address') and bp.ip_address else '—'
            position = bp.position if bp.position else '—'
            name = bp.name if bp.name else '—'
            
            bp_data.append([
                f"BP{bp.bp_number}",
                position,
                name,
                ip
            ])
        
        bp_table = Table(bp_data, colWidths=[0.75*inch, 2*inch, 2*inch, 1.75*inch])
        bp_table.setStyle(table_style)
        elements.append(bp_table)
    else:
        no_data = Paragraph("<i>No hardwired belt packs defined</i>", info_style)
        elements.append(no_data)
    
    elements.append(Spacer(1, 0.2*inch))
    
    # ==================== SUMMARY ====================
    elements.append(Spacer(1, 0.3*inch))
    section = Paragraph("SUMMARY", section_style)
    elements.append(section)
    
    # Count total IP addresses
    console_ips = sum([
        1 if c.primary_ip_address else 0 for c in consoles
    ] + [
        1 if c.secondary_ip_address else 0 for c in consoles
    ])
    
    device_ips = sum([
        1 if d.primary_ip_address else 0 for d in devices
    ] + [
        1 if d.secondary_ip_address else 0 for d in devices
    ])
    
    amp_ips = sum([
        1 if hasattr(a, 'ip_address') and a.ip_address else 0 for a in amps
    ])
    
    processor_ips = sum([
        1 if hasattr(p, 'ip_address') and p.ip_address else 0 for p in processors
    ])
    
    bp_ips = sum([
        1 if hasattr(bp, 'ip_address') and bp.ip_address else 0 for bp in belt_packs
    ])
    
    total_ips = console_ips + device_ips + amp_ips + processor_ips + bp_ips
    
    summary_data = [
        ['Module', 'IP Addresses Assigned'],
        ['Mixing Consoles', str(console_ips)],
        ['I/O Devices', str(device_ips)],
        ['Amplifiers', str(amp_ips)],
        ['System Processors', str(processor_ips)],
        ['COMM Belt Packs (Hardwired)', str(bp_ips)],
        ['TOTAL', str(total_ips)]
    ]
    
    summary_table = Table(summary_data, colWidths=[4*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('BACKGROUND', (0, -1), (-1, -1), colors.Color(0.9, 0.9, 0.9)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(summary_table)
    
    # Build PDF
    doc.build(elements)
    
    buf.seek(0)
    return buf