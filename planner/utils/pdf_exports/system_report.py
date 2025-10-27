# planner/utils/pdf_exports/system_report.py
"""
System Report PDF Export - Comprehensive report of all parent modules
Combines: Locations, IP Addresses, Consoles, Devices, Amps, System Processors, etc.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
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


def export_system_report(request):
    """
    Generate comprehensive system report PDF
    Includes all parent modules for the current project
    """
    from planner.models import (
        Location, Console, Device, Amp, SystemProcessor,
        PACableSchedule, CommBeltPack, PowerDistributionPlan
    )
    
    # Get current project
    if not hasattr(request, 'current_project') or not request.current_project:
        # Return empty PDF with message
        return _empty_project_pdf()
    
    project = request.current_project
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"{project.name.replace(' ', '_')}_System_Report.pdf"
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
    title_style = ParagraphStyle(
        'Title',
        fontSize=28,
        textColor=BRAND_BLUE,
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    header_style = ParagraphStyle(
        'Header',
        fontSize=20,
        textColor=BRAND_BLUE,
        spaceAfter=12,
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
    
    # Cover Page
    story.append(Spacer(1, 1.5*inch))
    story.append(Paragraph("System Report", title_style))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f"Project: {project.name}", header_style))
    
    project_info = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    story.append(Paragraph(project_info, info_style))
    
    story.append(PageBreak())
    
    # Helper function to create section tables
    def create_table(headers, data, col_widths):
        """Create a formatted table"""
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
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
            ('LINEBELOW', (0, 0), (-1, 0), 2, BRAND_BLUE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BACKGROUND_GRAY]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        return table
    
    # SECTION 1: EQUIPMENT LOCATIONS
    story.append(Paragraph("Equipment Locations", header_style))
    
    locations = Location.objects.filter(project=project).prefetch_related(
        'consoles', 'devices', 'amps', 'system_processors'
    ).order_by('name')
    
    if locations.exists():
        location_data = []
        for location in locations:
            console_count = location.consoles.count()
            device_count = location.devices.count()
            amp_count = location.amps.filter(project=project).count()
            processor_count = location.system_processors.count()
            total = console_count + device_count + amp_count + processor_count
            
            location_data.append([
                location.name,
                str(console_count),
                str(device_count),
                str(amp_count),
                str(processor_count),
                str(total)
            ])
        
        headers = ['Location', 'Consoles', 'I/O Devices', 'Amps', 'Processors', 'Total']
        col_widths = [2*inch, 0.9*inch, 1*inch, 0.7*inch, 1*inch, 0.7*inch]
        
        table = create_table(headers, location_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No locations defined", info_style))
    
    story.append(Spacer(1, 0.3*inch))
    
    # SECTION 2: IP ADDRESS ASSIGNMENTS
    story.append(Paragraph("IP Address Assignments", header_style))
    
    # Collect all IP addresses from different modules
    ip_data = []
    
    # Consoles
    consoles = Console.objects.filter(project=project).order_by('name')
    for console in consoles:
        if console.primary_ip_address:
            ip_data.append(['Console', console.name, console.primary_ip_address, 'Primary'])
        if console.secondary_ip_address:
            ip_data.append(['Console', console.name, console.secondary_ip_address, 'Secondary'])
    
    # Devices
    devices = Device.objects.filter(project=project).order_by('name')
    for device in devices:
        if device.primary_ip_address:
            ip_data.append(['I/O Device', device.name, device.primary_ip_address, 'Primary'])
        if device.secondary_ip_address:
            ip_data.append(['I/O Device', device.name, device.secondary_ip_address, 'Secondary'])
    
    # Amplifiers
    amps = Amp.objects.filter(project=project).select_related('amp_model').order_by('name')
    for amp in amps:
        if amp.ip_address:
            amp_name = amp.name if hasattr(amp, 'name') and amp.name else f"Amp {amp.id}"
            ip_data.append(['Amplifier', amp_name, amp.ip_address, 'AVB'])
    
    # System Processors
    processors = SystemProcessor.objects.filter(project=project).order_by('name')
    for processor in processors:
        if processor.ip_address:
            ip_data.append(['Processor', processor.name, processor.ip_address, processor.device_type])
    
    if ip_data:
        headers = ['Module', 'Device Name', 'IP Address', 'Type/Network']
        col_widths = [1.2*inch, 2.5*inch, 1.5*inch, 1.3*inch]
        
        table = create_table(headers, ip_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No IP addresses assigned", info_style))
    
    story.append(PageBreak())
    
    # SECTION 3: CONSOLES
    story.append(Paragraph("Consoles", header_style))
    
    if consoles.exists():
        console_data = []
        for console in consoles:
            input_count = console.consoleinput_set.count() if hasattr(console, 'consoleinput_set') else 0
            aux_count = console.consoleauxoutput_set.count() if hasattr(console, 'consoleauxoutput_set') else 0
            matrix_count = console.consolematrixoutput_set.count() if hasattr(console, 'consolematrixoutput_set') else 0
            
            console_data.append([
                console.name,
                console.primary_ip_address or 'N/A',
                str(input_count),
                str(aux_count),
                str(matrix_count),
                '✓' if console.is_template else ''
            ])
        
        headers = ['Console Name', 'IP Address', 'Inputs', 'Aux', 'Matrix', 'Template']
        col_widths = [2.5*inch, 1.3*inch, 0.6*inch, 0.6*inch, 0.6*inch, 0.9*inch]
        
        table = create_table(headers, console_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No consoles configured", info_style))
    
    story.append(Spacer(1, 0.3*inch))
    
    # SECTION 4: I/O DEVICES
    story.append(Paragraph("I/O Devices", header_style))
    
    if devices.exists():
        device_data = []
        for device in devices:
            device_data.append([
                device.name,
                str(device.input_count),
                str(device.output_count),
                device.primary_ip_address or 'N/A'
            ])
        
        headers = ['Device Name', 'Inputs', 'Outputs', 'IP Address']
        col_widths = [2.5*inch, 0.8*inch, 0.8*inch, 2*inch]
        
        table = create_table(headers, device_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No I/O devices configured", info_style))
    
    story.append(Spacer(1, 0.3*inch))
    
    # SECTION 5: AMPLIFIERS
    story.append(Paragraph("Amplifiers", header_style))
    
    if amps.exists():
        amp_data = []
        for amp in amps:
            amp_name = amp.name if hasattr(amp, 'name') and amp.name else f"Amp {amp.id}"
            model_name = str(amp.amp_model) if amp.amp_model else 'N/A'
            location_name = amp.location.name if amp.location else 'N/A'
            channel_count = amp.channels.count() if hasattr(amp, 'channels') else 0
            
            amp_data.append([
                amp_name,
                model_name,
                location_name,
                amp.ip_address or 'N/A',
                str(channel_count)
            ])
        
        headers = ['Amp Name', 'Model', 'Location', 'IP Address', 'Channels']
        col_widths = [1.5*inch, 1.8*inch, 1.3*inch, 1.3*inch, 0.8*inch]
        
        table = create_table(headers, amp_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No amplifiers configured", info_style))
    
    story.append(PageBreak())
    
    # SECTION 6: SYSTEM PROCESSORS
    story.append(Paragraph("System Processors", header_style))
    
    if processors.exists():
        processor_data = []
        for processor in processors:
            location_name = processor.location.name if processor.location else 'N/A'
            processor_data.append([
                processor.name,
                processor.get_device_type_display() if hasattr(processor, 'get_device_type_display') else processor.device_type,
                location_name,
                processor.ip_address or 'N/A'
            ])
        
        headers = ['Processor Name', 'Type', 'Location', 'IP Address']
        col_widths = [2*inch, 1.5*inch, 1.5*inch, 1.5*inch]
        
        table = create_table(headers, processor_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No system processors configured", info_style))
    
    story.append(Spacer(1, 0.3*inch))
    
    # SECTION 7: PA CABLE SCHEDULES
    story.append(Paragraph("PA Cable Schedule", header_style))

    pa_cables = PACableSchedule.objects.filter(project=project).order_by('label')

    if pa_cables.exists():
        cable_data = []
        for cable in pa_cables:
            label_text = 'N/A'
            if hasattr(cable, 'label') and cable.label:
                label_text = str(cable.label)
            
            # Get length
            length_text = 'N/A'
            if hasattr(cable, 'length') and cable.length:
                length_text = str(cable.length)
            
            cable_data.append([
                label_text,
                cable.cable_type if cable.cable_type else 'N/A',
                length_text,
                str(cable.count) if cable.count else '0',
                cable.to_location if cable.to_location else 'N/A'
            ])
        
        headers = ['Label', 'Cable Type', 'Length', 'Count', 'To Location']
        col_widths = [1.2*inch, 1.3*inch, 0.8*inch, 0.7*inch, 2.5*inch]
        
        table = create_table(headers, cable_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No PA cable runs defined", info_style))

    story.append(Spacer(1, 0.3*inch))
    
    
    # SECTION 8: COMM SYSTEM
    # SECTION 8: COMM SYSTEM
    story.append(Paragraph("COMM System", header_style))

    # Helper function to extract channel abbreviations
    def get_channel_abbrev(channel):
        """Extract abbreviation from channel name like 'CH1 (PROD)' -> 'PROD'"""
        if not channel:
            return ''
        channel_str = str(channel)
        if '(' in channel_str and ')' in channel_str:
            return channel_str[channel_str.find('(')+1:channel_str.find(')')].strip()
        return channel_str

    # Separate by system_type
    for system_type, type_name in [('H', 'Hardwired'), ('W', 'Wireless')]:
        belt_packs = CommBeltPack.objects.filter(
            project=project,
            system_type=system_type
        ).order_by('bp_number')
        
        if belt_packs.exists():
            story.append(Paragraph(f"{type_name} Belt Packs", subheader_style))
            
            comm_data = []
            for pack in belt_packs:
                comm_data.append([
                    str(pack.bp_number) if pack.bp_number else '',
                    pack.position or '',
                    pack.name or '',
                    pack.get_headset_display() if pack.headset else '',
                    get_channel_abbrev(pack.channel_a),
                    get_channel_abbrev(pack.channel_b),
                    get_channel_abbrev(pack.channel_c),
                    get_channel_abbrev(pack.channel_d),
                    pack.get_group_display() if pack.group else ''
                ])
            
            headers = ['BP #', 'Position', 'Name', 'Headset', 'CH A', 'CH B', 'CH C', 'CH D', 'Group']
            col_widths = [0.4*inch, 0.9*inch, 1.6*inch, 0.7*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.6*inch]
            
            table = create_table(headers, comm_data, col_widths)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.2*inch))

    if not CommBeltPack.objects.filter(project=project).exists():
        story.append(Paragraph("No COMM belt packs configured", info_style))

    story.append(PageBreak())
    
    # SECTION 9: POWER DISTRIBUTION
    # SECTION 9: POWER DISTRIBUTION
    story.append(Paragraph("Power Distribution", header_style))

    power_plans = PowerDistributionPlan.objects.filter(project=project)

    if power_plans.exists():
        for plan in power_plans:
            # Get phase assignments
            phase_data = []
            if hasattr(plan, 'phaseassignment_set'):
                assignments = plan.phaseassignment_set.select_related('amp').order_by('phase', 'position')
                for assignment in assignments:
                    amp_name = assignment.amp.name if hasattr(assignment.amp, 'name') and assignment.amp.name else f"Amp {assignment.amp.id}"
                    phase_data.append([
                        assignment.phase,
                        str(assignment.position),
                        amp_name,
                        f"{assignment.amp_load:.1f}A" if assignment.amp_load else 'N/A'
                    ])
            
            if phase_data:
                headers = ['Phase', 'Position', 'Amplifier', 'Load']
                col_widths = [0.8*inch, 0.8*inch, 3*inch, 1*inch]
                
                table = create_table(headers, phase_data, col_widths)
                if table:
                    story.append(table)
                    story.append(Spacer(1, 0.2*inch))
    else:
        story.append(Paragraph("No power distribution plans configured", info_style))
    
    # Build PDF
    doc.build(story)
    
    # Get PDF data and return
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response


def _empty_project_pdf():
    """Return a PDF with 'No project selected' message"""
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="No_Project_Selected.pdf"'
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    
    story = []
    style = ParagraphStyle('Error', fontSize=16, textColor=DARK_GRAY, alignment=TA_CENTER)
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("No project selected", style))
    story.append(Paragraph("Please select a project from the dropdown menu", style))
    
    doc.build(story)
    
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response