"""The wiring diagram as one standalone SVG string, drawn from ``layout``.

Every name in it is user data (device names, labels, PA Destination text, amp
input text), so every text node and attribute value goes through ``_e`` --
input slot labels too, though today they are built from numbers. No
script, no external references; the styles are inline so the file stands on
its own.
"""
from html import escape

from planner.connections.layout import BOX_W, GROUP_HEAD, LINE_H, MARGIN, clip

STYLE = """
.wd-bg { fill: #ffffff; }
.wd-col { font: 600 12px system-ui, -apple-system, sans-serif; fill: #555; letter-spacing: .04em; text-transform: uppercase; }
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
.wd-end { fill: #2b4c7e; }
"""


def _e(value):
    return escape(str(value), quote=True)


def _n(value):
    return f'{value:.1f}'.rstrip('0').rstrip('.')


def _slots(box):
    out = []
    for i, label in enumerate(box.slots):
        if not label:
            continue
        y = box.row_y(i)
        out.append(f'<text class="p" data-slot="{_e(label)}" x="{_n(box.x + 8)}" y="{_n(y + 3.5)}">'
                   f'{_e(clip(label, BOX_W - 16))}</text>')
    return ''.join(out)


def _box(box):
    title = clip(box.label, BOX_W - 16)
    sub = clip(box.sub, BOX_W - 16)
    return (
        f'<g class="wd-box {_e(box.style)}" data-node="{_e(box.node)}" data-box="{_e(box.id)}">'
        f'<title>{_e(box.label)}</title>'
        f'<rect x="{_n(box.x)}" y="{_n(box.y)}" width="{_n(box.w)}" height="{_n(box.h)}" rx="4"/>'
        f'<text class="t" x="{_n(box.x + 8)}" y="{_n(box.y + 15)}">{_e(title)}</text>'
        f'<text class="s" x="{_n(box.x + 8)}" y="{_n(box.y + 28)}">{_e(sub)}</text>'
        + ''.join(f'<text class="s ln" x="{_n(box.x + 8)}" y="{_n(box.y + 28 + LINE_H * (i + 1))}">'
                  f'{_e(clip(line, BOX_W - 16))}</text>' for i, line in enumerate(box.lines)) +
        f'{_slots(box)}'
        '</g>')


def _route(route):
    path = ' '.join(f'{"M" if i == 0 else "L"}{_n(x)} {_n(y)}' for i, (x, y) in enumerate(route.points))
    end_x, end_y = route.points[-1]
    classes = ' '.join(route.classes)
    return (
        f'<g class="wd-link" data-edge="{_e(route.id)}">'
        f'<title>{_e(route.label_full)}</title>'
        f'<path class="wd-edge {_e(classes)}" d="{path}"/>'
        f'<path class="wd-end" d="M{_n(end_x)} {_n(end_y)} l-6 -3.5 v7 z"/>'
        f'<text class="wd-label {_e(classes)}" x="{_n(route.label_x)}" y="{_n(route.label_y)}">'
        f'{_e(route.label)}</text>'
        '</g>')


def render(lay, title=''):
    w, h = _n(lay.width), _n(lay.height)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" class="wd-svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" role="img" aria-label="{_e(title or "Wiring diagram")}">',
           f'<style>{STYLE}</style>',
           f'<rect class="wd-bg" width="{w}" height="{h}"/>']
    for text, x, _ in lay.columns:
        out.append(f'<text class="wd-col" x="{_n(x)}" y="{_n(MARGIN + 12)}">{_e(text)}</text>')
    for group in lay.groups:
        y = group.y + GROUP_HEAD - 8
        out.append(f'<text class="wd-group" x="{_n(group.x)}" y="{_n(y)}">{_e(group.label)}</text>'
                   f'<line class="wd-group-rule" x1="{_n(group.x)}" x2="{_n(group.x + BOX_W)}" '
                   f'y1="{_n(y + 4)}" y2="{_n(y + 4)}"/>')
    out += [_route(r) for r in lay.routes]
    out += [_box(b) for b in lay.boxes]
    out.append('</svg>')
    return ''.join(out)
