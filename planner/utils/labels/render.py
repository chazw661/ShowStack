"""Label PDFs: layouts in, bytes out. No database, no request.

Each label is painted in three layers, back to front:

1. background  -- BACKGROUNDS[options.background]; 'none' only for now. A
   client-logo watermark goes here later.
2. header band -- HEADER_STYLES[options.header_style]; 'neutral' only for now.
3. name panel  -- a white knockout; every line of presenter text sits on it.

The two registries are the extension points: a new background or header
style is a function registered under a new key, and nothing else changes.
"""

from dataclasses import dataclass
from io import BytesIO

from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas as pdfcanvas

from planner.utils.labels import fonts, layout as L
from planner.utils.labels.data import running_units, single_name_items
from planner.utils.labels.stock import Rect, mm, sheet_positions

BAND = HexColor('#3A4250')
TINT = HexColor('#EEF0F2')
INK = HexColor('#15181C')
RULE = HexColor('#8A9099')


@dataclass(frozen=True)
class Options:
    color: bool = True
    start: int = 1
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    background: str = 'none'
    header_style: str = 'neutral'


# ---------------------------------------------------------------- shapes

def _top_rounded_rect(c, r, radius, fill, stroke):
    """Rect with only its top corners rounded: the header band follows the
    label's corners and meets the panel area square."""
    p = c.beginPath()
    p.moveTo(r.x, r.y)
    p.lineTo(r.right, r.y)
    p.lineTo(r.right, r.top - radius)
    p.arcTo(r.right - 2 * radius, r.top - 2 * radius, r.right, r.top, startAng=0, extent=90)
    p.lineTo(r.x + radius, r.top)
    p.arcTo(r.x, r.top - 2 * radius, r.x + 2 * radius, r.top, startAng=90, extent=90)
    p.close()
    c.drawPath(p, fill=fill, stroke=stroke)


def _inset_for_stroke(r, width):
    # Strokes straddle the path; pull it in so the outer edge stays inside r.
    return Rect(r.x + width / 2, r.y + width / 2, r.w - width, r.h - width)


# ---------------------------------------------------------------- layer 1

def background_none(c, geometry, options):
    pass


BACKGROUNDS = {'none': background_none}


# ---------------------------------------------------------------- layer 2

def header_neutral(c, geometry, options):
    if options.color:
        c.setFillColor(BAND)
        _top_rounded_rect(c, geometry.band, geometry.corner_r, fill=1, stroke=0)
    else:
        c.setStrokeColor(black)
        c.setFillColor(white)
        c.setLineWidth(1)
        _top_rounded_rect(c, _inset_for_stroke(geometry.band, 1),
                          geometry.corner_r - 0.5, fill=1, stroke=1)


HEADER_STYLES = {'neutral': header_neutral}


# ---------------------------------------------------------------- one label

def draw_label(c, layout, options):
    g = layout.geometry
    if options.color:
        # Light tint over the safe area so the white panel reads as a panel.
        c.setFillColor(TINT)
        c.roundRect(g.safe.x, g.safe.y, g.safe.w, g.safe.h, g.corner_r, fill=1, stroke=0)
    BACKGROUNDS[options.background](c, g, options)
    HEADER_STYLES[options.header_style](c, g, options)

    c.setFillColor(white)
    if options.color:
        c.roundRect(g.panel.x, g.panel.y, g.panel.w, g.panel.h, g.panel_r, fill=1, stroke=0)
    else:
        p = _inset_for_stroke(g.panel, 0.5)
        c.setStrokeColor(black)
        c.setLineWidth(0.5)
        c.roundRect(p.x, p.y, p.w, p.h, g.panel_r, fill=1, stroke=1)

    for run in layout.runs:
        if run.role == 'header':
            c.setFillColor(white if options.color else black)
        else:
            c.setFillColor(INK if options.color else black)
        c.setFont(run.font, run.size)
        c.drawString(run.x, run.y, run.text)

    c.setStrokeColor(RULE if options.color else black)
    c.setLineWidth(0.5)
    for x1, y, x2 in layout.rules:
        c.line(x1, y, x2, y)


# ---------------------------------------------------------------- documents

def _canvas(buffer, stock, title):
    fonts.register_fonts()
    # initialFontName: otherwise ReportLab declares Helvetica on every page
    # before anything is drawn, and a viewer missing it may substitute.
    c = pdfcanvas.Canvas(buffer, pagesize=(float(stock.page_w), float(stock.page_h)),
                         pageCompression=1, initialFontName=fonts.REGULAR, initialFontSize=9)
    c.setTitle(title)
    c.setAuthor('ShowStack')
    c.setCreator('ShowStack')
    return c


def build_layouts(data, mode, scope, stock):
    if mode == 'running':
        pages = []
        for unit in running_units(data, scope):
            pages.extend(L.paginate_running(unit, stock))
        return [L.layout_running(p, stock) for p in pages]
    return [L.layout_single(item, stock) for item in single_name_items(data)]


def render_labels_pdf(layouts, stock, options, title='Beltpack labels'):
    buffer = BytesIO()
    c = _canvas(buffer, stock, title)
    if not layouts:
        c.setFont(fonts.REGULAR, 12)
        c.drawCentredString(float(stock.page_w) / 2, float(stock.page_h) / 2,
                            'No presenters assigned in this scope, so there are no labels to print.')
    page = 0
    for lay, (p, position) in zip(layouts, sheet_positions(stock, len(layouts), options.start)):
        while page < p:
            c.showPage()
            page += 1
        r = stock.label_rect(position, options.dx_mm, options.dy_mm)
        c.saveState()
        c.translate(float(r.x), float(r.y))
        draw_label(c, lay, options)
        c.restoreState()
    c.showPage()
    c.save()
    return buffer.getvalue()


def generate_labels_pdf(data, mode, scope, stock, options, title='Beltpack labels'):
    """The whole pipeline from ScopeData: (pdf bytes, number of labels)."""
    layouts = build_layouts(data, mode, scope, stock)
    return render_labels_pdf(layouts, stock, options, title), len(layouts)


# ---------------------------------------------------------------- alignment

def _scale_bar(c, x, y, length_mm, vertical=False):
    """A ruler from (x, y): 1 mm minor ticks every 10 mm, 5 mm half ticks."""
    length = float(mm(length_mm))
    c.setStrokeColor(black)
    c.setLineWidth(0.5)
    if vertical:
        c.line(x, y, x, y - length)
    else:
        c.line(x, y, x + length, y)
    for i in range(0, length_mm + 1, 5):
        tick = 6 if i % 10 == 0 else 3
        d = float(mm(i))
        if vertical:
            c.line(x, y - d, x + tick, y - d)
        else:
            c.line(x + d, y, x + d, y + tick)
    c.setFont(fonts.REGULAR, 6)
    for i in (0, 50, 100):
        d = float(mm(i))
        label = '{} mm'.format(i) if i == 100 else str(i)
        if vertical:
            c.drawString(x + 8, y - d - 2, label)
        else:
            c.drawCentredString(x + d, y + 8, label)


def render_alignment_pdf(stock, options):
    """The fit test: every label outline, its 3.2 mm safe zone, centre
    crosshairs, and a horizontal and a vertical 100 mm bar -- printers can
    scale the two axes differently, and either is enough to ruin a sheet."""
    buffer = BytesIO()
    c = _canvas(buffer, stock, 'Label alignment test - {}'.format(stock.part))
    g = L.geometry(stock)
    for position in range(1, stock.count + 1):
        r = stock.label_rect(position, options.dx_mm, options.dy_mm)
        x, y = float(r.x), float(r.y)
        c.setStrokeColor(black)
        c.setLineWidth(0.25)
        c.setDash()
        c.roundRect(x, y, g.label.w, g.label.h, g.corner_r, fill=0, stroke=1)
        c.setDash(2, 2)
        c.rect(x + g.safe.x, y + g.safe.y, g.safe.w, g.safe.h, fill=0, stroke=1)
        c.setDash()
        cx, cy, arm = x + g.label.w / 2, y + g.label.h / 2, g.size * 0.1
        c.line(cx - arm, cy, cx + arm, cy)
        c.line(cx, cy - arm, cx, cy + arm)
        c.setFont(fonts.REGULAR, 7)
        c.drawCentredString(cx, cy - arm - 9, str(position))

    dx, dy = float(mm(repr(options.dx_mm))), float(mm(repr(options.dy_mm)))
    first, below = stock.label_rect(1), stock.label_rect(1 + stock.cols)
    gap_mid = float(below.top + first.y) / 2
    bar_x = float(first.x) + dx
    _scale_bar(c, bar_x, gap_mid - 4 - dy, 100)

    # The vertical bar runs down the LAST column gap, clear of the
    # horizontal one (which starts at the left margin and is 100 mm long).
    left = stock.label_rect(stock.cols - 1) if stock.cols > 1 else first
    vx = float(left.right + stock.label_rect(stock.cols).x) / 2 - 6 + dx \
        if stock.cols > 1 else float(first.right) + 6 + dx
    _scale_bar(c, vx, float(first.top) - dy, 100, vertical=True)

    third = stock.label_rect(1 + 2 * stock.cols) if stock.rows > 2 else None
    y = (float(below.y + third.top) / 2 if third else float(below.y) - 12) + 4 - dy
    c.setFont(fonts.BOLD, 8)
    c.drawString(bar_x, y, 'Each bar should measure exactly 100 mm. If it does not, '
                 'print at 100% / Actual size, not "Fit to page".')
    c.setFont(fonts.REGULAR, 8)
    c.drawString(bar_x, y - 12, 'ShowStack label alignment: {}. Offset X {:+.1f} mm, Y {:+.1f} mm. '
                 'Dashed line = 3.2 mm safe zone.'.format(stock.part, options.dx_mm, options.dy_mm))
    c.showPage()
    c.save()
    return buffer.getvalue()
