"""Label branding: colour rules, logo handling, layout with a brand, the
rendered PDF, and who may change a project's branding.

Every logo here is drawn on the spot with Pillow. The repo is public: no
client artwork, in tests or anywhere else.

Run with::

    python manage.py test planner.tests.test_label_branding \\
        --settings=audiopatch.test_settings
"""

import re
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image, ImageDraw

from planner.utils import image_upload
from planner.utils.image_upload import ImageRejected, normalize_logo
from planner.utils.labels import fonts, layout as L
from planner.utils.labels.brand import (
    BW_SEPARATION, DEFAULT, DEFAULT_BG_K, TEXT_THRESHOLD, Brand, BrandError, Logo,
    bw_accent_greys, contrast, k_for_hex, luminance, parse_accents, parse_hex, parse_style,
)
from planner.utils.labels.data import RunningUnit, SingleItem
from planner.utils.labels.render import (
    Options, corner_bars, corner_bars_zone, edge_stripe, generate_labels_pdf, paint_for,
    render_alignment_pdf, render_preview_pdf,
)
from planner.utils.labels.stock import STOCKS, Rect

OL = STOCKS['OL3016LP']
NAVY = '#08274F'
ACCENTS = ('#D9006C', '#F39200', '#0096D6')


# ---------------------------------------------------------------- placeholder logos

def image_bytes(w, h, fmt='PNG', alpha=True, margin=0, colours=((255, 255, 255),)):
    """A placeholder logo: coloured blocks side by side, with ``margin``
    pixels of empty border (transparent, or white when opaque)."""
    mode = 'RGBA' if alpha else 'RGB'
    empty = (0, 0, 0, 0) if alpha else (255, 255, 255)
    img = Image.new(mode, (w + 2 * margin, h + 2 * margin), empty)
    draw = ImageDraw.Draw(img)
    step = w / len(colours)
    for i, colour in enumerate(colours):
        fill = tuple(colour) + ((255,) if alpha else ())
        draw.rectangle((margin + i * step, margin, margin + (i + 1) * step - 1, margin + h - 1), fill=fill)
    out = BytesIO()
    img.save(out, format=fmt)
    return out.getvalue()


def logo(kind, w, h, **kw):
    content, _, width, height, _ = normalize_logo(image_bytes(w, h, **kw))
    return Logo(kind, content, width, height)


def overlaps(a, b):
    return a.x < b.right and b.x < a.right and a.y < b.top and b.y < a.top


def running_page(names, header=('Day 1',), compact=None, part=None, dividers=False, pack=2):
    rows = tuple(L.Row(n, divider=dividers and i > 0) for i, n in enumerate(names))
    return L.RunningPage(pack, header, rows, part, compact)


SINGLE = SingleItem(pack=1, day_label='Day 1', name='Sarah McMillan', time='9:00a',
                    session='Session 1 +2')


# ---------------------------------------------------------------- validation

class ValidationTests(SimpleTestCase):

    def test_hex(self):
        self.assertEqual(parse_hex('08274f'), '#08274F')
        self.assertEqual(parse_hex(' #abcdef '), '#ABCDEF')
        for bad in ('#12345', 'red', '#GGGGGG', '', None, '#1234567', '#12 456'):
            with self.assertRaises(BrandError, msg=bad):
                parse_hex(bad)

    def test_accents(self):
        self.assertEqual(parse_accents(['#ff0000', '', ' ', '00ff00']), ['#FF0000', '#00FF00'])
        with self.assertRaises(BrandError):
            parse_accents(['#111111'] * 4)
        with self.assertRaises(BrandError):
            parse_accents(['#111111', 'blue'])

    def test_style(self):
        for style in ('none', 'corner_bars', 'edge_stripe'):
            self.assertEqual(parse_style(style), style)
        with self.assertRaises(BrandError):
            parse_style('watermark')

    def test_svg_and_other_formats_are_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
        gif = image_bytes(20, 10, fmt='GIF', alpha=False)
        webp = image_bytes(20, 10, fmt='WEBP')
        for data in (svg, gif, webp, b'just some text', b''):
            with self.assertRaises(ImageRejected, msg=data[:20]):
                normalize_logo(data)

    def test_truncated_png_is_refused(self):
        data = image_bytes(200, 100)
        with self.assertRaises(ImageRejected):
            normalize_logo(data[:len(data) // 2])

    def test_oversize_file_is_refused_before_decoding(self):
        data = image_bytes(20, 10) + b'\0' * image_upload.MAX_PHOTO_BYTES
        with self.assertRaises(ImageRejected) as caught:
            normalize_logo(data)
        self.assertIn('MB', str(caught.exception))

    def test_too_many_pixels_is_refused(self):
        with patch.object(image_upload, 'MAX_PHOTO_PIXELS', 100):
            with self.assertRaises(ImageRejected):
                normalize_logo(image_bytes(20, 10))

    def test_blank_logo_is_refused(self):
        empty = BytesIO()
        Image.new('RGBA', (30, 30), (0, 0, 0, 0)).save(empty, format='PNG')
        with self.assertRaises(ImageRejected):
            normalize_logo(empty.getvalue())

    def test_transparent_margins_are_trimmed_and_alpha_kept(self):
        content, content_type, w, h, _ = normalize_logo(image_bytes(300, 100, margin=50))
        self.assertEqual((content_type, w, h), ('image/png', 300, 100))
        with Image.open(BytesIO(content)) as img:
            self.assertEqual(img.mode, 'RGBA')

    def test_opaque_jpeg_is_trimmed_to_its_artwork(self):
        data = image_bytes(300, 100, fmt='JPEG', alpha=False, margin=40, colours=((8, 39, 79),))
        content, content_type, w, h, _ = normalize_logo(data)
        self.assertEqual(content_type, 'image/jpeg')
        self.assertLess(abs(w - 300), 6)
        self.assertLess(abs(h - 100), 6)

    def test_downscaled_to_1200(self):
        _, _, w, h, _ = normalize_logo(image_bytes(3000, 600))
        self.assertEqual((w, h), (1200, 240))

    def test_reencoded_not_stored_as_sent(self):
        data = image_bytes(300, 100) + b'trailing payload'
        content, *_ = normalize_logo(data)
        self.assertNotIn(b'trailing payload', content)


# ---------------------------------------------------------------- colour rules

class ContrastTests(SimpleTestCase):

    def test_threshold(self):
        self.assertAlmostEqual(TEXT_THRESHOLD, 0.1791, places=4)
        self.assertAlmostEqual(contrast(1.0, TEXT_THRESHOLD), contrast(0.0, TEXT_THRESHOLD), places=9)
        self.assertGreater(contrast(1.0, TEXT_THRESHOLD), 4.58)

    def test_light_mid_and_dark_backgrounds(self):
        cases = {
            '#FFFFFF': False, '#F2E8D5': False,      # light: black text
            '#767676': False, '#808080': False,      # mid, just over the threshold
            '#757575': True,                         # mid, just under it
            NAVY: True, '#000000': True,             # dark: white text
        }
        for bg, white in cases.items():
            self.assertEqual(Brand(bg=bg).text_white, white, bg)

    def test_contrast_always_clears_aa(self):
        for v in range(0, 256, 3):
            grey = '#{0:02X}{0:02X}{0:02X}'.format(v)
            self.assertGreaterEqual(Brand(bg=grey).text_contrast, 4.5, grey)
        for bg in (NAVY, '#D9006C', '#F39200', '#0096D6', '#00A799', '#FFCC00'):
            self.assertGreaterEqual(Brand(bg=bg).text_contrast, 4.5, bg)

    def test_black_and_white_keeps_the_text_decision(self):
        for v in range(0, 256, 5):
            brand = Brand(bg='#{0:02X}{0:02X}{0:02X}'.format(v))
            paint = paint_for(brand, color=False)
            self.assertEqual(paint.text.black == 0, brand.text_white, v)
            self.assertEqual(paint.bg.black, brand.bg_k / 100)

    def test_default_theme(self):
        self.assertTrue(DEFAULT.is_default)
        self.assertEqual(DEFAULT.bg_k, DEFAULT_BG_K)
        self.assertTrue(DEFAULT.text_white)
        for color in (True, False):
            paint = paint_for(DEFAULT, color)
            self.assertEqual((paint.bg.cyan, paint.bg.magenta, paint.bg.yellow, paint.bg.black),
                             (0, 0, 0, 0.85))

    def test_navy_greys_to_the_default(self):
        self.assertEqual(k_for_hex(NAVY), 85)
        self.assertLess(luminance(NAVY), TEXT_THRESHOLD)


class BlackAndWhiteAccentTests(SimpleTestCase):

    def assert_separated(self, bg_k, greys):
        values = (bg_k,) + tuple(greys)
        for i, a in enumerate(values):
            for b in values[i + 1:]:
                self.assertGreaterEqual(abs(a - b), BW_SEPARATION, values)

    def test_three_accents_always_separate(self):
        for bg_k in range(0, 101, 5):
            for accents in ((50, 50, 50), (bg_k, bg_k, bg_k), (10, 40, 70), (0, 100, 55)):
                greys, separated = bw_accent_greys(bg_k, accents)
                self.assertTrue(separated, (bg_k, accents))
                self.assert_separated(bg_k, greys)

    def test_already_separate_greys_are_left_alone(self):
        self.assertEqual(bw_accent_greys(85, (57, 34, 10)), ((57, 34, 10), True))

    def test_navy_with_three_accents(self):
        greys, separated = Brand(bg=NAVY, accents=ACCENTS).bw_accents()
        self.assertTrue(separated)
        self.assert_separated(85, greys)

    def test_reported_when_impossible(self):
        # Five accents and a mid background need six greys 20 K apart in
        # 0-100, which only 0, 20, ... 100 can do -- and 50 is not one.
        greys, separated = bw_accent_greys(50, (10, 20, 30, 70, 80))
        self.assertFalse(separated)
        self.assertEqual(greys, (10, 20, 30, 70, 80))


# ---------------------------------------------------------------- layout with a brand

class CapacityTests(SimpleTestCase):

    def capacities(self, brand):
        frame = brand.frame()
        g = L.geometry(OL, frame.footer)
        one = 0
        while L._rows_fit([L.Row('Ann Lee')] * (one + 1), g, L.RUNNING_NAME_FLOOR):
            one += 1
        return one, L.running_order_capacity(OL, frame)

    def test_capacity_with_each_accent_style(self):
        mark = logo('mark', 100, 100)
        wide = logo('on_dark', 250, 100)
        expected = {'none': (6, 5), 'edge_stripe': (6, 5), 'corner_bars': (5, 4)}
        for style, caps in expected.items():
            for logos in ((), (wide, mark)):
                brand = Brand(bg=NAVY, accents=ACCENTS, accent_style=style, logos=logos)
                self.assertEqual(self.capacities(brand), caps, (style, bool(logos)))
                self.assertTrue(L.running_order_available(OL, brand.frame())[0])

    def test_accent_style_without_accents_is_none(self):
        brand = Brand(bg=NAVY, accent_style='corner_bars')
        self.assertEqual(brand.style, 'none')
        self.assertEqual(brand.frame().footer, 0)

    def test_pagination_follows_the_brand(self):
        unit = RunningUnit(pack=1, header=('Day 1',), groups=(('Ann Lee',) * 6,))
        plain = Brand(bg=NAVY)
        bars = Brand(bg=NAVY, accents=ACCENTS, accent_style='corner_bars')
        self.assertEqual(len(L.paginate_running(unit, OL, plain.frame())), 1)
        self.assertEqual(len(L.paginate_running(unit, OL, bars.frame())), 2)


class LogoLayoutTests(SimpleTestCase):

    def header_runs(self, layout):
        return [r for r in layout.runs if r.role == 'header']

    def left_edge_right(self, layout):
        """Right edge of the RF column and number."""
        g = layout.geometry
        lefts = [r for r in self.header_runs(layout)
                 if r.text == 'RF' or re.fullmatch(r'\d+/\d+', r.text) or r.size == g.number]
        return max(r.x + r.width for r in lefts)

    def right_block_left(self, layout):
        g = layout.geometry
        xs = [r.x for r in self.header_runs(layout)
              if not (r.text == 'RF' or re.fullmatch(r'\d+/\d+', r.text) or r.size == g.number)]
        if layout.logo:
            xs.append(layout.logo[1].x)
        return min(xs)

    def test_fallback_chain_full_mark_none(self):
        page = running_page(['Ann Lee'])
        cases = (
            ((('on_dark', 2.5), ('mark', 1.0)), 'on_dark'),
            ((('on_dark', 6.0), ('mark', 1.0)), 'mark'),
            ((('on_dark', 6.0),), None),
            ((('mark', 6.0),), None),
        )
        for logos, expected in cases:
            layout = L.layout_running(page, OL, L.Frame(logos=logos))
            self.assertEqual(layout.logo[0] if layout.logo else None, expected, logos)

    def test_logo_is_8mm_top_right_inside_the_safe_zone(self):
        layout = L.layout_single(SINGLE, OL, L.Frame(logos=(('on_dark', 2.5),)))
        g = layout.geometry
        _, rect = layout.logo
        self.assertAlmostEqual(rect.h, L.LOGO_HEIGHT, places=9)
        self.assertAlmostEqual(rect.h, 8 * 72 / 25.4, places=9)
        self.assertAlmostEqual(rect.right, g.safe.right, places=9)
        self.assertAlmostEqual(rect.top, g.safe.top, places=9)
        self.assertTrue(g.safe.contains(rect, 1e-6))
        for run in layout.runs:
            self.assertFalse(overlaps(run.bbox, rect), run.text)

    def test_never_shrunk_below_8mm(self):
        # Just too wide: no logo at all, not a smaller one.
        widest = L.max_logo_aspect(OL)
        layout = L.layout_single(SINGLE, OL, L.Frame(logos=(('on_dark', widest + 0.01),)))
        self.assertIsNone(layout.logo)
        layout = L.layout_single(SINGLE, OL, L.Frame(logos=(('on_dark', widest - 0.01),)))
        self.assertIsNotNone(layout.logo)

    def test_max_aspect(self):
        self.assertAlmostEqual(L.max_logo_aspect(OL), 3.05, places=2)
        self.assertAlmostEqual(L.max_logo_aspect(OL, part=True), 2.91, places=2)

    def test_day_and_time_without_ellipsis_when_only_the_session_is_dropped(self):
        page = running_page(['Ann Lee'], header=('Day 1', '9:00a', 'General Session'),
                            compact=('Day 1', '9:00a'))
        layout = L.layout_running(page, OL, L.Frame(logos=(('on_dark', 2.5),)))
        texts = [r.text for r in self.header_runs(layout)]
        self.assertIn('Day 1 · 9:00a', texts)
        self.assertFalse(any(L.ELLIPSIS in t for t in texts), texts)
        self.assertFalse(any('General' in t for t in texts), texts)

    def test_without_a_logo_the_header_is_unchanged(self):
        page = running_page(['Ann Lee'], header=('Day 1', '9:00a', 'Keynote'),
                            compact=('Day 1', '9:00a'))
        texts = [r.text for r in self.header_runs(L.layout_running(page, OL))]
        self.assertEqual(texts[-3:], ['Day 1', '9:00a', 'Keynote'])

    def test_long_day_with_a_part_marker_keeps_the_gap(self):
        frame = L.Frame(logos=(('on_dark', 1.0),))
        cases = (
            # day . time too wide, the day alone fits: the day, no ellipsis
            (('Wed Nov 25', '10:30a'), 'Wed Nov 25'),
            # even the day is too wide: the day cut short, with an ellipsis
            (('Wednesday Breakout Track Day', '10:30a'), None),
        )
        for compact, expected in cases:
            page = running_page(['Ann Lee'], header=compact + ('Breakouts',), compact=compact,
                                part=(1, 2))
            layout = L.layout_running(page, OL, frame)
            self.assertIsNotNone(layout.logo)
            day = [r for r in self.header_runs(layout) if r.y < layout.logo[1].y
                   and r.x > self.left_edge_right(layout)][0]
            if expected:
                self.assertEqual(day.text, expected)
            else:
                self.assertTrue(day.text.endswith(L.ELLIPSIS), day.text)
                self.assertTrue(day.text.startswith('Wednesday'))
            self.assertGreaterEqual(self.right_block_left(layout) - self.left_edge_right(layout), 4)
            self.assertTrue(layout.geometry.safe.contains(day.bbox, 1e-6))
            self.assertFalse(overlaps(day.bbox, layout.logo[1]))

    def test_gap_without_a_logo_too(self):
        page = running_page(['Ann Lee'], header=('Wednesday Breakout Track Day',), part=(1, 2))
        layout = L.layout_running(page, OL)
        self.assertGreaterEqual(self.right_block_left(layout) - self.left_edge_right(layout), 4)

    def test_single_name_meta_is_centred_under_the_name(self):
        layout = L.layout_single(SINGLE, OL)
        box = layout.geometry.text
        meta = [r for r in layout.runs if r.role == 'meta']
        self.assertEqual([r.text for r in meta], ['9:00a', 'Session 1 +2'])
        for run in meta:
            self.assertAlmostEqual(run.x + run.width / 2, box.x + box.w / 2, places=6)


class AccentClearanceTests(SimpleTestCase):

    NAMES = ['Ann Lee', 'WILLIAM M. MORROW', 'Bartholomew Featherstonehaugh-Smythe',
             'Nguyễn Đặng', 'Zoë Müller-Łukasz']

    def layouts(self, brand):
        frame = brand.frame()
        cap = L.running_order_capacity(OL, frame)
        for count in range(1, cap + 2):
            for dividers in (False, True):
                names = (self.NAMES * 3)[:count]
                unit = RunningUnit(pack=7, header=('Day 1', '9:00a', 'Keynote'),
                                   groups=tuple((n,) for n in names) if dividers else (tuple(names),),
                                   compact=('Day 1', '9:00a'))
                for page in L.paginate_running(unit, OL, frame):
                    yield L.layout_running(page, OL, frame)
        for name in self.NAMES:
            item = SingleItem(pack=12, day_label='Thursday Nov 26', name=name, time='10:30a',
                              session='General Session +2')
            yield L.layout_single(item, OL, frame)

    def test_corner_bars_never_under_text_or_logo(self):
        brand = Brand(bg=NAVY, accents=ACCENTS, accent_style='corner_bars',
                      logos=(logo('on_dark', 250, 100), logo('mark', 100, 100)))
        n = 0
        for layout in self.layouts(brand):
            g = layout.geometry
            zone = corner_bars_zone(g)
            boxes = [r.bbox for r in layout.runs] + ([layout.logo[1]] if layout.logo else [])
            for box in boxes:
                self.assertFalse(overlaps(box, zone), box)
                self.assertTrue(g.safe.contains(box, 1e-6), box)
            for bar in corner_bars(g, 3):
                xs, ys = [p[0] for p in bar], [p[1] for p in bar]
                self.assertTrue(zone.contains(Rect(min(xs), min(ys), max(xs) - min(xs),
                                                   max(ys) - min(ys)), 1e-6))
            n += 1
        self.assertGreater(n, 10)

    def test_edge_stripe_stays_outside_the_safe_zone(self):
        brand = Brand(bg=NAVY, accents=ACCENTS, accent_style='edge_stripe')
        for layout in self.layouts(brand):
            g = layout.geometry
            for x, y, w, h in edge_stripe(g, 3):
                self.assertLessEqual(y + h, g.safe.y + 1e-6)
                for run in layout.runs:
                    self.assertFalse(overlaps(run.bbox, Rect(x, y, w, h)))


# ---------------------------------------------------------------- PDFs

def page_streams(pdf):
    from PyPDF2 import PdfReader
    reader = PdfReader(BytesIO(pdf))
    for page in reader.pages:
        yield page, page.get_contents().get_data().decode('latin-1')


def images(page):
    xobjects = page['/Resources'].get('/XObject') or {}
    return [x.get_object() for x in xobjects.values()
            if x.get_object().get('/Subtype') == '/Image']


class RenderTests(SimpleTestCase):

    def data(self):
        from planner.utils.labels.data import ScopeData, SessionInfo
        s = SessionInfo(id=1, day_id=1, day_label='Day 1', index=0, name='Keynote', time='9:00a')
        return ScopeData(sessions=[s], packs={rf: {1: [(rf, 'Name {}'.format(rf))]} for rf in range(1, 13)})

    def test_unbranded_output_is_the_default_theme(self):
        pdf, count = generate_labels_pdf(self.data(), 'single', OL, Options())
        self.assertEqual(count, 12)
        for page, stream in page_streams(pdf):
            self.assertIn('0 0 0 .85 k', stream)
            self.assertNotRegex(stream, r'\brg\b|\bRG\b')    # no RGB anywhere: K only
            self.assertEqual(images(page), [])

    def test_black_and_white_is_black_toner_only(self):
        brand = Brand(bg=NAVY, accents=ACCENTS, accent_style='corner_bars',
                      logos=(logo('on_dark', 250, 100, colours=((0, 150, 214), (255, 255, 255))),))
        pdf, _ = generate_labels_pdf(self.data(), 'single', OL, Options(color=False, brand=brand))
        for page, stream in page_streams(pdf):
            self.assertNotRegex(stream, r'\brg\b|\bRG\b')
            found = images(page)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]['/ColorSpace'], '/DeviceGray')

    def test_colour_logo_is_embedded_once_for_a_whole_sheet(self):
        brand = Brand(bg=NAVY, logos=(logo('on_dark', 250, 100),))
        pdf, count = generate_labels_pdf(self.data(), 'single', OL, Options(brand=brand))
        self.assertEqual(count, 12)
        (page, stream), = page_streams(pdf)
        self.assertEqual(len(images(page)), 1)
        self.assertEqual(stream.count(' Do'), 12)

    def test_light_background_uses_the_on_light_logo(self):
        dark, light = logo('on_dark', 250, 100), logo('on_light', 200, 100, colours=((0, 0, 0),))
        brand = Brand(bg='#F2E8D5', logos=(dark, light))
        self.assertEqual([lg.kind for lg in brand.logo_candidates()], ['on_light'])
        self.assertEqual(Brand(bg=NAVY, logos=(dark, light)).logo_candidates(), (dark,))

    def test_preview_and_alignment_render(self):
        brand = Brand(bg=NAVY, accents=ACCENTS, accent_style='corner_bars')
        self.assertTrue(render_preview_pdf(brand, OL).startswith(b'%PDF'))
        pdf = render_alignment_pdf(OL, Options(brand=brand))
        (_, stream), = page_streams(pdf)
        # The background swatch, in RGB, and its K85 grey beside it.
        self.assertIn('.031373 .152941 .309804 rg', stream)
        self.assertIn('0 0 0 .85 k', stream)


# ---------------------------------------------------------------- views

class BrandingViewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        from planner.models import Project, ProjectMember, UserProfile

        def user(name, plan='paid'):
            u = User.objects.create_user(name, f'{name}@example.com', 'pw', is_staff=True)
            UserProfile.objects.update_or_create(user=u, defaults={'account_type': plan})
            return u

        cls.owner = user('owner')
        cls.project = Project.objects.create(name='Main Show', owner=cls.owner)
        cls.editor, cls.viewer, cls.stranger = user('editor'), user('viewer'), user('stranger')
        ProjectMember.objects.create(user=cls.editor, project=cls.project, role='editor', invited_by=cls.owner)
        ProjectMember.objects.create(user=cls.viewer, project=cls.project, role='viewer', invited_by=cls.owner)
        cls.theirs = Project.objects.create(name='Theirs', owner=cls.stranger)

    def login(self, user, project=None):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = (project or self.project).pk
        session.save()

    def save(self, **fields):
        data = {'bg_color': NAVY, 'accent': list(ACCENTS), 'accent_style': 'corner_bars'}
        data.update(fields)
        return self.client.post(reverse('planner:branding_save'), data)

    def upload(self, kind='on_dark', data=None, name='logo.png'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile(name, data or image_bytes(250, 100), content_type='image/png')
        return self.client.post(reverse('planner:branding_logo_upload'), {'kind': kind, 'logo': f})

    def branding(self):
        self.project.refresh_from_db()
        return (self.project.brand_bg_color, self.project.brand_accent_colors,
                self.project.brand_accent_style, self.project.logos.count())

    def test_owner_and_editor_can_edit(self):
        for user in (self.owner, self.editor):
            self.login(user)
            self.assertEqual(self.save().status_code, 302)
            self.assertEqual(self.upload().status_code, 302)
            self.assertEqual(self.branding(), (NAVY, list(ACCENTS), 'corner_bars', 1))
            r = self.client.post(reverse('planner:branding_logo_delete'), {'kind': 'on_dark'})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(self.project.logos.count(), 0)
            self.save(bg_color='', accent=[], accent_style='none')

    def test_viewer_cannot_edit(self):
        from planner.models import ProjectLogo
        ProjectLogo.store(self.project, 'mark', image_bytes(100, 100))
        before = self.branding()
        self.login(self.viewer)
        self.assertEqual(self.save().status_code, 403)
        self.assertEqual(self.upload().status_code, 403)
        r = self.client.post(reverse('planner:branding_logo_delete'), {'kind': 'mark'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.branding(), before)
        # The page itself is read-only for them: no forms that post.
        r = self.client.get(reverse('planner:project_branding'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context['can_edit'])
        self.assertNotContains(r, reverse('planner:branding_save'))
        self.assertNotContains(r, reverse('planner:branding_logo_upload'))

    def test_non_member_cannot_edit_or_see(self):
        from planner.models import ProjectLogo
        ProjectLogo.store(self.project, 'mark', image_bytes(100, 100))
        before = self.branding()
        self.login(self.stranger)                  # session names our project
        self.save()
        self.upload()
        self.client.post(reverse('planner:branding_logo_delete'), {'kind': 'mark'})
        self.assertEqual(self.branding(), before)
        r = self.client.get(reverse('planner:branding_logo') + '?kind=mark')
        self.assertEqual(r.status_code, 404)

    def test_bad_values_are_refused_with_a_message(self):
        self.login(self.owner)
        for fields in ({'bg_color': 'navy'}, {'accent': ['#111111'] * 4},
                       {'accent': ['#12345']}, {'accent_style': 'watermark'}):
            r = self.save(**fields)
            self.assertEqual(r.status_code, 302)
            self.assertEqual(self.branding(), ('', [], 'none', 0), fields)
        r = self.client.get(reverse('planner:project_branding'))
        self.assertContains(r, 'is not a colour')

    def test_bad_uploads_are_refused(self):
        self.login(self.owner)
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        for data, name in ((svg, 'logo.svg'), (b'hello', 'logo.png'),
                           (image_bytes(20, 10, fmt='WEBP'), 'logo.webp')):
            self.upload(data=data, name=name)
        self.assertEqual(self.project.logos.count(), 0)
        self.upload(kind='watermark')
        self.assertEqual(self.project.logos.count(), 0)

    def test_logo_is_served_to_members(self):
        self.login(self.owner)
        self.upload()
        self.login(self.viewer)
        r = self.client.get(reverse('planner:branding_logo') + '?kind=on_dark')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/png')
        self.assertEqual(self.client.get(reverse('planner:branding_logo') + '?kind=mark').status_code, 404)

    def test_preview_follows_unsaved_values(self):
        self.login(self.viewer)
        url = reverse('planner:branding_preview_pdf')
        r = self.client.get(url + '?bg=%23F2E8D5&accent=%23D9006C&accent_style=edge_stripe&accents=1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        (_, stream), = page_streams(r.content)
        self.assertIn('.94902 .909804 .835294 rg', stream)     # #F2E8D5
        r = self.client.get(url + '?bg=nonsense')               # ignored, not an error
        self.assertEqual(r.status_code, 200)

    def test_suggest_accents_from_the_logo(self):
        self.login(self.owner)
        r = self.client.get(reverse('planner:branding_suggest_accents'))
        self.assertEqual(r.json()['accents'], [])
        self.upload(kind='on_light', data=image_bytes(
            300, 100, colours=((220, 20, 60), (220, 20, 60), (0, 90, 200), (0, 0, 0), (255, 255, 255))))
        body = self.client.get(reverse('planner:branding_suggest_accents') + '?bg=%23FFFFFF').json()
        self.assertEqual(body['source'], 'on_light')
        self.assertEqual(len(body['accents']), 2)
        red, blue = (tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in body['accents'])
        self.assertGreater(red[0], 180)
        self.assertGreater(blue[2], 160)
        # Suggesting saves nothing.
        self.assertEqual(self.branding()[1], [])

    def test_print_page_status_line(self):
        self.login(self.editor)
        r = self.client.get(reverse('planner:mic_tracker_print'))
        self.assertContains(r, 'none (default dark)')
        self.assertContains(r, reverse('planner:project_branding'))
        # The default theme is black toner already: B&W would save nothing.
        self.assertNotContains(r, 'Heavy colour coverage')
        self.save(accent=[], accent_style='none')
        r = self.client.get(reverse('planner:mic_tracker_print'))
        self.assertContains(r, NAVY)
        self.assertContains(r, 'Heavy colour coverage')
        self.save(bg_color='#FFFFFF', accent=[], accent_style='none')
        r = self.client.get(reverse('planner:mic_tracker_print'))
        self.assertContains(r, '#FFFFFF')
        self.assertNotContains(r, 'Heavy colour coverage')
        self.login(self.viewer)
        r = self.client.get(reverse('planner:mic_tracker_print'))
        self.assertNotContains(r, reverse('planner:project_branding'))

    def test_page_warns_about_wide_low_res_and_low_contrast_logos(self):
        self.login(self.owner)
        self.save(accent=[], accent_style='none')
        self.upload(kind='on_dark', data=image_bytes(600, 100))                  # 6:1
        self.upload(kind='mark', data=image_bytes(40, 40, colours=((10, 40, 80),)))  # dark, 40 px
        r = self.client.get(reverse('planner:project_branding'))
        notes = {logo['kind']: ' '.join(t for _, t in logo['notes']) for logo in r.context['logos']}
        self.assertIn('the mark prints instead', notes['on_dark'])
        self.assertIn('dpi', notes['mark'])
        self.assertIn('Low contrast', notes['mark'])

    def test_project_page_links_through_set_project(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('project_detail', args=[self.project.pk]))
        link = reverse('set_project', args=[self.project.pk]) + '?next=' + reverse('planner:project_branding')
        self.assertContains(r, link)
        r = self.client.get(link)
        self.assertRedirects(r, reverse('planner:project_branding'), fetch_redirect_response=False)
        url = reverse('set_project', args=[self.project.pk])
        for target in ('https://evil.com', '//evil.com', '/\\evil.com', 'javascript:alert(1)',
                       'http://showstack.io.evil.com', 'http://testserver.evil.com/'):
            r = self.client.get(url, {'next': target})
            self.assertEqual(r['Location'], '/admin/', target)
        for target in (reverse('planner:mic_tracker_print'), '/audiopatch/mic-tracker/?session=3'):
            r = self.client.get(url, {'next': target})
            self.assertEqual(r['Location'], target)

    def test_duplicate_copies_branding(self):
        from planner.models import ProjectLogo
        self.project.brand_bg_color = NAVY
        self.project.brand_accent_colors = list(ACCENTS)
        self.project.brand_accent_style = 'edge_stripe'
        self.project.save()
        ProjectLogo.store(self.project, 'mark', image_bytes(100, 100))
        copy = self.project.duplicate()
        self.assertEqual((copy.brand_bg_color, copy.brand_accent_colors, copy.brand_accent_style),
                         (NAVY, list(ACCENTS), 'edge_stripe'))
        self.assertEqual(list(copy.logos.values_list('kind', flat=True)), ['mark'])
        self.assertEqual(self.project.logos.count(), 1)

    def test_label_pdf_carries_the_brand(self):
        import datetime
        from planner.models import MicAssignment, MicSession, Presenter, PresenterSlot, ShowDay
        day = ShowDay.objects.create(project=self.project, date=datetime.date(2026, 11, 3))
        session = MicSession.objects.create(day=day, name='Keynote', num_mics=6, order=0)
        for rf in range(1, 7):
            a = MicAssignment.objects.get(session=session, rf_number=rf)
            PresenterSlot.objects.create(assignment=a, order=0, presenter=Presenter.objects.create(
                project=self.project, name='Person {}'.format(rf)))
        self.login(self.owner)
        self.save()
        r = self.client.get(reverse('planner:mic_labels_pdf') + f'?sessions={session.pk}&mode=single')
        (_, stream), = page_streams(r.content)
        self.assertIn('.031373 .152941 .309804 rg', stream)
        r = self.client.get(reverse('planner:mic_labels_pdf') + f'?sessions={session.pk}&mode=single&color=0')
        (_, stream), = page_streams(r.content)
        self.assertNotRegex(stream, r'\brg\b')
