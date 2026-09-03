# planner/utils/pdf_exports/report_kit.py
"""
Shared building blocks for ShowStack PDF exports.

Extracted from the Complete System Report so every standalone module export
(consoles, devices, amps, COMM, PA cable, IP, locations, processors,
Soundvision) gets the same professional look and page-break behaviour:

  * restrained navy/blue palette, clean tables with zebra striping
  * full-width section banners and a per-module title header
  * "Page X of Y" footer with the project name
  * empty-column pruning and widow/orphan-free page breaks
    (small tables kept whole; larger tables split with >=2 rows per fragment)

Import these helpers instead of re-styling each export by hand.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, KeepTogether, HRFlowable, CondPageBreak,
)
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from datetime import datetime

# ---------------------------------------------------------------------------
# Page + palette
# ---------------------------------------------------------------------------
PORTRAIT_PAGE = letter
LANDSCAPE_PAGE = landscape(letter)
MARGIN = 0.5 * inch
FOOTER_MARGIN = 0.6 * inch

NAVY = colors.HexColor('#16304f')          # section banners + table headers
BLUE = colors.HexColor('#4a9eff')          # accent rules
INK = colors.HexColor('#1f2933')           # primary body text
MUTED = colors.HexColor('#66727f')         # secondary / captions
HAIRLINE = colors.HexColor('#d5dbe1')      # grid lines
ROW_ALT = colors.HexColor('#f3f6f9')       # zebra striping

# Amp rack-view card accents (echo the ShowStack Amp Assignment module)
AMP_NAME = colors.HexColor('#ffe066')
AMP_ANALOG_BG = colors.HexColor('#ffe066')
AMP_AES_BG = colors.HexColor('#9ed87a')
AMP_OUT_BG = colors.HexColor('#c03a3a')
AMP_PILL_BG = colors.HexColor('#fff2b8')
AMP_DARK_INK = colors.HexColor('#222222')


def usable_width(pagesize):
    return pagesize[0] - 2 * MARGIN


# Columns whose values are short codes/numbers and read better centered.
NUMERIC_HEADERS = {
    'Dante #', 'Input Ch', 'Aux', 'Matrix', 'BP #', '#', 'Qty', 'Count',
    'Length', 'Current/Unit', 'Total Current', 'Input #', 'Output #', 'Ch',
    'Output', 'CH 1', 'CH 2', 'CH 3', 'CH 4',
}

# Minimum data rows that may land on either side of a table page break.
MIN_SPLIT_ROWS = 2

# Rough flowable heights (pt) for deciding keep-whole vs. split.
_ROW_H, _HEADER_H, _CAPTION_H, _HEADING_H = 22, 24, 18, 30
MAX_KEEP_HEIGHT = 470
# Minimum room to *start* a subsection so its heading never orphans.
SUBTABLE_MIN_ROOM = 1.5 * inch


# ===========================================================================
# Canvas: "Page X of Y" footer with project name
# ===========================================================================
class NumberedCanvas(pdfcanvas.Canvas):
    """Canvas that stamps a footer once the total page count is known.

    Set the module-level footer text via ``NumberedCanvas.configure(...)``
    before building, since ReportLab constructs the canvas internally.
    """

    _project_name = ''
    _skip_first = True   # cover/title page stays clean

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    @classmethod
    def configure(cls, project_name='', skip_first=True):
        cls._project_name = project_name or ''
        cls._skip_first = skip_first

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
        if page == 1 and self._skip_first:
            return
        self.saveState()
        width = self._pagesize[0]
        y = 0.32 * inch
        self.setStrokeColor(HAIRLINE)
        self.setLineWidth(0.5)
        self.line(MARGIN, y + 10, width - MARGIN, y + 10)
        self.setFont('Helvetica', 8)
        self.setFillColor(MUTED)
        if self._project_name:
            self.drawString(MARGIN, y, self._project_name)
        self.drawCentredString(width / 2.0, y, f"Page {page} of {total}")
        self.drawRightString(width - MARGIN, y, "ShowStack • showstack.io")
        self.restoreState()


def build_pdf(buffer, story, pagesize=LANDSCAPE_PAGE, project_name='',
              skip_first_footer=False, title=None):
    """Build ``story`` into ``buffer`` with the standard footer.

    ``skip_first_footer`` True keeps a cover/title page clean (used by the
    Complete System Report); most single-module exports want it False.
    """
    doc = SimpleDocTemplate(
        buffer, pagesize=pagesize,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=FOOTER_MARGIN,
        title=title or 'ShowStack Export',
    )
    NumberedCanvas.configure(project_name=project_name, skip_first=skip_first_footer)
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer


# ===========================================================================
# Paragraph styles
# ===========================================================================
def styles():
    return {
        'doc_title': ParagraphStyle(
            'DocTitle', fontSize=22, textColor=NAVY, alignment=TA_LEFT,
            fontName='Helvetica-Bold', leading=26, spaceAfter=2),
        'doc_sub': ParagraphStyle(
            'DocSub', fontSize=11, textColor=MUTED, alignment=TA_LEFT,
            fontName='Helvetica', leading=15, spaceAfter=8),
        'section': ParagraphStyle(
            'Section', fontSize=17, textColor=colors.white,
            fontName='Helvetica-Bold', leading=20),
        'sub': ParagraphStyle(
            'Sub', fontSize=12, textColor=NAVY, fontName='Helvetica-Bold',
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
        'body': ParagraphStyle(
            'Body', fontSize=9, textColor=INK, fontName='Helvetica', leading=12),
    }


# ===========================================================================
# Title header + section banner
# ===========================================================================
def title_header(title, subtitle, pagesize=LANDSCAPE_PAGE, S=None):
    """A left-aligned module title with a blue accent rule under it."""
    S = S or styles()
    flow = [Paragraph(title, S['doc_title'])]
    if subtitle:
        flow.append(Paragraph(subtitle, S['doc_sub']))
    flow.append(HRFlowable(width=usable_width(pagesize), thickness=2, color=BLUE,
                           spaceBefore=2, spaceAfter=12))
    return flow


def section_banner(title, number=None, pagesize=LANDSCAPE_PAGE, S=None):
    """Full-width navy banner with an optional leading number."""
    S = S or styles()
    label = f"{number}&nbsp;&nbsp;&nbsp;{title}" if number is not None else title
    para = Paragraph(label, S['section'])
    banner = Table([[para]], colWidths=[usable_width(pagesize)])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('LINEBELOW', (0, 0), (-1, -1), 2.5, BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    return banner


# ===========================================================================
# Tables
# ===========================================================================
def prune_empty_columns(headers, data, col_widths, keep=()):
    """Drop columns whose every data cell is blank. ``keep`` indices stay."""
    keep = set(keep)
    used = [c for c in range(len(headers))
            if c in keep or any(str(row[c]).strip() for row in data)]
    return ([headers[c] for c in used],
            [[row[c] for c in used] for row in data],
            [col_widths[c] for c in used])


class MinRowsTable(Table):
    """A Table that refuses to split off fewer than MIN_SPLIT_ROWS data rows."""

    def _header_rows(self):
        rr = self.repeatRows
        if isinstance(rr, int):
            return rr
        return (max(rr) + 1) if rr else 0

    def split(self, availWidth, availHeight):
        parts = Table.split(self, availWidth, availHeight)
        if len(parts) < 2:
            return parts
        m = MIN_SPLIT_ROWS
        n_head = self._header_rows()
        total_data = self._nrows - n_head
        if total_data <= m:
            return []
        first_data = parts[0]._nrows - n_head
        tail_data = parts[1]._nrows - n_head
        if first_data < m:
            return []
        if tail_data < m:
            k = m - tail_data
            if first_data - k < m:
                return []
            boundary = n_head + first_data
            row_heights = self._rowHeights or []
            trim = sum(row_heights[boundary - k:boundary])
            retry = Table.split(self, availWidth, availHeight - trim)
            return retry if len(retry) >= 2 else []
        return parts


def data_table(headers, data, col_widths, header_bg=NAVY):
    """Standard styled table. Returns None when there is nothing to show.

    Column alignment is chosen from the header label (see NUMERIC_HEADERS),
    so it stays correct even after empty columns are pruned.
    """
    if not data:
        return None
    table = MinRowsTable([headers] + data, colWidths=col_widths,
                         repeatRows=1, hAlign='LEFT')
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
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


def keep(flowables):
    """Wrap a heading + its table so the heading never orphans."""
    return KeepTogether([f for f in flowables if f is not None])


def table_block(flowables, n_rows, n_headings=0):
    """Keep a heading/caption/table group whole when it fits a page; otherwise
    start it cleanly (CondPageBreak) and let it split with a repeating header."""
    flowables = [f for f in flowables if f is not None]
    est = _HEADER_H + _CAPTION_H + n_rows * _ROW_H + _HEADING_H * n_headings
    if est <= MAX_KEEP_HEIGHT:
        return [keep(flowables)]
    return [CondPageBreak(SUBTABLE_MIN_ROOM)] + flowables


def emit_subtable(pending_blocks, caption, headers, data, col_widths, S=None):
    """Emit a captioned table, kept whole when it fits and split without
    orphaning its heading when it doesn't. Returns a list of flowables."""
    S = S or styles()
    table = data_table(headers, data, col_widths)
    if table is None:
        return []
    caption_para = Paragraph(caption, S['caption']) if caption else None
    blocks = list(pending_blocks) + ([caption_para] if caption_para else []) + [table]
    return table_block(blocks, len(data), n_headings=len(pending_blocks))


# ===========================================================================
# Amplifier rack-view cards (shared with the Complete System Report)
# ===========================================================================
_AMP_COLS = [3.4 * inch, 2.5 * inch, 4.1 * inch]

_AMP_P = {
    'name': ParagraphStyle('AmpName', fontSize=12, leading=14, textColor=AMP_NAME,
                           fontName='Helvetica-Bold'),
    'val': ParagraphStyle('AmpVal', fontSize=7, leading=8.5, textColor=INK),
    'hdr': ParagraphStyle('AmpHdr', fontSize=6.5, leading=8, textColor=colors.white,
                          fontName='Helvetica-Bold'),
    'hdrc': ParagraphStyle('AmpHdrC', fontSize=6.5, leading=8, textColor=colors.white,
                           fontName='Helvetica-Bold', alignment=TA_CENTER),
    'dark': ParagraphStyle('AmpDark', fontSize=6.5, leading=8, textColor=AMP_DARK_INK,
                           fontName='Helvetica-Bold', alignment=TA_CENTER),
    'pill': ParagraphStyle('AmpPill', fontSize=10, leading=11, textColor=AMP_DARK_INK,
                           alignment=TA_CENTER),
    'outc': ParagraphStyle('AmpOut', fontSize=7.5, leading=9, textColor=colors.white,
                           fontName='Helvetica-Bold', alignment=TA_CENTER),
}


def _amp_inputs_table(channels):
    P = _AMP_P
    data = [[Paragraph('XLR', P['hdrc']), Paragraph('AVB Stream', P['hdr']),
             Paragraph('Analogue Input', P['dark']), Paragraph('AES Input', P['dark'])]]
    for c in channels:
        data.append([str(c.channel_number),
                     Paragraph(c.avb_stream or '', P['val']),
                     Paragraph(c.analog_input or '', P['val']),
                     Paragraph(c.aes_input or '', P['val'])])
    t = Table(data, colWidths=[0.35 * inch, 1.0 * inch, 1.05 * inch, 1.0 * inch],
              hAlign='LEFT')
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, HAIRLINE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, 0), (1, 0), NAVY),
        ('BACKGROUND', (2, 0), (2, 0), AMP_ANALOG_BG),
        ('BACKGROUND', (3, 0), (3, 0), AMP_AES_BG),
        ('BACKGROUND', (0, 0), (0, -1), NAVY),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
    ]))
    return t


def _amp_pill(label, value):
    p = Paragraph(
        f'<font size="6" color="#8a7400"><b>{label}</b></font><br/>'
        f'<b>{value or "&mdash;"}</b>', _AMP_P['pill'])
    t = Table([[p]], colWidths=[2.2 * inch], hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), AMP_PILL_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#c0a020')),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def _amp_middle(amp, channels):
    P = _AMP_P
    flow = [_amp_pill('IP ADDRESS', amp.ip_address or ''), Spacer(1, 4),
            _amp_pill('PRESET', (amp.preset or '').strip())]
    setting_rows = [[str(c.channel_number),
                     c.get_channel_setting_display() if c.channel_setting else '']
                    for c in channels if c.channel_setting]
    if setting_rows:
        data = [[Paragraph('Ch', P['hdrc']), Paragraph('Setting', P['hdr'])]] + setting_rows
        t = Table(data, colWidths=[0.4 * inch, 1.8 * inch], hAlign='LEFT')
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, HAIRLINE),
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('TEXTCOLOR', (0, 1), (-1, -1), INK),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        flow += [Spacer(1, 6), t]
    return flow


def _amp_output_block(title, rows):
    P = _AMP_P
    title_tbl = Table([[Paragraph(title, P['outc'])]], colWidths=[3.9 * inch], hAlign='LEFT')
    title_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), AMP_OUT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    body = [[str(lbl), Paragraph(str(val or ''), P['val'])] for lbl, val in rows]
    body_tbl = Table(body, colWidths=[0.5 * inch, 3.4 * inch], hAlign='LEFT')
    body_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, HAIRLINE),
        ('BACKGROUND', (0, 0), (0, -1), NAVY),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    return [title_tbl, body_tbl, Spacer(1, 6)]


def _amp_outputs(amp):
    model = amp.amp_model
    flow = []
    if model and model.nl4_connector_count:
        flow += _amp_output_block('NL4 Out', [
            (n, getattr(amp, f'output_{n}', '')) for n in (1, 2, 3, 4)])
    if model and model.cacom_output_count:
        rows = []
        for ci in range(1, min(model.cacom_output_count + 1, 5)):
            base = (ci - 1) * 4
            for n in range(1, 5):
                rows.append((base + n, getattr(amp, f'cacom_{ci}_ch{n}', '')))
        flow += _amp_output_block('CaCom Out', rows)
    if model and getattr(model, 'sc32_connector_count', 0):
        flow += _amp_output_block('SC32 Out', [
            (n, getattr(amp, f'sc32_ch{n}', '')) for n in range(1, 17)])
    if not flow:
        generic = [(n, getattr(amp, f'output_{n}', '')) for n in (1, 2, 3, 4)]
        if any((v or '').strip() for _, v in generic):
            flow += _amp_output_block('Outputs', generic)
    return flow or [Paragraph('No outputs', _AMP_P['val'])]


def amp_card(amp):
    """One amp front-panel card matching the rack-view module."""
    channels = sorted(amp.channels.all(), key=lambda c: c.channel_number)
    model = amp.amp_model
    model_str = f"{model.manufacturer} {model.model_name}" if model else ""
    header = Paragraph(
        f'<font color="#ffe066"><b>{amp.name}</b></font>'
        + (f'&nbsp;&nbsp;<font color="#c9d6e3" size="8">{model_str}</font>' if model_str else ''),
        _AMP_P['name'])
    card = Table(
        [[header, '', ''],
         [_amp_inputs_table(channels), _amp_middle(amp, channels), _amp_outputs(amp)]],
        colWidths=_AMP_COLS, hAlign='LEFT')
    card.setStyle(TableStyle([
        ('SPAN', (0, 0), (2, 0)),
        ('BACKGROUND', (0, 0), (2, 0), NAVY),
        ('TOPPADDING', (0, 0), (2, 0), 6), ('BOTTOMPADDING', (0, 0), (2, 0), 6),
        ('LEFTPADDING', (0, 0), (2, 0), 10),
        ('VALIGN', (0, 1), (-1, 1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#8a97a6')),
        ('LINEAFTER', (0, 1), (1, 1), 0.5, colors.HexColor('#c9d2db')),
        ('TOPPADDING', (0, 1), (-1, 1), 6), ('BOTTOMPADDING', (0, 1), (-1, 1), 6),
        ('LEFTPADDING', (0, 1), (-1, 1), 6), ('RIGHTPADDING', (0, 1), (-1, 1), 6),
    ]))
    return card

