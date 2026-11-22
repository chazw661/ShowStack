"""The wiring diagram as one standalone SVG string, drawn from ``layout``.

Every name in it is user data (device names, labels, PA Destination text, amp
input text), so every text node and attribute value goes through ``_e`` --
input slot labels too, which name their source ("XLR 1 ← Y001 Out 3 (Left)"). No
script, no external references; the styles are inline so the file stands on
its own. Nothing is shortened: ``layout`` has wrapped every text into lines,
and a line or tspan is drawn per line. Each box and line keeps its full text
in a ``<title>``, the hover tooltip.
"""
from html import escape

from planner.connections.layout import (BOX_W, COLUMN_HINTS, GROUP_HEAD, HINT_Y, KEY_PAD, LABEL_LH,
                                        LINE_H, MARGIN, SLOT_LH, TITLE_Y)

STYLE = """
.wd-bg { fill: #ffffff; }
.wd-col { font: 600 12px system-ui, -apple-system, sans-serif; fill: #555; letter-spacing: .04em; text-transform: uppercase; }
.wd-col-hint { font: italic 10px system-ui, -apple-system, sans-serif; fill: #666; }
.wd-group { font: 600 11px system-ui, -apple-system, sans-serif; fill: #333; }
.wd-group-rule { stroke: #bbb; stroke-width: 1; }
.wd-box rect { fill: #f4f7fb; stroke: #4a6f9a; stroke-width: 1.4; }
.wd-box.location rect { fill: #f3f6ef; stroke: #6b8a4a; }
.wd-box.unlinked rect { fill: #fff8e6; stroke: #b7791f; stroke-dasharray: 5 3; }
.wd-box .t { font: 600 12px system-ui, -apple-system, sans-serif; fill: #111; }
.wd-box .s { font: 11px system-ui, -apple-system, sans-serif; fill: #555; }
.wd-box .p { font: 10px system-ui, -apple-system, sans-serif; fill: #2b4c7e; }
.wd-edge { fill: none; stroke: #2b4c7e; stroke-width: 1.4; }
.wd-edge.inferred { stroke-dasharray: 6 4; }
.wd-edge.unlinked { stroke: #b7791f; stroke-dasharray: 4 3; }
.wd-edge.network { stroke: #2f855a; stroke-dasharray: 2 3; stroke-width: 1.8; }
.wd-label { font: 11px system-ui, -apple-system, sans-serif; fill: #222; }
.wd-label.unlinked { fill: #8a5a12; font-weight: 600; }
.wd-label.network { fill: #2f855a; }
.wd-edge.unset { stroke: #7a7a7a; stroke-dasharray: 1 3; stroke-width: 1.8; }
.wd-label.unset { fill: #6b6b6b; font-style: italic; }
.wd-edge.b { stroke-opacity: .45; }
.wd-label.b { fill-opacity: .8; }
.wd-end { fill: #2b4c7e; }
.wd-key rect { fill: #ffffff; stroke: #1f2d3d; stroke-width: 1.2; }
.wd-key text { font: 700 11px system-ui, -apple-system, sans-serif; fill: #111; }
"""


def _e(value):
    return escape(str(value), quote=True)


def _n(value):
    return f'{value:.1f}'.rstrip('0').rstrip('.')


def _lines(lines, x, line_h):
    """A text's lines as tspans ``line_h`` apart. Each but the last ends in
    the space it was broken at, so the text still reads (and copies) whole."""
    if len(lines) == 1:
        return _e(lines[0])
    out = []
    for i, line in enumerate(lines):
        dy = f' dy="{_n(line_h)}"' if i else ''
        gap = ' ' if i < len(lines) - 1 else ''
        out.append(f'<tspan x="{_n(x)}"{dy}>{_e(line)}{gap}</tspan>')
    return ''.join(out)


def _slots(box):
    out = []
    x = box.x + 8
    for i, (label, lines) in enumerate(zip(box.slots, box.slot_lines)):
        if not label:
            continue
        y = box.row_y(i)
        out.append(f'<text class="p" data-slot="{_e(label)}" x="{_n(x)}" y="{_n(y + 3.5)}">'
                   f'{_lines(lines, x, SLOT_LH)}</text>')
    return ''.join(out)


def _box(box):
    x = box.x + 8
    return (
        f'<g class="wd-box {_e(box.style)}" data-node="{_e(box.node)}" data-box="{_e(box.id)}">'
        f'<title>{_e(box.label)}</title>'
        f'<rect x="{_n(box.x)}" y="{_n(box.y)}" width="{_n(box.w)}" height="{_n(box.h)}" rx="4"/>'
        + ''.join(f'<text class="{cls}" x="{_n(x)}" y="{_n(box.y + dy)}">{_e(line)}</text>'
                  for cls, line, dy in box.text_rows) +
        f'{_slots(box)}'
        '</g>')


def _route(route):
    path = ' '.join(f'{"M" if i == 0 else "L"}{_n(x)} {_n(y)}' for i, (x, y) in enumerate(route.points))
    end_x, end_y = route.points[-1]
    classes = ' '.join(route.classes)
    label = ''
    if route.key:
        # A boxed badge on the line itself, drawn over it, next to the source box.
        x0, y0, x1, y1 = route.badge
        label = (f'<g class="wd-key"><rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0)}" '
                 f'height="{_n(y1 - y0)}" rx="3"/>'
                 f'<text data-key="{route.key}" x="{_n(x0 + KEY_PAD)}" y="{_n(route.label_y)}">'
                 f'[{route.key}]</text></g>')
    elif route.lines:
        # The last line sits just above the run; the others stack above it.
        top = route.label_y - (len(route.lines) - 1) * LABEL_LH
        label = (f'<text class="wd-label {_e(classes)}" x="{_n(route.label_x)}" y="{_n(top)}">'
                 f'{_lines(route.lines, route.label_x, LABEL_LH)}</text>')
    return (
        f'<g class="wd-link" data-edge="{_e(route.id)}">'
        f'<title>{_e(route.label_full)}</title>'
        f'<path class="wd-edge {_e(classes)}" d="{path}"/>'
        f'<path class="wd-end" d="M{_n(end_x)} {_n(end_y)} l-6 -3.5 v7 z"/>'
        f'{label}'
        '</g>')


def render(lay, title=''):
    w, h = _n(lay.width), _n(lay.height)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" class="wd-svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" role="img" aria-label="{_e(title or "Wiring diagram")}">',
           f'<style>{STYLE}</style>',
           f'<rect class="wd-bg" width="{w}" height="{h}"/>']
    for text, x, _ in lay.columns:
        out.append(f'<text class="wd-col" x="{_n(x)}" y="{_n(MARGIN + TITLE_Y)}">{_e(text)}</text>')
        if text in COLUMN_HINTS:
            out.append(f'<text class="wd-col-hint" x="{_n(x)}" y="{_n(MARGIN + HINT_Y)}">'
                       f'{_e(COLUMN_HINTS[text])}</text>')
    for group in lay.groups:
        y = group.y + GROUP_HEAD - 8
        last = y + LINE_H * (len(group.lines) - 1)
        out.append(f'<text class="wd-group" x="{_n(group.x)}" y="{_n(y)}">'
                   f'{_lines(group.lines, group.x, LINE_H)}</text>'
                   f'<line class="wd-group-rule" x1="{_n(group.x)}" x2="{_n(group.x + BOX_W)}" '
                   f'y1="{_n(last + 4)}" y2="{_n(last + 4)}"/>')
    out += [_route(r) for r in lay.routes]
    out += [_box(b) for b in lay.boxes]
    out.append('</svg>')
    return ''.join(out)
