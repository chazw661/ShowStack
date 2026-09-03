# planner/utils/pdf_exports/system_report.py
"""
System Report PDF Export - Comprehensive report combining all module exports
Generates a complete system document suitable for sharing with crew members.

Design goals (issue #70):
  * Professional, consistent look across every section.
  * Page breaks that respect content flow - a heading never strands at the
    bottom of a page away from its table, and empty filler rows are dropped.
  * A real cover page and a table of contents with live page numbers.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, KeepTogether, HRFlowable, CondPageBreak,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from django.http import HttpResponse
from datetime import datetime
import io

from .pdf_styles import LANDSCAPE_PAGE, MARGIN

# ---------------------------------------------------------------------------
# Palette - a restrained, professional scheme built around the ShowStack blue.
# ---------------------------------------------------------------------------
NAVY = colors.HexColor('#16304f')          # section banners + table headers
BLUE = colors.HexColor('#4a9eff')          # accent rules
INK = colors.HexColor('#1f2933')           # primary body text
MUTED = colors.HexColor('#66727f')         # secondary / captions
HAIRLINE = colors.HexColor('#d5dbe1')      # grid lines
ROW_ALT = colors.HexColor('#f3f6f9')       # zebra striping

USABLE_WIDTH = LANDSCAPE_PAGE[0] - 2 * MARGIN

# Minimum space a subsection needs to *start* on the current page (heading +
# caption + table header + a couple of rows). If less remains, break first so
# the heading never orphans; if more remains, the table starts here and splits
# naturally across the page boundary.
SUBTABLE_MIN_ROOM = 1.5 * inch


# ===========================================================================
# Canvas + document template (footer with page numbers, TOC notifications)
# ===========================================================================
class NumberedCanvas(pdfcanvas.Canvas):
    """Canvas that stamps a 'Page X of Y' footer once the total is known."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        page = self._pageNumber
        # Cover page (page 1) stays clean - no footer chrome.
        if page == 1:
            return
        self.saveState()
        width = self._pagesize[0]
        y = 0.32 * inch
        self.setStrokeColor(HAIRLINE)
        self.setLineWidth(0.5)
        self.line(MARGIN, y + 10, width - MARGIN, y + 10)
        self.setFont('Helvetica', 8)
        self.setFillColor(MUTED)
        if self._report_project_name:
            self.drawString(MARGIN, y, self._report_project_name)
        self.drawCentredString(width / 2.0, y, f"Page {page} of {total}")
        self.drawRightString(width - MARGIN, y, "ShowStack • showstack.io")
        self.restoreState()

    # project name is injected via a class attribute set per-build
    _report_project_name = ''


class SystemReportDoc(SimpleDocTemplate):
    """Doc template that feeds heading flowables into the Table of Contents."""

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        style = flowable.style.name
        if style == 'TOCSection':
            self.notify('TOCEntry', (0, flowable.getPlainText(), self.page))
        elif style == 'TOCSub':
            self.notify('TOCEntry', (1, flowable.getPlainText(), self.page))


# ===========================================================================
# Paragraph styles
# ===========================================================================
def _styles():
    return {
        'cover_title': ParagraphStyle(
            'CoverTitle', fontSize=34, textColor=NAVY, alignment=TA_CENTER,
            fontName='Helvetica-Bold', leading=38, spaceAfter=6),
        'cover_sub': ParagraphStyle(
            'CoverSub', fontSize=18, textColor=BLUE, alignment=TA_CENTER,
            fontName='Helvetica-Bold', leading=22),
        'cover_meta': ParagraphStyle(
            'CoverMeta', fontSize=11, textColor=MUTED, alignment=TA_CENTER,
            fontName='Helvetica', leading=16),
        # Section banner text (also the TOC hook)
        'section': ParagraphStyle(
            'TOCSection', fontSize=17, textColor=colors.white,
            fontName='Helvetica-Bold', leading=20),
        # Sub-heading inside a section (console/device/cable name); TOC hook
        'sub': ParagraphStyle(
            'TOCSub', fontSize=12, textColor=NAVY, fontName='Helvetica-Bold',
            spaceBefore=10, spaceAfter=4, leading=15),
        'caption': ParagraphStyle(
            'Caption', fontSize=9, textColor=MUTED, fontName='Helvetica-Bold',
            spaceBefore=4, spaceAfter=3, leading=12),
        'meta': ParagraphStyle(
            'Meta', fontSize=9, textColor=MUTED, fontName='Helvetica',
            spaceAfter=2, leading=12),
        'empty': ParagraphStyle(
            'Empty', fontSize=10, textColor=MUTED, fontName='Helvetica-Oblique',
            spaceBefore=6, leading=14),
        'toc_head': ParagraphStyle(
            'TOCHead', fontSize=20, textColor=NAVY, fontName='Helvetica-Bold',
            spaceAfter=16),
    }


# ===========================================================================
# Shared building blocks
# ===========================================================================
def _section_banner(number, title, styles):
    """A full-width navy banner: '1   Consoles' with a blue accent underline."""
    para = Paragraph(f"{number}&nbsp;&nbsp;&nbsp;{title}", styles['section'])
    banner = Table([[para]], colWidths=[USABLE_WIDTH])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('LINEBELOW', (0, 0), (-1, -1), 2.5, BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    return banner


def _prune_empty_columns(headers, data, col_widths, keep=()):
    """Drop columns whose every data cell is blank (keeps report tight).

    ``keep`` is a set of column indices that are never dropped.
    """
    keep = set(keep)
    used = []
    for c in range(len(headers)):
        if c in keep or any(str(row[c]).strip() for row in data):
            used.append(c)
    headers = [headers[c] for c in used]
    data = [[row[c] for c in used] for row in data]
    col_widths = [col_widths[c] for c in used]
    return headers, data, col_widths


# Column headers whose values are short codes/numbers and read better centered.
NUMERIC_HEADERS = {
    'Dante #', 'Input Ch', 'Aux', 'Matrix', 'BP #', '#', 'Qty', 'Count',
    'Length', 'Current/Unit', 'Total Current', 'Input #', 'Output #',
    'CH 1', 'CH 2', 'CH 3', 'CH 4',
}


def _data_table(headers, data, col_widths):
    """Build a styled data table. Returns None when there is nothing to show.

    Alignment is chosen per column from the header label, so it stays correct
    even after empty columns are pruned away.
    """
    if not data:
        return None
    table_data = [headers] + data
    table = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    style = [
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        # Body
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TEXTCOLOR', (0, 1), (-1, -1), INK),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.25, HAIRLINE),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, BLUE),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    for c, head in enumerate(headers):
        if head in NUMERIC_HEADERS:
            style.append(('ALIGN', (c, 1), (c, -1), 'CENTER'))
    table.setStyle(TableStyle(style))
    return table


def _num_key(value):
    """Safe numeric sort key for CharField numbers (avoids Postgres cast crash)."""
    try:
        return (0, int(str(value).strip()))
    except (TypeError, ValueError):
        return (1, 0)  # blanks / non-numeric sort last, stably


def _keep(flowables):
    """Wrap a heading + its table so the heading never orphans at a page break."""
    return KeepTogether([f for f in flowables if f is not None])


# ===========================================================================
# Main entry point
# ===========================================================================
def export_system_report(request):
    """Generate the comprehensive system report PDF for the active project."""
    from planner.models import (
        Console, Device, SystemProcessor,
        PACableSchedule, CommBeltPack,
        PowerDistributionPlan, SoundvisionPrediction,
    )

    if not hasattr(request, 'current_project') or not request.current_project:
        return _empty_project_pdf()

    project = request.current_project
    styles = _styles()

    response = HttpResponse(content_type='application/pdf')
    filename = f"{project.name.replace(' ', '_')}_Complete_System_Report.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    buffer = io.BytesIO()
    doc = SystemReportDoc(
        buffer, pagesize=LANDSCAPE_PAGE,
        rightMargin=MARGIN, leftMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=0.6 * inch,
        title=f"{project.name} - Complete System Report",
    )

    story = []
    story += _cover_page(project, styles)
    story += _table_of_contents(styles)

    story += _section_consoles(project, styles, Console)
    story += _section_devices(project, styles, Device)
    story += _section_processors(project, styles, SystemProcessor)
    story += _section_pa_cable(project, styles, PACableSchedule)
    story += _section_comm(project, styles, CommBeltPack)
    story += _section_power(project, styles, PowerDistributionPlan)
    story += _section_soundvision(project, styles, SoundvisionPrediction)

    # Stamp the project name onto the footer canvas class for this build.
    NumberedCanvas._report_project_name = project.name

    doc.multiBuild(story, canvasmaker=NumberedCanvas)

    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    return response


# ===========================================================================
# Cover + TOC
# ===========================================================================
def _cover_page(project, styles):
    story = [
        Spacer(1, 2.4 * inch),
        Paragraph("Complete System Report", styles['cover_title']),
        Spacer(1, 0.15 * inch),
        HRFlowable(width=3.2 * inch, thickness=2, color=BLUE,
                   spaceBefore=4, spaceAfter=18, hAlign='CENTER'),
        Paragraph(project.name, styles['cover_sub']),
        Spacer(1, 0.5 * inch),
        Paragraph(
            f"Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
            styles['cover_meta']),
        Paragraph("Prepared with ShowStack • showstack.io", styles['cover_meta']),
        PageBreak(),
    ]
    return story


def _table_of_contents(styles):
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle('TOCL0', fontSize=12, fontName='Helvetica-Bold',
                       textColor=INK, leftIndent=6, firstLineIndent=-6,
                       spaceBefore=8, leading=18),
        ParagraphStyle('TOCL1', fontSize=9.5, fontName='Helvetica',
                       textColor=MUTED, leftIndent=26, firstLineIndent=0,
                       spaceBefore=2, leading=13),
    ]
    return [
        Paragraph("Table of Contents", styles['toc_head']),
        toc,
        PageBreak(),
    ]


# ===========================================================================
# Section 1 - Consoles
# ===========================================================================
def _section_consoles(project, styles, Console):
    from django.db.models import Q
    story = [_section_banner("1", "Consoles", styles), Spacer(1, 0.12 * inch)]
    consoles = Console.objects.filter(project=project).order_by('name')

    if not consoles.exists():
        story.append(Paragraph("No consoles configured.", styles['empty']))
        story.append(PageBreak())
        return story

    for console in consoles:
        blocks = [Paragraph(f"Console: {console.name}", styles['sub'])]

        # ---- Inputs (only rows with real signal content) ----
        inputs = sorted(
            console.consoleinput_set.all(),
            key=lambda i: _num_key(i.dante_number or i.input_ch),
        )
        rows = []
        for inp in inputs:
            if not (inp.source or '').strip():
                continue  # skip empty channels - this was the page-bloat culprit
            rows.append([
                str(inp.dante_number or ''), inp.input_ch or '', inp.source or '',
                inp.source_hardware or '', inp.group or '', inp.dca or '',
                inp.mute or '', inp.direct_out or '', inp.omni_in or '',
            ])
        if rows:
            headers = ['Dante #', 'Input Ch', 'Source', 'Src Hardware', 'Group',
                       'DCA', 'Mute', 'Direct Out', 'Omni In']
            widths = [0.7, 0.7, 1.9, 1.3, 0.7, 0.6, 0.6, 0.9, 0.8]
            widths = [w * inch for w in widths]
            headers, data, widths = _prune_empty_columns(headers, rows, widths, keep={1, 2})
            story += _emit_subtable(blocks, "Inputs", headers, data, widths, styles)
            blocks = []

        # ---- Aux outputs ----
        aux = sorted(
            console.consoleauxoutput_set.all(),
            key=lambda a: _num_key(a.aux_number),
        )
        rows = []
        for a in aux:
            if not (a.name or '').strip():
                continue  # numbered-but-unnamed = empty bus, skip
            rows.append([
                str(a.dante_number or ''), a.aux_number or '', a.name or '',
                a.mono_stereo or '', getattr(a, 'bus_type', '') or '',
                getattr(a, 'omni_out', '') or '',
            ])
        if rows:
            headers = ['Dante #', 'Aux', 'Name', 'Mono/Stereo', 'Bus Type', 'Omni Out']
            widths = [w * inch for w in (0.8, 0.7, 2.8, 1.1, 1.1, 1.0)]
            headers, data, widths = _prune_empty_columns(headers, rows, widths, keep={1, 2})
            story += _emit_subtable(blocks, "Aux Outputs", headers, data, widths, styles)
            blocks = []

        # ---- Matrix outputs ----
        matrix = sorted(
            console.consolematrixoutput_set.all(),
            key=lambda m: _num_key(m.matrix_number),
        )
        rows = []
        for m in matrix:
            if not (m.name or '').strip():
                continue  # numbered-but-unnamed = empty matrix, skip
            rows.append([
                str(m.dante_number or ''), m.matrix_number or '', m.name or '',
                m.mono_stereo or '', getattr(m, 'destination', '') or '',
                getattr(m, 'omni_out', '') or '',
            ])
        if rows:
            headers = ['Dante #', 'Matrix', 'Name', 'Mono/Stereo', 'Destination', 'Omni Out']
            widths = [w * inch for w in (0.8, 0.7, 2.6, 1.1, 1.4, 0.9)]
            headers, data, widths = _prune_empty_columns(headers, rows, widths, keep={1, 2})
            story += _emit_subtable(blocks, "Matrix Outputs", headers, data, widths, styles)
            blocks = []

        # ---- Stereo outputs ----
        rows = []
        for s in console.consolestereooutput_set.all():
            buss = s.get_stereo_type_display() if s.stereo_type else ''
            if not ((s.name or '').strip() or buss):
                continue
            rows.append([
                str(s.dante_number or ''), buss,
                s.name or '', getattr(s, 'omni_out', '') or '',
            ])
        if rows:
            headers = ['Dante #', 'Buss', 'Name', 'Omni Out']
            widths = [w * inch for w in (0.9, 1.4, 3.2, 1.0)]
            headers, data, widths = _prune_empty_columns(headers, rows, widths, keep={1, 2})
            story += _emit_subtable(blocks, "Stereo Outputs", headers, data, widths, styles)
            blocks = []

        # Console had a heading but no populated tables at all.
        if blocks:
            blocks.append(Paragraph("No channel data configured for this console.", styles['empty']))
            story.append(_keep(blocks))

        story.append(Spacer(1, 0.2 * inch))

    story.append(PageBreak())
    return story


def _emit_subtable(pending_blocks, caption, headers, data, widths, styles):
    """Emit a captioned table that starts cleanly and splits naturally.

    A CondPageBreak guarantees enough room for the heading + caption + first
    rows before starting, so nothing orphans at a page bottom - but unlike
    KeepTogether it does NOT push a whole large table onto the next page
    (which would leave the section banner alone above a blank gap). Big tables
    flow onto the current page and split across the boundary with a repeating
    header row.
    """
    table = _data_table(headers, data, widths)
    if table is None:
        return []
    caption_para = Paragraph(caption, styles['caption'])
    return [CondPageBreak(SUBTABLE_MIN_ROOM)] + list(pending_blocks) + [caption_para, table]


# ===========================================================================
# Section 2 - I/O Devices
# ===========================================================================
def _section_devices(project, styles, Device):
    story = [_section_banner("2", "I/O Devices", styles), Spacer(1, 0.12 * inch)]
    devices = Device.objects.filter(project=project).order_by('name')

    if not devices.exists():
        story.append(Paragraph("No I/O devices configured.", styles['empty']))
        story.append(PageBreak())
        return story

    for device in devices:
        header_blocks = [Paragraph(f"Device: {device.name}", styles['sub'])]
        if device.location:
            header_blocks.append(Paragraph(f"Location: {device.location.name}", styles['meta']))
        emitted = False

        # Physical port = 1-based position (ordered like the edit grid), NOT the
        # stored input_number, which can hold legacy/global values. Blank ports
        # are counted so the numbering lines up with the device's own labels.
        inputs = device.inputs.filter(input_number__isnull=False).order_by('input_number')
        rows = []
        for port, inp in enumerate(inputs, 1):
            label = (inp.signal_name or '').strip()
            console_source = ''
            if inp.console_input:
                if not label:
                    label = inp.console_input.source or ''
                if inp.console_input.console:
                    console_source = f"{inp.console_input.console.name} - Input {inp.console_input.input_ch}"
            if not (label or console_source):
                continue
            rows.append([str(port), label, console_source])
        if rows:
            headers = ['Input #', 'Signal', 'Console Source']
            widths = [w * inch for w in (0.9, 2.6, 3.6)]
            story += _emit_subtable(header_blocks, "Inputs", headers, rows, widths, styles)
            header_blocks = []
            emitted = True

        outputs = device.outputs.filter(output_number__isnull=False).order_by('output_number')
        rows = [[str(port), o.signal_name or '']
                for port, o in enumerate(outputs, 1) if (o.signal_name or '').strip()]
        if rows:
            headers = ['Output #', 'Signal Name']
            widths = [w * inch for w in (0.9, 6.2)]
            story += _emit_subtable(header_blocks, "Outputs", headers, rows, widths, styles)
            header_blocks = []
            emitted = True

        if not emitted:
            header_blocks.append(Paragraph("No input/output signals configured.", styles['empty']))
            story.append(_keep(header_blocks))

        story.append(Spacer(1, 0.2 * inch))

    story.append(PageBreak())
    return story


# ===========================================================================
# Section 3 - System Processors
# ===========================================================================
def _section_processors(project, styles, SystemProcessor):
    story = [_section_banner("3", "System Processors", styles), Spacer(1, 0.12 * inch)]
    procs = SystemProcessor.objects.filter(project=project).order_by('name')

    if procs.exists():
        rows = []
        for p in procs:
            rows.append([
                p.name,
                p.get_device_type_display() if hasattr(p, 'get_device_type_display') else p.device_type,
                p.location.name if p.location else '',
                p.ip_address or '',
            ])
        headers = ['Name', 'Type', 'Location', 'IP Address']
        widths = [w * inch for w in (2.8, 2.4, 2.4, 2.0)]
        table = _data_table(headers, rows, widths)
        if table:
            story.append(table)
    else:
        story.append(Paragraph("No system processors configured.", styles['empty']))

    story.append(PageBreak())
    return story


# ===========================================================================
# Section 4 - PA Cable Schedule
# ===========================================================================
def _section_pa_cable(project, styles, PACableSchedule):
    story = [_section_banner("4", "PA Cable Schedule", styles), Spacer(1, 0.12 * inch)]
    cables = PACableSchedule.objects.filter(project=project).order_by('label')

    if not cables.exists():
        story.append(Paragraph("No PA cable runs configured.", styles['empty']))
        story.append(PageBreak())
        return story

    rows = []
    for cable in cables:
        # One tidy row per cable run, with fan-outs summarised inline.
        fan_str = ", ".join(
            f"{fo.get_fan_out_type_display()} x{fo.quantity or 1}"
            for fo in cable.fan_outs.all() if fo.fan_out_type
        ) or '-'
        rows.append([
            str(cable.label or ''), cable.cable_type or '',
            str(cable.length) if cable.length else '',
            str(cable.count) if cable.count else '0',
            cable.to_location or '', fan_str,
        ])
    headers = ['Label', 'Cable Type', 'Length', 'Count', 'To Location', 'Fan Outs']
    widths = [w * inch for w in (1.6, 1.4, 0.9, 0.7, 2.2, 2.8)]
    table = _data_table(headers, rows, widths)
    if table:
        story.append(table)

    story.append(PageBreak())
    return story


# ===========================================================================
# Section 5 - COMM System
# ===========================================================================
def _section_comm(project, styles, CommBeltPack):
    story = [_section_banner("5", "COMM System", styles), Spacer(1, 0.12 * inch)]
    any_packs = False

    for system_type, type_name in [('WIRELESS', 'Wireless System'),
                                   ('HARDWIRED', 'Hardwired System')]:
        packs = sorted(
            CommBeltPack.objects.filter(project=project, system_type=system_type),
            key=lambda p: _num_key(p.bp_number),
        )
        if not packs:
            continue
        any_packs = True

        rows = []
        for pack in packs:
            channels = pack.channels.all().order_by('channel_number')
            ch = []
            for c in channels[:4]:
                if c.channel:
                    ch.append(str(getattr(c.channel, 'abbreviation', c.channel) or ''))
                else:
                    ch.append('')
            while len(ch) < 4:
                ch.append('')
            rows.append([
                str(pack.bp_number or ''),
                pack.position.name if pack.position else '',
                pack.name.name if pack.name else '',
                pack.unit_location.name if pack.unit_location else '',
                pack.get_headset_display() if pack.headset else '',
                ch[0], ch[1], ch[2], ch[3], pack.ip_address or '',
            ])
        headers = ['BP #', 'Position', 'Name', 'Location', 'Headset',
                   'CH 1', 'CH 2', 'CH 3', 'CH 4', 'IP']
        widths = [w * inch for w in (0.5, 1.4, 1.5, 1.1, 0.8, 0.6, 0.6, 0.6, 0.6, 1.1)]
        heading = Paragraph(type_name, styles['sub'])
        table = _data_table(headers, rows, widths)
        story.append(_keep([heading, table]))
        story.append(Spacer(1, 0.2 * inch))

    if not any_packs:
        story.append(Paragraph("No COMM belt packs configured.", styles['empty']))

    story.append(PageBreak())
    return story


# ===========================================================================
# Section 6 - Power Distribution
# ===========================================================================
def _section_power(project, styles, PowerDistributionPlan):
    story = [_section_banner("6", "Power Distribution", styles), Spacer(1, 0.12 * inch)]
    plans = PowerDistributionPlan.objects.filter(project=project)

    if not plans.exists():
        story.append(Paragraph("No power distribution plans configured.", styles['empty']))
        story.append(PageBreak())
        return story

    for plan in plans:
        heading = Paragraph(f"Venue: {plan.venue_name}", styles['sub'])
        assignments = plan.amplifier_assignments.all().order_by('phase_assignment', 'position')
        rows = []
        for a in assignments:
            rows.append([
                a.phase_assignment or '',
                str(a.position) if a.position else '',
                str(a.amplifier) if a.amplifier else '',
                str(a.quantity) if a.quantity else '1',
                f"{a.calculated_current_per_unit:.1f}A" if a.calculated_current_per_unit else '',
                f"{a.calculated_total_current:.1f}A" if a.calculated_total_current else '',
            ])
        headers = ['Phase', 'Position', 'Amplifier', 'Qty', 'Current/Unit', 'Total Current']
        widths = [w * inch for w in (0.9, 0.9, 3.2, 0.7, 1.3, 1.3)]
        table = _data_table(headers, rows, widths)
        if table:
            story.append(_keep([heading, table]))
        else:
            story.append(_keep([heading, Paragraph("No amplifier assignments.", styles['empty'])]))
        story.append(Spacer(1, 0.2 * inch))

    story.append(PageBreak())
    return story


# ===========================================================================
# Section 7 - Soundvision Predictions
# ===========================================================================
def _section_soundvision(project, styles, SoundvisionPrediction):
    story = [_section_banner("7", "Soundvision Predictions", styles), Spacer(1, 0.12 * inch)]
    predictions = SoundvisionPrediction.objects.filter(project=project)

    if not predictions.exists():
        story.append(Paragraph("No Soundvision predictions configured.", styles['empty']))
        return story

    array_header_style = ParagraphStyle(
        'ArrayHeader', fontSize=10.5, textColor=colors.white, backColor=NAVY,
        fontName='Helvetica-Bold', leftIndent=8, rightIndent=8,
        spaceBefore=8, spaceAfter=4, leading=18, borderPadding=(3, 4, 3, 4))
    array_info = ParagraphStyle(
        'ArrayInfo', fontSize=8, textColor=INK, leftIndent=12, leading=11)

    for prediction in predictions:
        title_parts = []
        if prediction.show_day:
            title_parts.append(str(prediction.show_day))
        title_parts.append(prediction.file_name)
        story.append(Paragraph("Prediction: " + " - ".join(title_parts), styles['sub']))

        info_parts = []
        if prediction.version:
            info_parts.append(f"Version {prediction.version}")
        if prediction.date_generated:
            info_parts.append(f"Generated {prediction.date_generated.strftime('%b %d, %Y')}")
        if info_parts:
            story.append(Paragraph("  •  ".join(info_parts), styles['meta']))

        arrays = prediction.speaker_arrays.all().order_by('source_name')
        if arrays.exists():
            total_arrays = arrays.count()
            total_cabinets = sum(a.cabinets.count() for a in arrays)
            summary = Table(
                [['TOTAL ARRAYS', 'TOTAL CABINETS'], [str(total_arrays), str(total_cabinets)]],
                colWidths=[2.2 * inch, 2.2 * inch])
            summary.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), NAVY),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8.5),
                ('FONTSIZE', (0, 1), (-1, 1), 13),
                ('TEXTCOLOR', (0, 1), (-1, 1), NAVY),
                ('GRID', (0, 0), (-1, -1), 0.5, HAIRLINE),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(summary)
            story.append(Spacer(1, 0.12 * inch))

            for array in arrays:
                blocks = [Paragraph(array.source_name or 'Array', array_header_style)]
                for label, val in _array_facts(array):
                    blocks.append(Paragraph(f"<b>{label}:</b> {val}", array_info))

                cabinets = array.cabinets.all().order_by('position_number')
                if cabinets.exists():
                    cab_rows = [['#', 'Model', 'Angle', 'Panflex']]
                    for idx, cab in enumerate(cabinets, 1):
                        angle = f"{cab.angle_to_next}°" if cab.angle_to_next is not None else ''
                        panflex = cab.get_panflex_setting_display() if (
                            hasattr(cab, 'get_panflex_setting_display') and cab.panflex_setting) else ''
                        cab_rows.append([str(idx), cab.speaker_model or '', angle, panflex])
                    cab_table = Table(cab_rows,
                                      colWidths=[0.5 * inch, 1.8 * inch, 0.9 * inch, 1.3 * inch])
                    cab_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('TEXTCOLOR', (0, 1), (-1, -1), INK),
                        ('GRID', (0, 0), (-1, -1), 0.5, HAIRLINE),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ]))
                    blocks.append(Spacer(1, 0.04 * inch))
                    blocks.append(cab_table)

                story.append(_keep(blocks))
                story.append(Spacer(1, 0.12 * inch))

        story.append(Spacer(1, 0.2 * inch))

    return story


def _array_facts(array):
    """Yield (label, value) pairs for an array's attributes, skipping blanks."""
    facts = []
    if array.array_base_name:
        facts.append(("Base Name", array.array_base_name))
    if array.group_context:
        facts.append(("Group", array.group_context))
    if array.configuration:
        facts.append(("Configuration",
                      array.get_configuration_display()
                      if hasattr(array, 'get_configuration_display') else array.configuration))
    if array.bumper_type and array.bumper_type != 'NONE':
        facts.append(("Bumper",
                      array.get_bumper_type_display()
                      if hasattr(array, 'get_bumper_type_display') else array.bumper_type))
    if array.mbar_hole:
        facts.append(("MBAR Hole", array.mbar_hole))
    pos = []
    if array.position_x is not None:
        pos.append(f"X: {array.position_x}")
    if array.position_y is not None:
        pos.append(f"Y: {array.position_y}")
    if array.position_z is not None:
        pos.append(f"Z: {array.position_z}")
    if pos:
        facts.append(("Position", ", ".join(pos)))
    if getattr(array, 'bottom_elevation', None) is not None:
        feet = int(array.bottom_elevation)
        inches = int((float(array.bottom_elevation) - feet) * 12)
        facts.append(("Bottom Trim Height", f"{feet}' {inches}\""))
    return facts


# ===========================================================================
# Fallback: no project selected
# ===========================================================================
def _empty_project_pdf():
    """Return a PDF with a 'No project selected' message."""
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="No_Project_Selected.pdf"'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)

    style = ParagraphStyle('Error', fontSize=16, textColor=INK, alignment=TA_CENTER)
    sub = ParagraphStyle('ErrorSub', fontSize=11, textColor=MUTED, alignment=TA_CENTER)
    story = [
        Spacer(1, 2 * inch),
        Paragraph("No project selected", style),
        Spacer(1, 0.2 * inch),
        Paragraph("Please select a project from the dropdown menu.", sub),
    ]
    doc.build(story)

    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    return response
