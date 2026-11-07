"""Scrubbed showflow PDFs for the Mic Plan tests, built with ReportLab.

Same shape as the real files (a 14-column table whose header is on page 1
only, rows continuing on later pages; a 9-column "LINE #" variant), with
made-up names. Built in the test run, so there is no binary in the repo and
no real show in it.

What the main file exercises, by line:
  101  "0:05:13" in Start is a video run time, not a clock time
  102  "Sam with Jo Backup mic": Jo Emcee gets the backup hint
  103  welcome line with a title before an ellipsis
  105  "8:10:00" with no AM/PM
  106  same-row send and catch; "Customer Panel Group 1-5" left over; Pat on HH
  108  send list stops at "Morgan" ("...Morgan Robin and Dana have pickles")
  110/111  "Lee Catches Dana," / "Chris, and Robin" split across a page break
  109  Taylor Eve listed as a speaker with no send or catch; Morgan never caught
  115/116  Kim and Alex caught, but still listed in the Keynote Conversation
  117  "KK" only ever in a BSM cue
"""

import io
from xml.sax.saxutils import escape

HEADER_14 = ['', 'Start', 'End', 'Duration', 'Description', 'Speaker Name', 'Location',
             'Video Preset', 'Background / Screen Notes', "DSM's", 'Audio', 'Lighting', 'BSM', 'Notes']


def _row14(line, start='', end='', dur='', desc='', speaker='', bsm='', notes=''):
    return [line, start, end, dur, desc, speaker, '', '', '', '', '', '', bsm, notes]


PAGE_1 = [
    HEADER_14,
    _row14('100', '7:00 AM', '7:45 AM', '0:45:00', 'Doors'),
    _row14('101', '0:05:13', '', '', 'VIDEO: walk-in loop'),
    _row14('102', '7:45 AM', '8:00 AM', '0:15:00', 'Pre-Show', 'Jo Emcee', 'Sam with Jo Backup mic'),
    _row14('103', '', '', '', 'EMCEE: please welcome... Acme President & CEO… Alex Host',
           'Titles: Alex Host', 'Rio Sends Alex'),
    _row14('104', '8:00 AM', '8:30 AM', '0:30:00', 'Opening', 'Alex Host, President & CEO'),
    _row14('105', '8:10:00', '', '', 'PPT'),
    _row14('106', '', '', '0:05:00', 'Guest comes up',
           'Pat Guest - Customer Customer Panel Group 1-5 Alex Host',
           'Sam Sends Pat Guest Lee catches Pat', 'Pat on HH'),
    _row14('107', '', '', '', 'Alex exits', '', 'Rio Catches Alex'),
    _row14('108', '', '', '', 'EMCEE: Please welcome Dana Able, Chris Baker, Robin Cole, Taylor Eve '
           '& Morgan Dee', 'Titles: Dana Able Chris Baker Robin Cole Taylor Eve Morgan Dee',
           'Sam sends Dana, Chris, Robin and Morgan Robin and Dana have pickles'),
]
PAGE_2 = [
    _row14('109', '8:30 AM', '9:00 AM', '0:30:00', 'Building the Future',
           'Dana Able Chris Baker Robin Cole Taylor Eve Morgan Dee'),
    _row14('110', '', '', '', 'Presenters Exit', '', 'Lee Catches Dana,'),
]
PAGE_3 = [
    _row14('111', '', '', '', 'Alex Enters', 'Alex Host', 'Chris, and Robin Rio Sends Alex'),
    _row14('112', '9:00 AM', '9:30 AM', '0:30:00', 'Break'),
    _row14('113', '', '', '', 'EMCEE: please welcome... Kim Keynote', 'Titles: Kim Keynote',
           'Sam sends Kim Keynote'),
    _row14('114', '9:30 AM', '10:00 AM', '0:30:00', 'Keynote', 'Kim Keynote'),
    _row14('115', '', '', '', 'Alex Enters', '', 'Rio Catches Alex and Kim'),
    _row14('116', '10:00 AM', '10:20 AM', '0:20:00', 'Keynote Conversation',
           'Titles (Stacked): Kim Keynote (SL) Alex Host (SR)'),
    _row14('117', '', '', '', 'Award walk', '', 'Sam sends KK'),
    _row14('118', '10:20 AM', '10:30 AM', '0:10:00', 'Close', 'Alex Host', 'Rio Catches KK'),
]
MAIN_PAGES = [PAGE_1, PAGE_2, PAGE_3]

# A later revision of the same part: same span, one extra cue.
REVISED_PAGES = [PAGE_1, PAGE_2, PAGE_3[:-1] + [
    _row14('118', '10:20 AM', '10:30 AM', '0:10:00', 'Close', 'Alex Host', 'Rio Catches KK and Alex'),
]]

# A PM part: no time overlap with the main file.
PM_PAGES = [[
    HEADER_14,
    _row14('200', '1:00 PM', '1:30 PM', '0:30:00', 'Afternoon', 'Alex Host', ''),
    _row14('201', '', '', '', 'Exit', '', 'Rio Catches Alex'),
    _row14('202', '1:30 PM', '2:00 PM', '0:30:00', 'Wrap', 'Jo Emcee', 'Sam with Jo Backup mic'),
]]

HEADER_9 = ['LINE #', 'Start', 'End', 'Duration', 'Description', 'Speaker Name', 'Video Preset',
            "DSM's", 'BSM']
NINE_COLUMN_PAGES = [[
    HEADER_9,
    ['1', '9:00 AM', '9:20 AM', '0:20:00', 'Welcome', 'Alex Host', '', '', ''],
    ['2', '', '', '', 'Please welcome Pat Guest', 'Titles: Pat Guest', '', '', 'Sam sends Pat'],
    ['3', '9:20 AM', '9:40 AM', '0:20:00', 'Talk', 'Pat Guest', '', '', ''],
    ['4', '', '', '', 'Exit', '', '', '', 'Lee catches Pat'],
]]

# Upper-case layout (seen in a real "BSM" export): legend rows above the
# header, "DURATIO N" wrapped mid-word, SCENE # and PROPS columns, Duration
# left blank, stage directions inside Speaker cells, a "Title, Company, Name"
# welcome line, and an affiliation after a dash.
LEGEND_10 = [['', '', 'SESSION SEGMENT', '', '', 'Questions', '', '', '', ''],
             ['', '', 'VOG', '', '', '', '', '', '', ''],
             ['', '', 'VIDEO', '', '', '', '', '', '', '']]
HEADER_UPPER = ['LINE #', 'SCENE #', 'START', 'END', 'DURATIO N', 'DESCRIPTION', 'SPEAKER',
                'STAGE LOCATION', 'PROPS', 'BSM']


def _row_upper(line, start='', end='', desc='', speaker='', bsm=''):
    return [line, '', start, end, '', desc, speaker, '', '', bsm]


UPPER_PAGES = [LEGEND_10 + [
    HEADER_UPPER,
    _row_upper('201', '8:30 AM', '9:00 AM', 'Open Doors'),
    _row_upper('206', desc='VOG: PLEASE WELCOME BACK TO THE STAGE, ROBIN COLE & DANA ABLE'),
    _row_upper('207', desc='TITLE: Robin & Dana', bsm='Ivo Sends Robin and Dana'),
    _row_upper('208', '9:00 AM', '9:10 AM', 'Welcome',
               'Robin Cole Dana Able Enter: BSL Exit: BSR'),
    _row_upper('213', desc='Robin departs', bsm='Uma Catches Robin'),
    _row_upper('215', desc='Dana intros Kim', bsm='Uma Catches Dana Ivo Sends Kim Needs Clicker'),
    _row_upper('217', '9:10 AM', '9:30 AM', 'Keynote', 'Kim Keynote {CLICKER 1} Enter: BSL Exit: BSR'),
    _row_upper('225', desc='Kim wraps', bsm='Uma Catches Kym Grab Clicker'),
    _row_upper('228', desc='VOG: please welcome to the stage, from Initech, Senior Director, '
                           'Product Management, Lee Panel'),
    _row_upper('230', '9:30 AM', '9:50 AM', 'Panel',
               'Lee Panel - Initech AI (Partner) Max Second - Hooli', 'Ivo Sends Lee and Max'),
    _row_upper('238', desc='All depart', bsm='Uma Catches Lee and Max'),
]]

# Wide layout with the line numbers under an "a" header, "H:MM" segment
# durations, crewless "Send X" cues, one stray clock time ahead of the rest,
# a "Title, Company, Name" welcome, and a second page of empty ruled grid.
HEADER_A = ['a', 'Start', 'End', 'Duration', 'Description', 'Speaker Name', 'BSM', 'Notes', '']


def _row_a(line, start='', end='', dur='', desc='', speaker='', bsm=''):
    return [line, start, end, dur, desc, speaker, bsm, '', '']


A_COLUMN_PAGES = [
    [HEADER_A,
     _row_a('101', '8:30:00 AM', '9:00 AM', '0:30', 'Doors Open'),
     _row_a('105', '9:00 AM', '9:00 AM', '', 'VT2 - Alert', bsm='Send Person 1'),
     _row_a('106', desc='PERSON ON STAGE SAYS SCRIPT', speaker='Zed'),
     _row_a('119', '9:33 AM', '', '', 'VOG: Please Welcome to the stage, Vice President, Acme '
                                     'Consulting, Alex Host', bsm='Send Alex'),
     _row_a('120', '9:00 AM', '9:10 AM', '0:10', 'Opening', 'Alex Host'),
     _row_a('121', '9:10 AM', '9:35 AM', '0:25', 'Talk', 'Pat Guest')],
    [[''] * len(HEADER_A) for _ in range(30)],
]

# No send/catch cues at all: a colour legend above the header, an image in a
# cell, "+" between speakers, a lower-case particle surname, "St. Clair", and
# handheld callouts that name nobody (they mean the row's speakers).
LEGEND_9 = [['VIDEO', 'GFX', 'AUDIO', '', '', '', '', '', ''],
            ['Purple', 'Green', 'Orange', '', '', '', '', '', '']]
IMAGE = object()   # build_pdf puts a small picture in this cell

CUE_FREE_PAGES = [LEGEND_9 + [
    HEADER_9,
    ['101', '12:45 PM', '1:00 PM', '0:15:00', 'Doors', 'DJ Audio Throughout', '', '', ''],
    ['108', '1:00 PM', '1:10 PM', '0:10:00', 'Warm-Up', 'Nina Host', IMAGE, '',
     'no clicker, handheld'],
    ['130', '1:50 PM', '1:55 PM', '0:05:00', 'MC returns', 'Nell Avery + Rory vandeberg', '', '',
     'no clicker, handhelds'],
    ['160', '3:32 PM', '3:37 PM', '0:05:00', 'Introduce Speaker', 'Ike Morrow & Tess St. Clair',
     '', '', 'no clicker'],
    ['172', '3:57 PM', '4:17 PM', '0:20:00', 'Talk', 'Clair Dunn', '', '', ''],
    ['198', '', '', '', 'Special Moment - Need HH with Ike', '', '', '', ''],
]]

# Client E layout: "LINE #" 14 columns, no send/catch cues, segment rows that
# are VOG lines or "END RECORDS", "TITLE:" / "N-UP TITLE:" Speaker cells, a
# "Dr." name later called "Dr. Reyes", first names that mean whoever was
# introduced last, and presenters named only in a description. Exits as
# Client E writes them (PR 5.2): on another person's walk-on row ("Ned
# welcomes ... Ned exits"), "Max re-enters", "Ola exits when ...",
# "Max and Dr. Reyes Exit", and a group with someone staying.
HEADER_E = ['LINE #', 'Start', 'End', 'Duration', 'Description', 'Speaker Name', 'Enter Exit',
            'Video Preset', 'Background / Screen Notes', 'DSMs', 'Audio', 'Lighting', 'BSM', 'Notes']

CLIENT_E_PAGES = [[
    HEADER_E,
    _row14('300', '8:00 AM', '8:45 AM', '0:45:00', 'Opening Session'),
    _row14('301', desc='Max enters', speaker='Max Pine'),
    _row14('302', desc='Ola enters', speaker='Ola Brand'),
    _row14('303', desc='Ned joins Max & Ola', speaker='Ned Quill'),
    _row14('304', desc='Ned welcomes Vic to stage Max exits', speaker='TITLE: Vic Stone'),
    _row14('305', desc='Scheduling demo', speaker='Ned, Ola, Vic'),
    _row14('306', desc='Max re-enters with Dr. Una Reyes', speaker='TITLE:\nDr. Una Reyes'),
    _row14('307', desc='Exam demo Ola exits when the exam is complete', speaker='Ned, Max, Dr. Reyes'),
    _row14('308', desc='Max and Dr. Reyes Exit. Gil Ware enters', speaker='TITLE: Gil Ware'),
    _row14('309', desc='Billing demo, then Gil Ware Exits', speaker='Ned, Gil'),
    _row14('310', desc='Ned welcomes Bo and Zed to stage Ned exits', speaker='2-UP TITLE: Bo Lark & Zed Moss'),
    _row14('311', desc='Amy introduces the 3 presenters. Cy Dorn, Eli Fay, Hal Grey'),
], [
    _row14('312', '8:45 AM', '9:00 AM', '0:15:00', 'END RECORDS'),
    _row14('313', desc='BREAK'),
    _row14('314', '9:00 AM', '9:45 AM', '0:45:00',
           'VOG: Please welcome our next group of presenters to stage. Kit Ames, Dr. Lou Penn'),
    _row14('315', desc='The Future Panel',
           speaker='4-UP TITLE: Kit Ames Dr. Lou Penn Dr. Sol Tate Vic Stone'),
    _row14('316', desc='Game', speaker='Ann Pike Vic Dahl'),
    _row14('317', desc='Vic sits', speaker='Vic'),
    _row14('318', desc='Both on', speaker='Vic Stone & Vic Dahl'),
    _row14('319', desc='Q&A', speaker='Vic'),
    _row14('320', desc='Panelists exit (Kit Ames stays)'),
]]

NO_HEADER_PAGES = [[
    ['When', 'What', 'Who'],
    ['9:00', 'Doors', ''],
]]


# Client F: CUE / Event / Presenter headers, no BSM column, a show title and date
# above a header repeated on every page, "X" for nobody, mic callouts in Audio,
# and a preset list continuing the same grid after the last line.
HEADER_F = ['CUE', 'Start', 'End', 'Duration', 'Event', 'Presenter', 'Speaker Timer', 'Screen Preset',
            'DSM Preset', 'Screens', 'Cameras', 'Audio', 'FOH Stage LIGHTS', 'Notes']


def _row_f(line='', start='', end='', dur='', event='', presenter='', audio='', notes=''):
    return [line, start, end, dur, event, presenter, '', '', '', '', '', audio, '', notes]


TITLES_F = [_row_f('Acme Forum Day 1'), _row_f('Thursday, March 5')]
CLIENT_F_PAGES = [
    TITLES_F + [
        HEADER_F,
        _row_f(event='Program speaker timer settings'),
        _row_f('100', '8:15 AM', '8:30 AM', '0:15:00', 'Doors Open', 'X',
               'Walk-In Playlist A2: Mic Presenters Lav #1: Ann Reed Lav #2: Bo Lund'),
        _row_f('', 'Roll Records'),
        _row_f('101', '', '', '', 'VOG: Please welcome, Acme President, Ann Reed', 'Ann Reed'),
        _row_f('102', '8:30 AM', '9:00 AM', '0:30:00', 'Ann Reed - Opening (20 slides)',
               'Ann Reed (Prompter Script)', 'Lav 1', 'No clicker'),
        _row_f(event='Ann departs'),
        _row_f('103', '9:00 AM', '9:30 AM', '0:30:00', 'Bo Lund - Keynote', 'Bo Lund', 'Lav 2', 'Clicker'),
        _row_f(event='Slide 40 - Video embedded, Bo walks off stage, Preset 5'),
    ],
    TITLES_F + [
        HEADER_F,
        _row_f('', '9:30 AM', '9:45 AM', '0:15:00', 'Break', 'X', 'Walk-In Playlist'),
        _row_f('104', '', '', '', 'VOG: Please welcome Cleo Hart, Tom Kerr and Ned Marsh',
               'Cleo Hart Tom Kerr Ned Marsh'),
        _row_f('105', '9:45 AM', '10:15 AM', '0:30:00', 'Fireside Chat',
               'Cleo (SL chair) Tom K. (loveseat) Ned (SR chair)', 'Lav 3,4,5'),
        _row_f(event='Cleo intros Sue, shakes hands, then departs stage'),
        _row_f('106', '10:15 AM', '10:45 AM', '0:30:00', 'Sue Tran - Closing', 'Sue Tran', 'Lav 1'),
        _row_f(event='Sue Tran exits'),
        _row_f('', 'PRESETS'),
        _row_f('', 'Preset', 'Nickname', 'STAGE RIGHT', 'Arches', 'STAGE LEFT Outboard', 'DSM 5 / 6'),
        _row_f('', '1', 'MoGFX - Full Canvas', 'Millumin', 'Millumin', 'Millumin', 'Prompter'),
    ],
    TITLES_F + [
        HEADER_F,
        _row_f('', '2', '3:1 Content (Main)', '1:1 IMAG', 'Millumin', '3:1 GFX1 / 1:1 IMAG', 'Current'),
    ],
]

# Client G: a Word-style document, no table. Each date repeats the headings.
DOCUMENT_LINES = [
    'Acme Leadership Meeting', 'Showflow #6', 'Wednesday, March 4', 'TIME EVENT/ PRESENTER SUPPORT',
    '8:00 am Crew Call', '2:02 VOG: Ladies & Gentlemen please welcome Ann Reed Play-on',
    '2:02 \u2013 2:15 Ann Reed Title', '-Welcome',
]


def build_document_pdf(lines):
    """PDF bytes: plain paragraphs, portrait letter, no table."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    style = getSampleStyleSheet()['BodyText']
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter).build([Paragraph(escape(line), style) for line in lines])
    return buf.getvalue()


def _cell(cell, style):
    from reportlab.platypus import Image, Paragraph
    if cell is IMAGE:
        from PIL import Image as PILImage
        png = io.BytesIO()
        PILImage.new('RGB', (24, 12), (120, 40, 160)).save(png, format='PNG')
        png.seek(0)
        return Image(png, width=24, height=12)
    return Paragraph(escape(cell), style) if cell else ''


def build_pdf(pages):
    """PDF bytes: one ruled table per page, landscape letter."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Table, TableStyle

    style = getSampleStyleSheet()['BodyText']
    style.fontSize, style.leading = 6, 7
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=18, rightMargin=18,
                            topMargin=18, bottomMargin=18)
    story = []
    width = landscape(letter)[0] - 36
    for n, rows in enumerate(pages):
        cols = len(rows[0])
        data = [[_cell(cell, style) for cell in row] for row in rows]
        table = Table(data, colWidths=[width / cols] * cols)
        table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                                   ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story.append(table)
        if n + 1 < len(pages):
            story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()


# The same Client E part revised: line 311 (the "introduces the 3 presenters"
# line people get added from) is gone.
CLIENT_E_WITHOUT_311 = [[row for row in page if row[0] != '311'] for page in CLIENT_E_PAGES]
