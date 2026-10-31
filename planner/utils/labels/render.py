"""Label PDFs: layouts in, bytes out. No database, no request.

Each label is painted back to front:

1. background -- the brand colour (the default is charcoal, K85), full
   bleed: BLEED_MM past the die line on every side.
2. accents    -- ACCENT_STYLES[brand.style]: angled bars in the bottom-right
   corner, in the footer the layout keeps clear of text, or a stripe along
   the bottom edge, outside the safe zone.
3. logo       -- top-right in the header, where the layout placed it.
4. text       -- white or black by the brand's contrast rule; session
   dividers half way between the text colour and the background.

In black & white everything is black toner only: the background and accents
become greys (planner.utils.labels.brand) and the logo greyscale. The default
theme is K-only in colour mode too.

ACCENT_STYLES is the extension point: a new style is a function registered
under a new key (and a footer height in brand.ACCENT_FOOTER_MM).
"""

from dataclasses import dataclass
from io import BytesIO

from reportlab.lib.colors import CMYKColor, Color, HexColor, black
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from planner.utils.labels import fonts, layout as L
from planner.utils.labels.brand import ACCENT_FOOTER_MM, DEFAULT, Brand
from planner.utils.labels.data import RunningUnit, SingleItem, running_units, single_name_items
from planner.utils.labels.stock import BLEED_MM, Rect, mm, sheet_positions


@dataclass(frozen=True)
class Options:
    color: bool = True
    start: int = 1
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    brand: Brand = DEFAULT


def bleed():
    return float(mm(BLEED_MM))


def K(percent):
    return CMYKColor(0, 0, 0, percent / 100)


# ---------------------------------------------------------------- colours

@dataclass(frozen=True)
class Paint:
    bg: object
    text: object
    rule: object
    accents: tuple
    grey_logos: bool


def _mix(a, b):
    return Color((a.red + b.red) / 2, (a.green + b.green) / 2, (a.blue + b.blue) / 2)


def paint_for(brand, color):
    """The colours one PDF is painted in. Colour mode with a brand
    background is RGB; everything else -- the default theme, and black &
    white -- is black toner only."""
    text_k = 0 if brand.text_white else 100
    if color and brand.bg:
        bg = HexColor(brand.bg)
        text = Color(1, 1, 1) if brand.text_white else Color(0, 0, 0)
        return Paint(bg, text, _mix(bg, text),
                     tuple(HexColor(a) for a in brand.accents), False)
    bg_k = brand.bg_k
    if color:
        accents = tuple(HexColor(a) for a in brand.accents)
    else:
        greys, _ = brand.bw_accents()
        accents = tuple(K(k) for k in greys)
    return Paint(K(bg_k), K(text_k), K((bg_k + text_k) / 2), accents, not color)


class _Logos:
    """One ImageReader per logo per PDF: ReportLab then embeds each image
    once, however many labels print it."""

    def __init__(self, brand, grey):
        self.brand, self.grey, self.cache = brand, grey, {}

    def __getitem__(self, kind):
        if kind not in self.cache:
            from planner.utils.labels.palette import greyscale_png
            data = self.brand.logo(kind).content
            self.cache[kind] = ImageReader(BytesIO(greyscale_png(data) if self.grey else data))
        return self.cache[kind]


# ---------------------------------------------------------------- layer 2: accents

def _polygon(c, points):
    p = c.beginPath()
    p.moveTo(*points[0])
    for point in points[1:]:
        p.lineTo(*point)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


# Corner bars, as fractions of the label side S: three "/" parallelograms
# from the bottom-right corner into the bleed. The first sits on the bottom
# edge and runs into the bleed below it too.
BAR_LEFTS = (0.50, 0.64, 0.78)
BAR_PITCH = 8.4 / 144
BAR_HEIGHT = 6.2 / 144
BAR_SLANT = 0.75
STRIPE_MM = 2


def corner_bars_zone(g):
    """Everything the corner bars may cover, bleed included: from 0.50 S
    to the right bleed, from the bottom bleed to the top of the footer."""
    b = bleed()
    top = g.safe.y + float(mm(ACCENT_FOOTER_MM['corner_bars']))
    x = BAR_LEFTS[0] * g.size
    return Rect(x, -b, g.label.right + b - x, top + b)


def corner_bars(g, n):
    """Label-local polygons for ``n`` bars, bottom first."""
    b, s = bleed(), g.size
    zone = corner_bars_zone(g)
    bars = []
    for i in range(min(n, len(BAR_LEFTS))):
        y0 = -b if i == 0 else i * BAR_PITCH * s
        y1 = min(i * BAR_PITCH * s + BAR_HEIGHT * s, zone.top)
        x0 = BAR_LEFTS[i] * s
        bars.append([(x0, y0), (g.label.right + b, y0), (g.label.right + b, y1),
                     (x0 + BAR_SLANT * (y1 - y0), y1)])
    return bars


def edge_stripe(g, n):
    """Label-local rects (x, y, w, h): the full bled width split equally,
    STRIPE_MM on the label plus the bleed below."""
    b = bleed()
    width = (g.label.w + 2 * b) / n
    height = float(mm(STRIPE_MM)) + b
    return [(-b + i * width, -b, width, height) for i in range(n)]


def accent_none(c, g, paint):
    pass


def accent_corner_bars(c, g, paint):
    for colour, points in zip(paint.accents, corner_bars(g, len(paint.accents))):
        c.setFillColor(colour)
        _polygon(c, points)


def accent_edge_stripe(c, g, paint):
    for colour, (x, y, w, h) in zip(paint.accents, edge_stripe(g, len(paint.accents))):
        c.setFillColor(colour)
        # A hair wider than its share, so no paper shows between stripes.
        c.rect(x, y, w + 0.05, h, fill=1, stroke=0)


ACCENT_STYLES = {
    'none': accent_none,
    'corner_bars': accent_corner_bars,
    'edge_stripe': accent_edge_stripe,
}


# ---------------------------------------------------------------- one label

def draw_label(c, layout, options, paint=None, logos=None):
    brand = options.brand
    paint = paint or paint_for(brand, options.color)
    g = layout.geometry
    b = bleed()

    c.setFillColor(paint.bg)
    c.rect(-b, -b, g.label.w + 2 * b, g.label.h + 2 * b, fill=1, stroke=0)
    ACCENT_STYLES[brand.style](c, g, paint)

    if layout.logo:
        kind, r = layout.logo
        logos = logos or _Logos(brand, paint.grey_logos)
        c.drawImage(logos[kind], r.x, r.y, r.w, r.h, mask='auto')

    c.setFillColor(paint.text)
    for run in layout.runs:
        c.setFont(run.font, run.size)
        c.drawString(run.x, run.y, run.text)

    c.setStrokeColor(paint.rule)
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


def build_layouts(data, mode, stock, frame=L.PLAIN):
    if mode == 'running':
        pages = []
        for unit in running_units(data):
            pages.extend(L.paginate_running(unit, stock, frame))
        return [L.layout_running(p, stock, frame) for p in pages]
    return [L.layout_single(item, stock, frame) for item in single_name_items(data)]


def render_labels_pdf(layouts, stock, options, title='Beltpack labels'):
    buffer = BytesIO()
    c = _canvas(buffer, stock, title)
    if not layouts:
        c.setFont(fonts.REGULAR, 12)
        c.drawCentredString(float(stock.page_w) / 2, float(stock.page_h) / 2,
                            'No presenters assigned in these sessions, so there are no labels to print.')
    page = 0
    paint = paint_for(options.brand, options.color)
    logos = _Logos(options.brand, paint.grey_logos)
    for lay, (p, position) in zip(layouts, sheet_positions(stock, len(layouts), options.start)):
        while page < p:
            c.showPage()
            page += 1
        r = stock.label_rect(position, options.dx_mm, options.dy_mm)
        c.saveState()
        c.translate(float(r.x), float(r.y))
        draw_label(c, lay, options, paint, logos)
        c.restoreState()
    c.showPage()
    c.save()
    return buffer.getvalue()


def generate_labels_pdf(data, mode, stock, options, title='Beltpack labels'):
    """The whole pipeline from ScopeData: (pdf bytes, number of labels)."""
    layouts = build_layouts(data, mode, stock, options.brand.frame())
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


def _swatches(c, x, top, brand):
    """The brand's colours as printed: a square of each beside the grey it
    becomes in black & white, labelled with its hex. Printed on the venue's
    printer before a full sheet, it shows a colour shift while the colours
    can still be changed."""
    entries = [('Background', brand.bg, brand.bg_k)]
    greys, _ = brand.bw_accents()
    entries += [('Accent {}'.format(i + 1), hexv, k)
                for i, (hexv, k) in enumerate(zip(brand.accents, greys))]
    side, step = float(mm(8)), float(mm(45))
    c.setFont(fonts.BOLD, 7)
    c.setFillColor(black)
    c.drawString(x, top, 'Colour check: compare with the branding page. '
                 'The small square is what black & white prints.')
    y = top - 5 - side
    for i, (title, hexv, k) in enumerate(entries):
        sx = x + i * step
        c.setFillColor(HexColor(hexv) if hexv else K(k))
        c.rect(sx, y, side, side, fill=1, stroke=0)
        c.setFillColor(K(k))
        c.rect(sx + side + 2, y, side / 2, side / 2, fill=1, stroke=0)
        c.setFillColor(black)
        tx = sx + 1.5 * side + 6
        c.setFont(fonts.BOLD, 6.5)
        c.drawString(tx, y + side - 7, title)
        c.setFont(fonts.REGULAR, 6.5)
        c.drawString(tx, y + side - 15, hexv or 'K{}'.format(k))
        c.drawString(tx, y + side - 23, 'B&W K{}'.format(k))


def render_alignment_pdf(stock, options):
    """The fit test: every label outline, its 3.2 mm safe zone and 2.5 mm
    bleed, centre crosshairs, a horizontal and a vertical 100 mm bar --
    printers can scale the two axes differently, and either is enough to
    ruin a sheet -- and a swatch of each brand colour."""
    buffer = BytesIO()
    c = _canvas(buffer, stock, 'Label alignment test - {}'.format(stock.part))
    g = L.geometry(stock)
    b = bleed()
    for position in range(1, stock.count + 1):
        r = stock.label_rect(position, options.dx_mm, options.dy_mm)
        x, y = float(r.x), float(r.y)
        c.setStrokeColor(black)
        c.setLineWidth(0.25)
        c.setDash()
        c.roundRect(x, y, g.label.w, g.label.h, g.corner_r, fill=0, stroke=1)
        c.setDash(2, 2)
        c.rect(x + g.safe.x, y + g.safe.y, g.safe.w, g.safe.h, fill=0, stroke=1)
        c.setDash(0.5, 1.5)
        c.rect(x - b, y - b, g.label.w + 2 * b, g.label.h + 2 * b, fill=0, stroke=1)
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
                 'Dashed = 3.2 mm safe zone; dotted = 2.5 mm bleed.'.format(
                     stock.part, options.dx_mm, options.dy_mm))

    # The swatches go in the gap above the bottom row of labels.
    if stock.rows > 1:
        above = stock.label_rect(1 + (stock.rows - 2) * stock.cols)
        _swatches(c, bar_x, float(above.y) - b - 9 - dy, options.brand)
    c.showPage()
    c.save()
    return buffer.getvalue()


# ---------------------------------------------------------------- branding preview

# Made-up sample content for the branding page: never a project's own names.
PREVIEW_RUNNING = RunningUnit(
    pack=2, header=('Day 1', '9:00a', 'General Session'),
    groups=(('Mark Phezan', 'Amanda Phillen'), ('Phil Jacobs', 'Nguyễn Đặng')),
    compact=('Day 1', '9:00a'))
PREVIEW_SINGLE = SingleItem(pack=1, day_label='Day 1', name='Sarah McMillan',
                            time='9:00a', session='Session 1 +2')


def preview_layouts(brand, stock):
    frame = brand.frame()
    running = L.paginate_running(PREVIEW_RUNNING, stock, frame)[0]
    return (L.layout_running(running, stock, frame),
            L.layout_single(PREVIEW_SINGLE, stock, frame))


def render_preview_pdf(brand, stock):
    """One page: a running-order and a single-name label, in colour and in
    black & white, each clipped to its die line as it will look peeled."""
    s = float(stock.label_w)
    gap, caption = 0.35 * 72, 14
    width = 2 * s + 3 * gap
    height = 2 * (s + caption) + 3 * gap
    buffer = BytesIO()
    fonts.register_fonts()
    c = pdfcanvas.Canvas(buffer, pagesize=(width, height), pageCompression=1,
                         initialFontName=fonts.REGULAR, initialFontSize=9)
    c.setTitle('Label branding preview')
    running, single = preview_layouts(brand, stock)
    for row, (lay, name) in enumerate(((running, 'Running order'), (single, 'Single name'))):
        for col, color in enumerate((True, False)):
            x = gap + col * (s + gap)
            y = height - (row + 1) * (s + caption + gap)
            options = Options(color=color, brand=brand)
            c.saveState()
            c.translate(x, y + caption)
            p = c.beginPath()
            p.roundRect(0, 0, s, float(stock.label_h), float(stock.corner_r))
            c.clipPath(p, stroke=0, fill=0)
            draw_label(c, lay, options)
            c.restoreState()
            c.setFillColor(black)
            c.setFont(fonts.REGULAR, 7)
            c.drawCentredString(x + s / 2, y + 3, '{} · {}'.format(name, 'colour' if color else 'black & white'))
    c.showPage()
    c.save()
    return buffer.getvalue()
