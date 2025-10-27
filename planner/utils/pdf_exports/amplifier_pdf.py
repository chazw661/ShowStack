# planner/utils/pdf_exports/amplifier_pdf.py
"""
Amplifier Assignments PDF Export - Grouped by Location, ordered by IP address
"""

from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
from reportlab.lib import colors
from io import BytesIO
from django.http import HttpResponse
from collections import defaultdict
import ipaddress

from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN, BRAND_BLUE, DARK_GRAY


def export_all_amps_pdf():
    """
    Generate PDF export for ALL amplifiers grouped by Location, ordered by IP
    
    Returns:
        HttpResponse with PDF content
    """
    from planner.models import Amp, Location
    
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Amplifier Assignments"
    )
    
    story = []
    styles = PDFStyles()
    
    # Main header
    header_text = "<b>Amplifier Assignments</b>"
    story.append(Paragraph(header_text, styles.get_header_style()))
    story.append(Spacer(1, 0.2 * inch))
    
    # Get all amps with their locations
    amps = Amp.objects.select_related('location', 'amp_model').prefetch_related('channels').all()
    
    # Group amps by location
    location_groups = defaultdict(list)
    for amp in amps:
        location_groups[amp.location].append(amp)
    
    # Sort locations by their lowest IP address
    def get_location_min_ip(location):
        """Get the minimum IP address for a location"""
        location_amps = location_groups[location]
        ips = []
        for amp in location_amps:
            if amp.ip_address:
                try:
                    ips.append(ipaddress.ip_address(amp.ip_address))
                except:
                    pass
        return min(ips) if ips else ipaddress.ip_address('255.255.255.255')
    
    sorted_locations = sorted(location_groups.keys(), key=get_location_min_ip)
    
    # Process each location
    for loc_idx, location in enumerate(sorted_locations):
        # Location header
        location_name = location.name if location else "No Location"
        story.append(Paragraph(f"<b>{location_name}</b>", styles.get_section_style()))
        story.append(Spacer(1, 0.15 * inch))
        
        # Sort amps within location by IP address
        location_amps = location_groups[location]
        location_amps.sort(key=lambda a: ipaddress.ip_address(a.ip_address) if a.ip_address else ipaddress.ip_address('255.255.255.255'))
        
        # Process each amp in this location
        for amp_idx, amp in enumerate(location_amps):
            # Amp name and model header
            amp_header = f"<b>{amp.name}</b>"
            if amp.amp_model:
                amp_header += f" - {amp.amp_model.manufacturer} {amp.amp_model.model_name}"
            if amp.ip_address:
                amp_header += f" ({amp.ip_address})"
            
            story.append(Paragraph(amp_header, styles.get_section_style()))
            story.append(Spacer(1, 0.15 * inch))
            
            # SECTION 1: Amp Channels (Inputs) - AT THE TOP
            channels = list(amp.channels.all().order_by('channel_number'))
            
            if channels:
                # Build channel table
                channel_data = [['Ch', 'Name', 'AVB Stream', 'AES Input', 'Analog Input']]
                
                for ch in channels:
                    # Format AVB stream reference
                    avb_ref = ''
                    if ch.avb_stream:
                        avb_ref = f"AVB {ch.avb_stream.output_number}" if ch.avb_stream.output_number else str(ch.avb_stream)
                    
                    channel_data.append([
                        str(ch.channel_number),
                        ch.channel_name or '----------',
                        avb_ref or '----------',
                        ch.aes_input or '----------',
                        ch.analog_input or '----------'
                    ])
                
                col_widths = [0.5*inch, 2*inch, 1.5*inch, 1.5*inch, 1.5*inch]
                t = Table(channel_data, colWidths=col_widths)
                t.setStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUND', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ])
                story.append(t)
                story.append(Spacer(1, 0.2 * inch))
            
            # SECTION 2: NL4 Connectors Section (if present)
            if amp.amp_model and amp.amp_model.nl4_connector_count > 0:
                nl4_data = [['NL4 Connector A', '', 'NL4 Connector B', '']]
                nl4_data.append(['Pair 1 +/-', 'Pair 2 +/-', 'Pair 1 +/-', 'Pair 2 +/-'])
                nl4_data.append([
                    amp.nl4_a_pair_1 or '----------',
                    amp.nl4_a_pair_2 or '----------',
                    amp.nl4_b_pair_1 or '----------' if amp.amp_model.nl4_connector_count >= 2 else '',
                    amp.nl4_b_pair_2 or '----------' if amp.amp_model.nl4_connector_count >= 2 else ''
                ])
                
                col_widths = [1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]
                t = Table(nl4_data, colWidths=col_widths)
                t.setStyle([
                    ('BACKGROUND', (0, 0), (1, 0), BRAND_BLUE),
                    ('BACKGROUND', (2, 0), (3, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (3, 0), colors.white),
                    ('FONTNAME', (0, 0), (3, 1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (3, -1), 9),
                    ('ALIGN', (0, 0), (3, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (3, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (3, -1), 0.5, colors.grey),
                    ('BACKGROUND', (0, 1), (3, 1), colors.HexColor('#e6f2ff')),
                    ('TOPPADDING', (0, 0), (3, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (3, -1), 6),
                ])
                story.append(t)
                story.append(Spacer(1, 0.15 * inch))
            
            # SECTION 3: Cacom Outputs Section (if present) - NOW AT BOTTOM
            if amp.amp_model and amp.amp_model.cacom_output_count > 0:
                cacom_data = [['Cacom Outputs (Ch1-Ch4)']]
                cacom_data.append(['Ch1', 'Ch2', 'Ch3', 'Ch4'])
                cacom_data.append([
                    amp.cacom_1_assignment or '----------',
                    amp.cacom_2_assignment or '----------',
                    amp.cacom_3_assignment or '----------',
                    amp.cacom_4_assignment or '----------'
                ])
                
                col_widths = [1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch]
                t = Table(cacom_data, colWidths=col_widths)
                t.setStyle([
                    ('BACKGROUND', (0, 0), (3, 0), BRAND_BLUE),
                    ('TEXTCOLOR', (0, 0), (3, 0), colors.white),
                    ('SPAN', (0, 0), (3, 0)),
                    ('FONTNAME', (0, 0), (3, 1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (3, -1), 9),
                    ('ALIGN', (0, 0), (3, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (3, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (3, -1), 0.5, colors.grey),
                    ('BACKGROUND', (0, 1), (3, 1), colors.HexColor('#e6f2ff')),
                    ('TOPPADDING', (0, 0), (3, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (3, -1), 6),
                ])
                story.append(t)
            
            # Page break after EVERY amp (one amp per page)
            story.append(PageBreak())
    
    # Build PDF (remove last page break if needed)
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Amplifier_Assignments.pdf"'
    
    return response