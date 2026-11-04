# planner/utils/pdf_exports/mic_plan_pdf.py
"""
Mic Plan PDF: the A2 schedule (one section per A2), the pack sheet and the
review list of one show day's stored plan. Landscape letter.

Readable in black and white: every status is a word (MIC / DE-MIC, BREAK,
HOST, BACKUP, PINNED, MID-SESSION, CONFLICT, late / tight), never a colour
alone. Every page carries the plan header (project, day, version, when it
was made and edited, settings, warnings) and a footer with the version and
when it was printed.

Built from the stored plan through planner.mic_plan.schedule and page, the
same pieces the A2 schedule screen uses; nothing is re-solved.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from planner.mic_plan import page, schedule
from planner.mic_plan.display import MARKS
from planner.mic_plan.solver import hm
from planner.utils.pdf_exports.report_kit import (
    BLUE, FOOTER_MARGIN, HAIRLINE, INK, LANDSCAPE_PAGE, MARGIN, MUTED, NAVY,
    NumberedCanvas, data_table, section_banner, styles, usable_width,
)

BREAK_BG = colors.HexColor('#e2e2e2')      # mid grey: a break, also on a mono printer
SEGMENT_BG = colors.HexColor('#eef1f4')
WARN_INK = colors.HexColor('#7a4b00')
LOGO_H = 0.42 * inch
LOGO_MAX_W = 1.8 * inch
HEAD_LEADING = 11


def stamp(dt, zone):
    """"Nov 3, 2026 14:05 PST"."""
    dt = dt.astimezone(zone)
    return '{} {}, {} {}'.format(dt.strftime('%b'), dt.day, dt.strftime('%Y %H:%M'), dt.strftime('%Z'))


def _logo(brand):
    """The logo for a white page: the on-light logo, else the mark. An
    on-dark logo alone would vanish on white, so it is left out."""
    logo = brand.logo('on_light') or brand.logo('mark')
    if logo is None or not logo.content:
        return None
    try:
        image = ImageReader(BytesIO(logo.content))
        w, h = image.getSize()
    except Exception:  # a logo ReportLab cannot read is no reason to fail the export
        return None
    if not w or not h:
        return None
    scale = min(LOGO_H / h, LOGO_MAX_W / w)
    return image, w * scale, h * scale


def header_lines(head, project, day, zone):
    """(title, [plain lines], [warning lines]) printed at the top of every page."""
    title = 'Mic Plan — {} · {}'.format(project.name, day)
    made = 'Plan v{} · generated {}'.format(head['version'], stamp(head['generated_at'], zone))
    if head['edited_at']:
        made += ' · edited {}'.format(stamp(head['edited_at'], zone))
    if head['edit_count']:
        made += ' · edited: {} change{}'.format(head['edit_count'], '' if head['edit_count'] == 1 else 's')
    times = 'times from send/catch cues' if head['cue_mode'] == 'cues' else 'times from line estimates'
    lines = [made, 'Settings: {} · {}'.format(head['settings'], times)]
    return title, lines, ['WARNING: ' + w for w in head['warnings']]


class _Header:
    """Draws the plan header on each page (SimpleDocTemplate onPage)."""

    def __init__(self, title, lines, warnings, logo, width):
        self.title, self.lines, self.logo = title, lines, logo
        self.text_w = width - (self.logo[1] + 12 if self.logo else 0)
        self.warnings = [part for w in warnings
                         for part in simpleSplit(w, 'Helvetica-Bold', 8.5, self.text_w)]
        self.height = 18 + HEAD_LEADING * (len(self.lines) + len(self.warnings)) + 8

    def __call__(self, canvas, doc):
        width, height = doc.pagesize
        top = height - MARGIN
        canvas.saveState()
        if self.logo:
            image, w, h = self.logo
            canvas.drawImage(image, width - MARGIN - w, top - h, w, h, mask='auto')
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 13)
        y = top - 12
        canvas.drawString(MARGIN, y, self.title)
        y -= 6
        canvas.setFont('Helvetica', 8.5)
        canvas.setFillColor(MUTED)
        for line in self.lines:
            y -= HEAD_LEADING
            canvas.drawString(MARGIN, y, line)
        canvas.setFont('Helvetica-Bold', 8.5)
        canvas.setFillColor(WARN_INK)
        for line in self.warnings:
            y -= HEAD_LEADING
            canvas.drawString(MARGIN, y, line)
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.5)
        canvas.line(MARGIN, top - self.height + 2, width - MARGIN, top - self.height + 2)
        canvas.restoreState()


def _canvas_class(project_name, version, printed):
    """NumberedCanvas whose footer also says the plan version and when it
    was printed. A class per build: ReportLab makes the canvas itself."""

    class MicPlanCanvas(NumberedCanvas):
        _skip_first = False

        def _draw_footer(self, total):
            self.saveState()
            width = self._pagesize[0]
            y = 0.32 * inch
            self.setStrokeColor(HAIRLINE)
            self.setLineWidth(0.5)
            self.line(MARGIN, y + 10, width - MARGIN, y + 10)
            self.setFont('Helvetica', 8)
            self.setFillColor(MUTED)
            self.drawString(MARGIN, y, '{} · Plan v{} · Printed {}'.format(project_name, version, printed))
            self.drawCentredString(width / 2.0, y, 'Page {} of {}'.format(self._pageNumber, total))
            self.drawRightString(width - MARGIN, y, 'ShowStack • showstack.io')
            self.restoreState()
    return MicPlanCanvas


def _p(text, style):
    return Paragraph(escape(text or ''), style)


def _schedule_story(sched, S, a2_label):
    """One A2's schedule: a heading and table per session; segment and break
    headings are full-width rows inside it."""
    W = usable_width(LANDSCAPE_PAGE)
    widths = [0.8 * inch, 0.85 * inch, 2.6 * inch, 1.3 * inch]
    widths.append(W - sum(widths))
    head_style = S['body'].clone('MpSegHead', fontName='Helvetica-Bold', fontSize=9, leading=11)
    note_style = S['body'].clone('MpNote', fontSize=8.5, leading=10.5)
    name_style = S['body'].clone('MpName', fontSize=10, leading=12)
    story = []
    if not sched['count']:
        story.append(Paragraph('No mics or de-mics for {} in this plan.'.format(a2_label or 'this A2'), S['empty']))
    for sess in sched['sessions']:
        rows = [['Time', 'Action', 'Name', 'RF', 'Note']]
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 8.5),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, BLUE),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TEXTCOLOR', (0, 1), (-1, -1), INK), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 1), (-1, -1), 0.25, HAIRLINE),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        for seg in sess['segments']:
            r = len(rows)
            brk = seg['is_break'] and seg['name'].strip().upper() != 'BREAK'
            text = '{}{}  {}'.format('BREAK — ' if brk else '', seg['name'], seg['time'])
            if seg['line']:
                text += '  ·  line {}'.format(seg['line'])
            if seg['part_no'] and len({s['part_no'] for x in sched['sessions'] for s in x['segments']}) > 1:
                text += '  ·  part {}'.format(seg['part_no'])
            if seg['busy']:
                text += '  ·  {} busy {} of {} min'.format(a2_label or 'A2', seg['busy'], seg['span'])
            rows.append([_p(text, head_style), '', '', '', ''])
            style += [('SPAN', (0, r), (-1, r)),
                      ('BACKGROUND', (0, r), (-1, r), BREAK_BG if seg['is_break'] else SEGMENT_BG)]
            for note in seg['notes']:
                r = len(rows)
                rows.append([_p(note, note_style), '', '', '', ''])
                style += [('SPAN', (0, r), (-1, r)), ('BACKGROUND', (0, r), (-1, r), BREAK_BG)]
            for a in seg['actions']:
                r = len(rows)
                note = a['reason'] + ('  ·  ' + ' · '.join(a['marks']) if a['marks'] else '')
                rows.append([a['time'], a['verb'], _p(a['name'], name_style),
                             a['rf'], _p(note, note_style)])
                style.append(('FONTNAME', (3, r), (3, r), 'Helvetica-Bold'))
                if a['kind'] == 'mic':
                    style.append(('FONTNAME', (1, r), (1, r), 'Helvetica-Bold'))
                if a['late']:
                    style.append(('FONTNAME', (4, r), (4, r), 'Helvetica-Bold'))
        table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle(style))
        story.append(Paragraph('Session {} · {}'.format(sess['number'], sess['time']), S['sub']))
        story.append(table)
    return story


def _pack_rows(plan, apps, actions):
    """[(pack, [wearer, ...])] in RF order; wearers by mic time."""
    mic, demic = {}, {}
    for act in actions:
        key = (act.appearance_id, act.backup)
        if act.kind == 'mic':
            mic[key] = act.start_min
        else:
            demic[key] = act.end_min
    reuse = {(f.get('person'), f.get('row')) for f in plan.flags if f['kind'] in ('reuse', 'pin_reuse')}
    worn = {}
    for a in apps:
        for s in a.assignments.all():
            marks = []
            if s.backup:
                marks.append(MARKS['backup'])
            elif a.pinned_rf is not None or a.pinned_type:
                marks.append(MARKS['pinned'])
            if not s.backup and (a.person_id, a.on_row_id) in reuse:
                marks.append(MARKS['mid_session'])
            if a.is_host:
                marks.append(MARKS['host'])
            worn.setdefault(s.rf_number, []).append({
                'name': a.person_name, 'from': mic.get((a.pk, s.backup), a.on_min),
                'to': demic.get((a.pk, s.backup), a.off_min), 'on': a.on_min, 'off': a.off_min,
                'line': a.on_line, 'marks': marks})
    return [(p, sorted(worn.get(p['rf'], []), key=lambda w: (w['from'], w['name']))) for p in plan.packs]


def _pack_story(plan, apps, actions, S):
    W = usable_width(LANDSCAPE_PAGE)
    widths = [0.6 * inch, 0.75 * inch, 1.7 * inch]
    widths.append(W - sum(widths))
    cell = S['body'].clone('MpPack', fontSize=9, leading=12)
    data = []
    for p, wearers in _pack_rows(plan, apps, actions):
        if p.get('spare'):
            role = 'SPARE — never assigned'
        elif p.get('backup_of'):
            role = p.get('label') or 'BACKUP'
        elif p.get('host'):
            role = 'HOST'
        elif p.get('over'):
            role = 'OVER — past the rig: add channels'
        else:
            role = ''
        lines = ['{}. <b>{}</b> — mic {} · on stage {}–{}{} · de-mic {}{}'.format(
            k + 1, escape(w['name']), hm(w['from']), hm(w['on']), hm(w['off']),
            ' (line {})'.format(escape(w['line'])) if w['line'] else '', hm(w['to']),
            '  <b>{}</b>'.format(' · '.join(w['marks'])) if w['marks'] else '')
            for k, w in enumerate(wearers)]
        data.append(['RF {}'.format(p['rf']), 'Handheld' if p['pool'] == 'HH' else 'Body pack',
                     _p(role, cell), Paragraph('<br/>'.join(lines) or '—', cell)])
    table = data_table(['RF', 'Type', 'Role', 'Order and times (wearer order = Mic Tracker slot order)'],
                       data, widths)
    story = [Paragraph('One row per RF. Times are mic → on stage → de-mic. PINNED: moved by an A2. '
                       'MID-SESSION: goes to someone else within a session.', S['meta'])]
    unused = page.unused_channels(plan)
    if unused:
        story.append(Paragraph('Rig: {} · Unused: {}'.format(escape(page.rig_text(page.plan_values(plan))),
                                                            escape(unused)), S['meta']))
    return story + ([table] if table else [Paragraph('No packs in this plan.', S['empty'])])


def _review_story(cards, S):
    W = usable_width(LANDSCAPE_PAGE)
    widths = [1.0 * inch, 1.1 * inch]
    widths.append(W - sum(widths))
    cell = S['body'].clone('MpReview', fontSize=9, leading=11.5)
    order = sorted(cards, key=lambda c: (c['kind'] != 'conflict', c['part_no'] or 0))
    data = []
    for c in order:
        where = 'Line {}'.format(c['line']) if c['line'] else '—'
        if c['part_no'] and len({x['part_no'] for x in cards if x['part_no']}) > 1:
            where += ' · part {}'.format(c['part_no'])
        text = escape(c['text']) + ('<br/><i>Plan: {}</i>'.format(escape(c['note'])) if c['note'] else '')
        data.append([c['label'].upper(), where, Paragraph(text, cell)])
    table = data_table(['Flag', 'Where', 'What'], data, widths)
    return [table] if table else [Paragraph('Nothing to review.', S['empty'])]


def build_mic_plan_pdf(buffer, *, project, day, plan, apps, actions, parts, cards, a2s, brand, printed_at, zone):
    """Write the PDF into ``buffer`` and return it. ``a2s``: the A2 numbers
    whose schedules to include."""
    S = styles()
    head = page.plan_header(plan, parts)
    title, lines, warnings = header_lines(head, project, day, zone)
    header = _Header(title, lines, warnings, _logo(brand), usable_width(LANDSCAPE_PAGE))
    doc = SimpleDocTemplate(
        buffer, pagesize=LANDSCAPE_PAGE, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + header.height + 6, bottomMargin=FOOTER_MARGIN,
        title='Mic Plan — {} — {}'.format(project.name, day))
    a2_count = max(1, plan.settings.get('a2_count', 1))
    story = []
    for n, a2 in enumerate(a2s):
        sched = schedule.build(plan, actions, a2, parts)
        label = 'A2 {}'.format(a2) if a2_count > 1 else ''
        if n:
            story.append(Spacer(1, 14))
        story.append(section_banner('A2 schedule' + (' — ' + label if label else ''), pagesize=LANDSCAPE_PAGE, S=S))
        story += _schedule_story(sched, S, label)
    story += [Spacer(1, 14), section_banner('Pack sheet', pagesize=LANDSCAPE_PAGE, S=S)]
    story += _pack_story(plan, apps, actions, S)
    story += [Spacer(1, 14), section_banner('Review', pagesize=LANDSCAPE_PAGE, S=S)]
    story += _review_story(cards, S)
    canvas = _canvas_class(project.name, plan.version, stamp(printed_at, zone))
    doc.build(story, onFirstPage=header, onLaterPages=header, canvasmaker=canvas)
    return buffer

