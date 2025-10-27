# planner/utils/pdf_exports/console_pdf.py
"""
Console PDF Export - Professional PDF generation for Console configurations
"""

from reportlab.lib.pagesizes import landscape
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch
from io import BytesIO
from django.http import HttpResponse

from .pdf_styles import PDFStyles, LANDSCAPE_PAGE, MARGIN


def export_console_pdf(console):
    """
    Generate a comprehensive PDF export for a Console
    
    Args:
        console: Console model instance
    
    Returns:
        HttpResponse with PDF content
    """
    # Create PDF in memory
    buffer = BytesIO()
    
    # Use landscape orientation for wide tables
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"{console.name} - Console Configuration"
    )
    
    # Build document content
    story = []
    styles = PDFStyles()
    
    # Header
    header_text = styles.format_header_text(
        show_name=None,
        document_type="Console Configuration",
        console_name=console.name
    )
    story.append(Paragraph(header_text, styles.get_header_style()))
    story.append(Spacer(1, 0.2 * inch))
    
    # Section 1: Console Inputs
    if console.consoleinput_set.exists():
        story.append(Paragraph("Console Inputs", styles.get_section_style()))
        story.append(Spacer(1, 0.1 * inch))
        
        # Build table data
        data = [['#', 'Dante', 'Input Ch', 'Source', 'Notes', 'Group', 'DCA']]
        
    # Section 1: Console Inputs
    if console.consoleinput_set.exists():
        story.append(Paragraph("Console Inputs", styles.get_section_style()))
        story.append(Spacer(1, 0.1 * inch))
        
        # Build table data
    data = [['#', 'Dante', 'Input Ch', 'Source', 'Group', 'DCA']]

    # Section 1: Console Inputs
    if console.consoleinput_set.exists():
        story.append(Paragraph("Console Inputs", styles.get_section_style()))
        story.append(Spacer(1, 0.1 * inch))
        
        # Build table data with all fields
        data = [['Dante #', 'Input Ch', 'Source', 'Group', 'DCA', 'Mute', 'Direct Out', 'Omni In']]
        
        for inp in console.consoleinput_set.all().order_by('dante_number'):
            # Only include if at least one field has data
            if inp.dante_number or inp.input_ch or inp.source or inp.group or inp.dca or inp.mute or inp.direct_out or inp.omni_in:
                data.append([
                    str(inp.dante_number) if inp.dante_number else '',
                    inp.input_ch or '',
                    inp.source or '',
                    inp.group or '',
                    inp.dca or '',
                    inp.mute or '',
                    inp.direct_out or '',
                    inp.omni_in or ''
                ])
    
    # Only create the section if there's actual data
    if len(data) > 1:  # More than just the header row
        # Column widths for landscape page (11" wide minus margins = ~10" available)
        col_widths = [0.6*inch, 0.7*inch, 2.2*inch, 0.8*inch, 0.6*inch, 0.6*inch, 0.9*inch, 0.9*inch]
        
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(styles.get_compact_table_style())
        story.append(t)
        story.append(PageBreak())
    

        # Section 2: Aux Outputs
    if console.consoleauxoutput_set.exists():
        story.append(Paragraph("Aux Outputs", styles.get_section_style()))
        story.append(Spacer(1, 0.1 * inch))
        
        data = [['Dante #', 'Aux', 'Name', 'Mono/Stereo', 'Bus Type', 'Omni Out']]
        
        # Get all aux outputs and sort them numerically
        aux_outputs = list(console.consoleauxoutput_set.all())
        aux_outputs.sort(key=lambda x: int(x.aux_number) if x.aux_number and x.aux_number.isdigit() else 999)
        
        for aux in aux_outputs:
            # Only include if at least one field has data
            if aux.aux_number or aux.dante_number or aux.name or aux.mono_stereo or hasattr(aux, 'bus_type') and aux.bus_type or hasattr(aux, 'omni_out') and aux.omni_out:
                data.append([
                    str(aux.dante_number) if aux.dante_number else '',
                    aux.aux_number or '',
                    aux.name or '',
                    aux.mono_stereo or '',
                    getattr(aux, 'bus_type', '') or '',
                    getattr(aux, 'omni_out', '') or ''
                ])
        
        # Only create the section if there's actual data
        if len(data) > 1:
            col_widths = [0.8*inch, 0.6*inch, 3*inch, 1*inch, 1*inch, 1*inch]
            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(styles.get_compact_table_style())
            story.append(t)
            story.append(PageBreak())
        

            # Section 3: Matrix Outputs
        if console.consolematrixoutput_set.exists():
            story.append(Paragraph("Matrix Outputs", styles.get_section_style()))
            story.append(Spacer(1, 0.1 * inch))
            
            data = [['Dante #', 'Matrix', 'Name', 'Mono/Stereo', 'Destination', 'Omni Out']]
            
            # Get all matrix outputs and sort them numerically
            matrix_outputs = list(console.consolematrixoutput_set.all())
            matrix_outputs.sort(key=lambda x: int(x.matrix_number) if x.matrix_number and x.matrix_number.isdigit() else 999)
            
            for mtx in matrix_outputs:
                # Only include if at least one field has data
                if mtx.matrix_number or mtx.dante_number or mtx.name or mtx.mono_stereo or hasattr(mtx, 'destination') and mtx.destination or hasattr(mtx, 'omni_out') and mtx.omni_out:
                    data.append([
                        str(mtx.dante_number) if mtx.dante_number else '',
                        mtx.matrix_number or '',
                        mtx.name or '',
                        mtx.mono_stereo or '',
                        getattr(mtx, 'destination', '') or '',
                        getattr(mtx, 'omni_out', '') or ''
                    ])
            
            # Only create the section if there's actual data
            if len(data) > 1:
                col_widths = [0.8*inch, 0.7*inch, 2.5*inch, 1*inch, 1.5*inch, 0.9*inch]
                t = Table(data, colWidths=col_widths, repeatRows=1)
                t.setStyle(styles.get_compact_table_style())
                story.append(t)
                story.append(PageBreak())



                        # Section 4: Stereo Outputs
            story.append(Paragraph("Stereo Outputs", styles.get_section_style()))
            story.append(Spacer(1, 0.1 * inch))

            data = [['Dante #', 'Buss', 'Name', 'Omni Out']]

            # Get all stereo outputs for this console
            stereo_outputs = console.consolestereooutput_set.all()

            # Add each stereo output to the table
            for stereo in stereo_outputs:
                data.append([
                    str(stereo.dante_number or ''),
                    stereo.get_stereo_type_display() if stereo.stereo_type else '',
                    str(stereo.name or ''),
                    str(getattr(stereo, 'omni_out', '') or '')
                ])

            # Create the table (will show even if all rows are blank)
            col_widths = [1.2*inch, 1.8*inch, 4*inch, 1.5*inch]
            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(styles.get_compact_table_style())
            story.append(t)


        
    # Build PDF with page numbers
    doc.build(story, onFirstPage=styles.add_page_number, onLaterPages=styles.add_page_number)
    
    # Return as HTTP response
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"Console_{console.name.replace(' ', '_')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response