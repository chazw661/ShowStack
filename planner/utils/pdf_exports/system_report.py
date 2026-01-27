# planner/utils/pdf_exports/system_report.py
"""
System Report PDF Export - Comprehensive report combining all module exports
Generates a complete system document suitable for sharing with crew members
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, PageBreak, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from django.http import HttpResponse
from datetime import datetime
import io

from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN

# Brand colors
BRAND_BLUE = colors.HexColor('#4a9eff')
DARK_GRAY = colors.HexColor('#333333')
MEDIUM_GRAY = colors.HexColor('#666666')
LIGHT_GRAY = colors.HexColor('#cccccc')
BACKGROUND_GRAY = colors.HexColor('#f5f5f5')


def export_system_report(request):
    """
    Generate comprehensive system report PDF
    Combines all module exports into one document
    """
    from planner.models import (
        Location, Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput,
        Device, DeviceInput, DeviceOutput,
        Amp, AmpChannel, SystemProcessor,
        PACableSchedule, PAFanOut,
        CommBeltPack, CommChannel,
        PowerDistributionPlan, AmplifierAssignment,
        SoundvisionPrediction, SpeakerArray, SpeakerCabinet
    )
    
    # Get current project
    if not hasattr(request, 'current_project') or not request.current_project:
        return _empty_project_pdf()
    
    project = request.current_project
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"{project.name.replace(' ', '_')}_Complete_System_Report.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    # Create PDF document - use landscape for wide tables
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN
    )
    
    story = []
    styles = PDFStyles()
    
    # Styles
    title_style = ParagraphStyle(
        'Title',
        fontSize=32,
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
        spaceAfter=8,
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
    
    # Helper function to create section tables
    def create_table(headers, data, col_widths):
        if not data:
            return None
        table_data = [headers] + data
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
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
    
    # =====================
    # COVER PAGE
    # =====================
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("Complete System Report", title_style))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"{project.name}", header_style))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", info_style))
    story.append(PageBreak())
    
    # =====================
    # TABLE OF CONTENTS
    # =====================
    story.append(Paragraph("Table of Contents", header_style))
    story.append(Spacer(1, 0.2*inch))
    
    toc_items = [
        "1. Consoles",
        "2. I/O Devices", 
        "3. System Processors",
        "4. PA Cable Schedule",
        "5. COMM System",
        "6. Power Distribution",
        "7. Soundvision Predictions"
    ]
    for item in toc_items:
        story.append(Paragraph(item, info_style))
    story.append(PageBreak())
    
    # =====================
    # SECTION 1: CONSOLES
    # =====================
    story.append(Paragraph("1. Consoles", header_style))
    story.append(Spacer(1, 0.1*inch))
    
    consoles = Console.objects.filter(project=project).order_by('name')
    
    if consoles.exists():
        for console in consoles:
            story.append(Paragraph(f"Console: {console.name}", subheader_style))
            
    
            # Console Inputs - sort numerically since dante_number is CharField
            from django.db.models.functions import Cast
            from django.db.models import IntegerField
            inputs = console.consoleinput_set.annotate(
                dante_num_int=Cast('dante_number', IntegerField())
            ).order_by('dante_num_int')
            if inputs.exists():
                input_data = []
                for inp in inputs:
                    if inp.dante_number or inp.input_ch or inp.source:
                        input_data.append([
                            str(inp.dante_number) if inp.dante_number else '',
                            inp.input_ch or '',
                            inp.source or '',
                            inp.source_hardware or '',
                            inp.group or '',
                            inp.dca or '',
                            inp.mute or '',
                            inp.direct_out or '',
                            inp.omni_in or ''
                        ])
                
                if input_data:
                    story.append(Paragraph("Inputs", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                    headers = ['Dante #', 'Input Ch', 'Source', 'Src Hardware', 'Group', 'DCA', 'Mute', 'Direct Out', 'Omni In']
                    col_widths = [0.5*inch, 0.6*inch, 1.4*inch, 1.0*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.7*inch, 0.7*inch]
                    table = create_table(headers, input_data, col_widths)
                    if table:
                        story.append(table)
                        story.append(Spacer(1, 0.15*inch))
            
            # Console Aux Outputs
            aux_outputs = console.consoleauxoutput_set.all()
            if aux_outputs.exists():
                aux_data = []
                for aux in sorted(aux_outputs, key=lambda x: int(x.aux_number) if x.aux_number and x.aux_number.isdigit() else 999):
                    if aux.aux_number or aux.name:
                        aux_data.append([
                            str(aux.dante_number) if aux.dante_number else '',
                            aux.aux_number or '',
                            aux.name or '',
                            aux.mono_stereo or '',
                            getattr(aux, 'bus_type', '') or '',
                            getattr(aux, 'omni_out', '') or ''
                        ])
                
                if aux_data:
                    story.append(Paragraph("Aux Outputs", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                    headers = ['Dante #', 'Aux', 'Name', 'Mono/Stereo', 'Bus Type', 'Omni Out']
                    col_widths = [0.7*inch, 0.5*inch, 2.5*inch, 0.9*inch, 0.9*inch, 0.9*inch]
                    table = create_table(headers, aux_data, col_widths)
                    if table:
                        story.append(table)
                        story.append(Spacer(1, 0.15*inch))
            
            # Console Matrix Outputs
            matrix_outputs = console.consolematrixoutput_set.all()
            if matrix_outputs.exists():
                matrix_data = []
                for mtx in sorted(matrix_outputs, key=lambda x: int(x.matrix_number) if x.matrix_number and x.matrix_number.isdigit() else 999):
                    if mtx.matrix_number or mtx.name:
                        matrix_data.append([
                            str(mtx.dante_number) if mtx.dante_number else '',
                            mtx.matrix_number or '',
                            mtx.name or '',
                            mtx.mono_stereo or '',
                            getattr(mtx, 'destination', '') or '',
                            getattr(mtx, 'omni_out', '') or ''
                        ])
                
                if matrix_data:
                    story.append(Paragraph("Matrix Outputs", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                    headers = ['Dante #', 'Matrix', 'Name', 'Mono/Stereo', 'Destination', 'Omni Out']
                    col_widths = [0.7*inch, 0.6*inch, 2.2*inch, 0.9*inch, 1.3*inch, 0.7*inch]
                    table = create_table(headers, matrix_data, col_widths)
                    if table:
                        story.append(table)
                        story.append(Spacer(1, 0.15*inch))
            
            # Console Stereo Outputs
            stereo_outputs = console.consolestereooutput_set.all()
            if stereo_outputs.exists():
                stereo_data = []
                for stereo in stereo_outputs:
                    stereo_data.append([
                        str(stereo.dante_number) if stereo.dante_number else '',
                        stereo.get_stereo_type_display() if stereo.stereo_type else '',
                        stereo.name or '',
                        getattr(stereo, 'omni_out', '') or ''
                    ])
                
                if stereo_data:
                    story.append(Paragraph("Stereo Outputs", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                    headers = ['Dante #', 'Buss', 'Name', 'Omni Out']
                    col_widths = [0.8*inch, 1.2*inch, 3*inch, 1*inch]
                    table = create_table(headers, stereo_data, col_widths)
                    if table:
                        story.append(table)
            
            story.append(PageBreak())
    else:
        story.append(Paragraph("No consoles configured", info_style))
        story.append(PageBreak())
    
    # =====================
    # SECTION 2: I/O DEVICES
    # =====================
    story.append(Paragraph("2. I/O Devices", header_style))
    story.append(Spacer(1, 0.1*inch))
    
    devices = Device.objects.filter(project=project).order_by('name')
    
    if devices.exists():
        for device in devices:
            story.append(Paragraph(f"Device: {device.name}", subheader_style))
            if device.location:
                story.append(Paragraph(f"Location: {device.location.name}", info_style))
            
            # Device Inputs
            inputs = device.inputs.filter(input_number__isnull=False).order_by('input_number')
            if inputs.exists():
                input_data = []
                for inp in inputs:
                    # Get label from linked console input
                    input_label = ''
                    console_source = ''
                    if inp.console_input:
                        input_label = inp.console_input.source or ''
                        if inp.console_input.console:
                            console_input_num = inp.console_input.input_ch
                            console_source = f"{inp.console_input.console.name} - Input {console_input_num}"
                    
                    input_data.append([
                        str(inp.input_number) if inp.input_number else '',
                        input_label,
                        console_source,
                    ])
                
                if input_data:
                    story.append(Paragraph("Inputs", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                    headers = ['Input #', 'Signal', 'Console Source']
                    col_widths = [0.7*inch, 2*inch, 3*inch]
                    table = create_table(headers, input_data, col_widths)
                    if table:
                        story.append(table)
                        story.append(Spacer(1, 0.15*inch))
            
            # Device Outputs
            outputs = device.outputs.filter(output_number__isnull=False).order_by('output_number')
            if outputs.exists():
                output_data = []
                for out in outputs:
                    output_label = out.signal_name or ''
                    output_data.append([
                        str(out.output_number) if out.output_number else '',
                        output_label,
                    ])
                
                if output_data:
                    story.append(Paragraph("Outputs", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                    headers = ['Output #', 'Signal Name']
                    col_widths = [0.7*inch, 5*inch]
                    table = create_table(headers, output_data, col_widths)
                    if table:
                        story.append(table)
            
            story.append(PageBreak())
    else:
        story.append(Paragraph("No I/O devices configured", info_style))
        story.append(PageBreak())
    
    # =====================
    # SECTION 3: SYSTEM PROCESSORS
    # =====================
    story.append(Paragraph("3. System Processors", header_style))
    story.append(Spacer(1, 0.1*inch))
    
    processors = SystemProcessor.objects.filter(project=project).order_by('name')
    
    if processors.exists():
        processor_data = []
        for proc in processors:
            processor_data.append([
                proc.name,
                proc.get_device_type_display() if hasattr(proc, 'get_device_type_display') else proc.device_type,
                proc.location.name if proc.location else '',
                proc.ip_address or ''
            ])
        
        headers = ['Name', 'Type', 'Location', 'IP Address']
        col_widths = [2.5*inch, 2*inch, 2*inch, 2*inch]
        table = create_table(headers, processor_data, col_widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No system processors configured", info_style))
    
    story.append(PageBreak())
    
   # =====================
    # SECTION 4: PA CABLE SCHEDULE
    # =====================
    story.append(Paragraph("4. PA Cable Schedule", header_style))
    story.append(Spacer(1, 0.1*inch))
    
    pa_cables = PACableSchedule.objects.filter(project=project).order_by('label')
    
    if pa_cables.exists():
        for cable in pa_cables:
            story.append(Paragraph(f"Cable Run: {cable.label}", subheader_style))
            
            # Cable info
            cable_info = []
            cable_info.append(['Cable Type', cable.cable_type or 'N/A'])
            cable_info.append(['Length', str(cable.length) if cable.length else 'N/A'])
            cable_info.append(['Count', str(cable.count) if cable.count else '0'])
            cable_info.append(['To Location', cable.to_location or 'N/A'])
            
            info_table = Table(cable_info, colWidths=[1.5*inch, 4*inch])
            info_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(info_table)
            
            # Fan outs
            fanouts = cable.fan_outs.all()
            if fanouts.exists():
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("Fan Outs", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                
                fanout_data = []
                for fo in fanouts:
                    fanout_data.append([
                        fo.get_fan_out_type_display() if fo.fan_out_type else '',
                        str(fo.quantity) if fo.quantity else '1',
                    ])
                
                headers = ['Fan Out Type', 'Quantity']
                col_widths = [3*inch, 1*inch]
                table = create_table(headers, fanout_data, col_widths)
                if table:
                    story.append(table)
            
            story.append(Spacer(1, 0.2*inch))
    else:
        story.append(Paragraph("No PA cable runs configured", info_style))
    
    story.append(PageBreak())
    
    # =====================
    # SECTION 5: COMM SYSTEM
    # =====================
    story.append(Paragraph("5. COMM System", header_style))
    story.append(Spacer(1, 0.1*inch))
    
    for system_type, type_name in [('WIRELESS', 'Wireless System'), ('HARDWIRED', 'Hardwired System')]:
        belt_packs = CommBeltPack.objects.filter(
            project=project,
            system_type=system_type
        ).order_by('bp_number')
        
        if belt_packs.exists():
            story.append(Paragraph(type_name, subheader_style))
            
            comm_data = []
            for pack in belt_packs:
                position_name = pack.position.name if pack.position else ''
                crew_name = pack.name.name if pack.name else ''
                location_name = pack.unit_location.name if pack.unit_location else ''
                
                # Get channel assignments
                channels = pack.channels.all().order_by('channel_number')
                channel_strs = []
                for ch in channels[:4]:  # Show first 4 channels
                    if ch.channel:
                        channel_strs.append(str(ch.channel.abbreviation if hasattr(ch.channel, 'abbreviation') else ch.channel))
                    else:
                        channel_strs.append('')
                
                # Pad to 4 channels
                while len(channel_strs) < 4:
                    channel_strs.append('')
                
                comm_data.append([
                    str(pack.bp_number) if pack.bp_number else '',
                    position_name,
                    crew_name,
                    location_name,
                    pack.get_headset_display() if pack.headset else '',
                    channel_strs[0],
                    channel_strs[1],
                    channel_strs[2],
                    channel_strs[3],
                    pack.ip_address or ''
                ])
            
            headers = ['BP #', 'Position', 'Name', 'Location', 'Headset', 'CH 1', 'CH 2', 'CH 3', 'CH 4', 'IP']
            col_widths = [0.35*inch, 1.2*inch, 1.3*inch, 0.9*inch, 0.6*inch, 0.45*inch, 0.45*inch, 0.45*inch, 0.45*inch, 0.9*inch]
            
            table = create_table(headers, comm_data, col_widths)
            if table:
                story.append(table)
                story.append(Spacer(1, 0.2*inch))
    
    if not CommBeltPack.objects.filter(project=project).exists():
        story.append(Paragraph("No COMM belt packs configured", info_style))
    
    story.append(PageBreak())
    
    # =====================
    # SECTION 6: POWER DISTRIBUTION
    # =====================
    story.append(Paragraph("6. Power Distribution", header_style))
    story.append(Spacer(1, 0.1*inch))
    
    power_plans = PowerDistributionPlan.objects.filter(project=project)
    
    if power_plans.exists():
        for plan in power_plans:
            story.append(Paragraph(f"Venue: {plan.venue_name}", subheader_style))
            
            # Get amplifier assignments
            assignments = plan.amplifier_assignments.all().order_by('phase_assignment', 'position')
            if assignments.exists():
                assign_data = []
                for assign in assignments:
                    amp_name = str(assign.amplifier) if assign.amplifier else ''
                    assign_data.append([
                        assign.phase_assignment or '',
                        str(assign.position) if assign.position else '',
                        amp_name,
                        str(assign.quantity) if assign.quantity else '1',
                        f"{assign.calculated_current_per_unit:.1f}A" if assign.calculated_current_per_unit else '',
                        f"{assign.calculated_total_current:.1f}A" if assign.calculated_total_current else ''
                    ])
                
                headers = ['Phase', 'Position', 'Amplifier', 'Qty', 'Current/Unit', 'Total Current']
                col_widths = [0.7*inch, 0.7*inch, 3*inch, 0.5*inch, 1*inch, 1*inch]
                
                table = create_table(headers, assign_data, col_widths)
                if table:
                    story.append(table)
            
            story.append(Spacer(1, 0.2*inch))
    else:
        story.append(Paragraph("No power distribution plans configured", info_style))
    
    story.append(PageBreak())
    
# =====================
    # SECTION 7: SOUNDVISION PREDICTIONS
    # =====================
    story.append(Paragraph("7. Soundvision Predictions", header_style))
    story.append(Spacer(1, 0.1*inch))
    
    predictions = SoundvisionPrediction.objects.filter(project=project)
    
    if predictions.exists():
        for prediction in predictions:
            story.append(Paragraph(f"Prediction: {prediction.file_name}", subheader_style))
            
            # Speaker Arrays
            arrays = prediction.speaker_arrays.all().order_by('source_name')
            if arrays.exists():
                for array in arrays:
                    story.append(Paragraph(f"Array: {array.source_name}", ParagraphStyle('Small', fontSize=10, textColor=DARK_GRAY, spaceBefore=6)))
                    
                    cabinets = array.cabinets.all().order_by('position_number')
                    if cabinets.exists():
                        cab_data = []
                        for cab in cabinets:
                            cab_data.append([
                                str(cab.position_number) if cab.position_number else '',
                                cab.speaker_model or '',
                                f"{cab.angle_to_next}°" if cab.angle_to_next else '',
                            ])
                        
                        headers = ['Position', 'Speaker Model', 'Angle']
                        col_widths = [0.8*inch, 2*inch, 0.8*inch]
                        
                        table = create_table(headers, cab_data, col_widths)
                        if table:
                            story.append(table)
                            story.append(Spacer(1, 0.1*inch))
            
            story.append(Spacer(1, 0.2*inch))
    else:
        story.append(Paragraph("No Soundvision predictions configured", info_style))
    
    # Build PDF
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    # Return response
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