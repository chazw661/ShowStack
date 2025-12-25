# planner/utils/pdf_exports/location_pdf.py
"""
Location PDF Export - Equipment listing by location
Shows all equipment assigned to each location, grouped by module
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, PageBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from django.http import HttpResponse
from datetime import datetime
import io


# Brand colors (matching your existing PDF exports)
BRAND_BLUE = colors.HexColor('#4a9eff')
DARK_GRAY = colors.HexColor('#333333')
MEDIUM_GRAY = colors.HexColor('#666666')
LIGHT_GRAY = colors.HexColor('#cccccc')
BACKGROUND_GRAY = colors.HexColor('#f5f5f5')


def export_all_locations_pdf(request):
    """
    Generate PDF showing ALL locations with their equipment
    Organized by location, then by module within each location
    """
    from planner.models import Location
    
    # Get all locations for current project
    if hasattr(request, 'current_project') and request.current_project:
        locations = Location.objects.filter(
            project=request.current_project
        ).prefetch_related(
            'consoles',
            'devices',
            'amps__amp_model',
            'amps__channels',
            'system_processors',
            'comm_beltpacks__position',
            'comm_beltpacks__name'
        ).order_by('name')
    else:
        locations = Location.objects.none()
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"All_Locations_Equipment_List.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create PDF document
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    # Container for PDF elements
    story = []
    
    # Styles
    header_style = ParagraphStyle(
    'CustomHeader',
    fontSize=20,  # Reduced from 24
    textColor=BRAND_BLUE,
    spaceAfter=12,  # Increased from 6
    alignment=TA_CENTER,
    fontName='Helvetica-Bold'
)
    
    location_header_style = ParagraphStyle(
        'LocationHeader',
        fontSize=18,
        textColor=BRAND_BLUE,
        spaceAfter=8,
        spaceBefore=20,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    subheader_style = ParagraphStyle(
        'SubHeader',
        fontSize=14,
        textColor=DARK_GRAY,
        spaceAfter=10,
        spaceBefore=10,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    info_style = ParagraphStyle(
        'Info',
        fontSize=10,
        textColor=MEDIUM_GRAY,
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    # Main header
    if hasattr(request, 'current_project') and request.current_project:
        project_name = request.current_project.name
    else:
        project_name = "All Projects"
    
    story.append(Paragraph(f"Equipment by Location", header_style))
    story.append(Spacer(1, 0.15*inch))  # ADD THIS LINE
    project_info = f"Project: {project_name} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    story.append(Paragraph(project_info, info_style))
    story.append(Spacer(1, 0.25*inch))
    
    # Helper function to create section tables
    def create_equipment_table(headers, data, col_widths):
        """Create a formatted table for equipment listing"""
        if not data:
            return None
            
        table_data = [headers] + data
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
            ('LINEBELOW', (0, 0), (-1, 0), 2, BRAND_BLUE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BACKGROUND_GRAY]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        return table
    
    # Loop through each location
    for location in locations:
        # Location header
        story.append(Paragraph(f"Location: {location.name}", location_header_style))
        
        if location.description:
            desc_style = ParagraphStyle(
                'Description',
                fontSize=9,
                textColor=MEDIUM_GRAY,
                spaceAfter=12,
                alignment=TA_LEFT,
                fontName='Helvetica-Oblique'
            )
            story.append(Paragraph(location.description, desc_style))
        
        # Track if location has any equipment
        has_equipment = False
        
        # CONSOLES
        consoles = location.consoles.all()
        if consoles.exists():
            has_equipment = True
            story.append(Paragraph("Consoles", subheader_style))
            
            console_data = []
            for console in consoles:
                console_data.append([
                    console.name,
                    console.primary_ip_address or 'N/A',
                    '✓' if console.is_template else ''
                ])
            
            headers = ['Console Name', 'IP Address', 'Template']
            col_widths = [3*inch, 2*inch, 1*inch]
            
            table = create_equipment_table(headers, console_data, col_widths)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.15*inch))
        
        # I/O DEVICES
        devices = location.devices.all()
        if devices.exists():
            has_equipment = True
            story.append(Paragraph("I/O Devices", subheader_style))
            
            device_data = []
            for device in devices:
                device_data.append([
                    device.name,
                    f"{device.input_count}/{device.output_count}",
                    device.primary_ip_address or 'N/A'
                ])
            
            headers = ['Device Name', 'I/O', 'IP Address']
            col_widths = [3*inch, 1*inch, 2*inch]
            
            table = create_equipment_table(headers, device_data, col_widths)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.15*inch))
        
       
        # AMPLIFIERS
        amps = location.amps.filter(project=location.project).select_related('amp_model').all()
        if amps.exists():
            has_equipment = True
            story.append(Paragraph("Amplifiers", subheader_style))
            
            amp_data = []
            for amp in amps:
                # Get the amp name
                amp_name = amp.name if hasattr(amp, 'name') and amp.name else "Unnamed Amp"
                
                # Get model name
                model_name = str(amp.amp_model) if amp.amp_model else 'N/A'
                
                # Get IP address
                ip = str(amp.ip_address) if amp.ip_address else 'N/A'
                
                amp_data.append([
                    amp_name,
                    model_name,
                    ip
                ])
            
            headers = ['Amp Name', 'Model', 'IP Address']
            col_widths = [1.5*inch, 2*inch, 1.5*inch]
            
            table = create_equipment_table(headers, amp_data, col_widths)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.15*inch))
        
        # SYSTEM PROCESSORS
        processors = location.system_processors.all()
        if processors.exists():
            has_equipment = True
            story.append(Paragraph("System Processors", subheader_style))
            
            processor_data = []
            for processor in processors:
                processor_data.append([
                    processor.name,
                    processor.device_type,
                    processor.ip_address or 'N/A'
                ])
            
            headers = ['Processor Name', 'Type', 'IP Address']
            col_widths = [2.5*inch, 1.5*inch, 2*inch]
            
            table = create_equipment_table(headers, processor_data, col_widths)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.15*inch))
        
        # COMM BELT PACKS
        beltpacks = location.comm_beltpacks.all().order_by('bp_number')
        if beltpacks.exists():
            has_equipment = True
            story.append(Paragraph("Comm Belt Packs", subheader_style))
            
            beltpack_data = []
            for bp in beltpacks:
                # Get position name
                position_name = bp.position.name if bp.position else 'Unassigned'
                
                # Get crew name
                crew_name = bp.name.name if bp.name else ''
                
                # Get system type display
                system_type = bp.get_system_type_display() if hasattr(bp, 'get_system_type_display') else bp.system_type
                
                # Get IP address for hardwired
                ip = bp.ip_address or '' if bp.system_type == 'HARDWIRED' else ''
                
                beltpack_data.append([
                    f"BP #{bp.bp_number}",
                    system_type,
                    position_name,
                    crew_name,
                    ip
                ])
            
            headers = ['BP #', 'Type', 'Position', 'Name', 'IP Address']
            col_widths = [0.8*inch, 1*inch, 1.5*inch, 1.5*inch, 1.2*inch]
            
            table = create_equipment_table(headers, beltpack_data, col_widths)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.15*inch))
        
        if not has_equipment:
            no_equip_style = ParagraphStyle(
                'NoEquipment',
                fontSize=10,
                textColor=MEDIUM_GRAY,
                spaceAfter=12,
                alignment=TA_LEFT,
                fontName='Helvetica-Oblique'
            )
            story.append(Paragraph("No equipment assigned to this location", no_equip_style))
        
        # Add page break between locations
        story.append(PageBreak())
    
    # Build PDF
    doc.build(story)
    
    # Get PDF data and return
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


def export_location_pdf(request, location_id):
    """
    Generate PDF showing all equipment in a specific location
    Organized by module: Consoles, Devices, Amps, System Processors, Comm Belt Packs
    """
    from planner.models import Location
    
    # Get location and related equipment
    location = Location.objects.select_related('project').prefetch_related(
        'consoles',
        'devices',
        'amps__amp_model',
        'amps__channels',
        'system_processors',
        'comm_beltpacks__position',
        'comm_beltpacks__name'
    ).get(id=location_id)
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"{location.name.replace(' ', '_')}_Equipment_List.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create PDF document
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    # Container for PDF elements
    story = []
    
    # Styles
    header_style = ParagraphStyle(
        'CustomHeader',
        fontSize=24,
        textColor=BRAND_BLUE,
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subheader_style = ParagraphStyle(
        'SubHeader',
        fontSize=16,
        textColor=DARK_GRAY,
        spaceAfter=12,
        spaceBefore=12,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    info_style = ParagraphStyle(
        'Info',
        fontSize=10,
        textColor=MEDIUM_GRAY,
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    # Main header - Location name
    story.append(Paragraph(f"Equipment Location: {location.name}", header_style))
    story.append(Spacer(1, 0.15*inch))  # ADD THIS LINE - spacing after header

    # Project and date info
    project_info = f"Project: {location.project.name} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    story.append(Paragraph(project_info, info_style))
    
    # Location description if exists
    if location.description:
        desc_style = ParagraphStyle(
            'Description',
            fontSize=10,
            textColor=DARK_GRAY,
            spaceAfter=20,
            alignment=TA_LEFT,
            fontName='Helvetica-Oblique'
        )
        story.append(Paragraph(f"Description: {location.description}", desc_style))
    
    story.append(Spacer(1, 0.25*inch))
    
    # Helper function to create section tables
    def create_equipment_table(headers, data, col_widths):
        """Create a formatted table for equipment listing"""
        if not data:
            return None
            
        table_data = [headers] + data
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Data rows styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid and borders
            ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
            ('LINEBELOW', (0, 0), (-1, 0), 2, BRAND_BLUE),
            
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BACKGROUND_GRAY]),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        return table
    
    # SECTION 1: CONSOLES
    consoles = location.consoles.all()
    if consoles.exists():
        story.append(Paragraph("Consoles", subheader_style))
        
        console_data = []
        for console in consoles:
            console_data.append([
                console.name,
                console.primary_ip_address or 'N/A',
                console.secondary_ip_address or 'N/A',
                '✓ Template' if console.is_template else ''
            ])
        
        headers = ['Console Name', 'Primary IP', 'Secondary IP', 'Status']
        col_widths = [2.5*inch, 1.5*inch, 1.5*inch, 1*inch]
        
        table = create_equipment_table(headers, console_data, col_widths)
        if table:
            story.append(table)
            story.append(Spacer(1, 0.3*inch))
    
    # SECTION 2: I/O DEVICES
    devices = location.devices.all()
    if devices.exists():
        story.append(Paragraph("I/O Devices", subheader_style))
        
        device_data = []
        for device in devices:
            device_data.append([
                device.name,
                str(device.input_count),
                str(device.output_count),
                device.primary_ip_address or 'N/A',
                device.secondary_ip_address or 'N/A'
            ])
        
        headers = ['Device Name', 'Inputs', 'Outputs', 'Primary IP', 'Secondary IP']
        col_widths = [2*inch, 0.7*inch, 0.7*inch, 1.5*inch, 1.5*inch]
        
        table = create_equipment_table(headers, device_data, col_widths)
        if table:
            story.append(table)
            story.append(Spacer(1, 0.3*inch))
    
   
  
    
   
    # SECTION 3: AMPLIFIERS
    amps = location.amps.filter(project=location.project).select_related('amp_model').all()
    if amps.exists():
        story.append(Paragraph("Amplifiers", subheader_style))
        
        amp_data = []
        for amp in amps:
            # Get the amp name
            amp_name = amp.name if hasattr(amp, 'name') and amp.name else "Unnamed Amp"
            
            # Get model name
            model_name = str(amp.amp_model) if amp.amp_model else 'N/A'
            
            # Get IP address
            ip = str(amp.ip_address) if amp.ip_address else 'N/A'
            
            amp_data.append([
                amp_name,
                model_name,
                ip
            ])
        
        headers = ['Amp Name', 'Model', 'IP Address']
        col_widths = [2*inch, 2.5*inch, 2*inch]
        
        table = create_equipment_table(headers, amp_data, col_widths)
        if table:
            story.append(table)
            story.append(Spacer(1, 0.3*inch))
    
    # SECTION 4: SYSTEM PROCESSORS
    processors = location.system_processors.all()
    if processors.exists():
        story.append(Paragraph("System Processors", subheader_style))
        
        processor_data = []
        for processor in processors:
            processor_data.append([
                processor.name,
                processor.device_type,
                processor.ip_address or 'N/A',
                processor.notes[:50] + '...' if processor.notes and len(processor.notes) > 50 else (processor.notes or '')
            ])
        
        headers = ['Processor Name', 'Type', 'IP Address', 'Notes']
        col_widths = [2*inch, 1.2*inch, 1.5*inch, 1.8*inch]
        
        table = create_equipment_table(headers, processor_data, col_widths)
        if table:
            story.append(table)
            story.append(Spacer(1, 0.3*inch))
    
    # SECTION 5: COMM BELT PACKS
    beltpacks = location.comm_beltpacks.all().order_by('bp_number')
    if beltpacks.exists():
        story.append(Paragraph("Comm Belt Packs", subheader_style))
        
        beltpack_data = []
        for bp in beltpacks:
            # Get position name
            position_name = bp.position.name if bp.position else 'Unassigned'
            
            # Get crew name
            crew_name = bp.name.name if bp.name else ''
            
            # Get system type display
            system_type = bp.get_system_type_display() if hasattr(bp, 'get_system_type_display') else bp.system_type
            
            # Get headset type
            headset = bp.get_headset_display() if hasattr(bp, 'get_headset_display') and bp.headset else ''
            
            # Get IP address for hardwired
            ip = bp.ip_address or '' if bp.system_type == 'HARDWIRED' else ''
            
            beltpack_data.append([
                f"BP #{bp.bp_number}",
                system_type,
                position_name,
                crew_name,
                headset,
                ip
            ])
        
        headers = ['BP #', 'Type', 'Position', 'Name', 'Headset', 'IP Address']
        col_widths = [0.7*inch, 0.9*inch, 1.3*inch, 1.3*inch, 1*inch, 1.3*inch]
        
        table = create_equipment_table(headers, beltpack_data, col_widths)
        if table:
            story.append(table)
            story.append(Spacer(1, 0.3*inch))
    
    # Summary section at bottom
    summary_style = ParagraphStyle(
        'Summary',
        fontSize=10,
        textColor=DARK_GRAY,
        spaceAfter=6,
        spaceBefore=20,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("Equipment Summary:", summary_style))
    
    summary_data = [
        ['Module', 'Count'],
        ['Consoles', str(consoles.count())],
        ['I/O Devices', str(devices.count())],
        ['Amplifiers', str(amps.count())],
        ['System Processors', str(processors.count())],
        ['Comm Belt Packs', str(beltpacks.count())],
        ['Total Equipment', str(consoles.count() + devices.count() + amps.count() + processors.count() + beltpacks.count())]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 1*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ('BACKGROUND', (0, -1), (-1, -1), BACKGROUND_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(summary_table)
    
    # Build PDF
    doc.build(story)
    
    # Get PDF data and return
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response