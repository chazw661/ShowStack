"""Beltpack labels: sheet geometry, grouping, layout, fonts, and who may print.

Most of this runs on plain data -- the stock, ScopeData built by hand, and
the pure layout functions -- so the rules are pinned without fixtures. The
database is only used for scope_data() and the views.

Run with::

    python manage.py test planner.tests.test_beltpack_labels \\
        --settings=audiopatch.test_settings
"""

import datetime
import unicodedata
from fractions import Fraction
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from planner.utils.labels import fonts, layout as L
from planner.utils.labels.data import (
    ScopeData, SessionInfo, format_time, natural_key, pack_entries,
    running_units, single_name_items,
)
from planner.utils.labels.render import (
    Options, build_layouts, generate_labels_pdf, render_alignment_pdf,
)
from planner.utils.labels.stock import (
    POINTS_PER_MM, STOCKS, LabelStock, Rect, clamp_offset, clamp_start, inches,
    sheet_positions, sheets_needed,
)

OL = STOCKS['OL3016LP']
TOL_PT = float(Fraction(1, 100) * POINTS_PER_MM)    # 0.01 mm


def small_stock():
    """A hypothetical 1" square stock: too small for a running order."""
    return LabelStock(
        part='TEST-1IN', description='test', page_w=inches('8.5'), page_h=inches(11),
        label_w=inches(1), label_h=inches(1), corner_r=inches('0.0625'),
        margin_left=inches('0.25'), margin_top=inches('0.25'),
        pitch_x=inches('1.25'), pitch_y=inches('1.25'), cols=6, rows=8,
    )


def big_stock():
    return LabelStock(
        part='TEST-3IN', description='test', page_w=inches('8.5'), page_h=inches(11),
        label_w=inches(3), label_h=inches(3), corner_r=inches('0.125'),
        margin_left=inches('0.25'), margin_top=inches('0.25'),
        pitch_x=inches('4'), pitch_y=inches('3.5'), cols=2, rows=3,
    )


# ---------------------------------------------------------------- geometry

class StockGeometryTests(SimpleTestCase):

    def test_columns_add_up_to_the_page_width(self):
        total = OL.margin_left + 2 * OL.pitch_x + OL.label_w + OL.margin_right
        self.assertEqual(total, inches('8.5'))
        self.assertAlmostEqual(float(OL.margin_right), 18.0, delta=TOL_PT)

    def test_rows_add_up_to_the_page_height(self):
        total = OL.margin_top + 3 * OL.pitch_y + OL.label_h + OL.margin_bottom
        self.assertEqual(total, inches(11))
        self.assertAlmostEqual(float(OL.margin_bottom), 18.0, delta=TOL_PT)

    def test_pitches_are_exact(self):
        self.assertEqual(OL.pitch_y, Fraction(204))          # 17/6" exactly
        self.assertEqual(OL.pitch_x, Fraction(216))
        self.assertEqual(OL.count, 12)

    def test_every_label_is_inside_the_page(self):
        page = Rect(0, 0, OL.page_w, OL.page_h)
        for position in range(1, 13):
            self.assertTrue(page.contains(OL.label_rect(position)), position)

    def test_positions_count_across_then_down(self):
        first, third, last = OL.label_rect(1), OL.label_rect(3), OL.label_rect(12)
        self.assertEqual((first.x, first.top), (inches('0.25'), inches('10.75')))
        self.assertEqual(third.right, inches('8.25'))
        self.assertEqual((last.right, last.y), (inches('8.25'), inches('0.25')))

    def test_offsets_shift_right_and_down(self):
        base, moved = OL.label_rect(1), OL.label_rect(1, 2, 2)
        self.assertAlmostEqual(float(moved.x - base.x), 2 * 72 / 25.4, delta=TOL_PT)
        self.assertAlmostEqual(float(base.y - moved.y), 2 * 72 / 25.4, delta=TOL_PT)

    def test_clamp(self):
        self.assertEqual(clamp_offset('7'), 5.0)
        self.assertEqual(clamp_offset(-7), -5.0)
        self.assertEqual(clamp_offset('1.26'), 1.3)
        for junk in ('nan', 'inf', '-inf', 'abc', None, ''):
            self.assertEqual(clamp_offset(junk), 0.0, junk)
        self.assertEqual(clamp_start('0', OL), 1)
        self.assertEqual(clamp_start('13', OL), 12)
        self.assertEqual(clamp_start('x', OL), 1)

    def test_start_position_fills_a_part_used_sheet_first(self):
        positions = sheet_positions(OL, 10, start=5)
        self.assertEqual(positions[0], (0, 5))
        self.assertEqual(positions[7], (0, 12))
        self.assertEqual(positions[8], (1, 1))
        self.assertEqual(sheets_needed(OL, 10, 5), 2)
        self.assertEqual(sheets_needed(OL, 8, 5), 1)
        self.assertEqual(sheets_needed(OL, 0, 5), 0)


# ---------------------------------------------------------------- grouping

DAY1, DAY2 = 'Tue Nov 3', 'Wed Nov 4'


def S(sid, index, name, time, day=1, label=DAY1):
    return SessionInfo(id=sid, day_id=day, day_label=label, index=index, name=name, time=time)


KEYNOTE, PANEL, BREAKOUT = S(1, 0, 'Keynote', '9:00a'), S(2, 1, 'Panel', '10:30a'), S(3, 2, 'Breakout', '1:15p')
OPENING = S(4, 0, 'Opening', '8:30a', day=2, label=DAY2)
ALL = [KEYNOTE, PANEL, BREAKOUT, OPENING]


def data(packs, sessions=ALL, skipped=0):
    return ScopeData(sessions=list(sessions), packs=packs, skipped=skipped)


ZOE, BOB, ANN = (1, 'Zoë'), (2, 'Bob'), (3, 'Ann')


class GroupingTests(SimpleTestCase):

    def test_natural_sort(self):
        self.assertEqual(sorted(['10', '2', '1'], key=natural_key), ['1', '2', '10'])
        self.assertEqual(sorted(['RF10', 'RF2'], key=natural_key), ['RF2', 'RF10'])
        d = data({10: {1: [ZOE]}, 2: {1: [BOB]}, 1: {1: [ANN]}})
        self.assertEqual([i.pack for i in single_name_items(d)], [1, 2, 10])

    def test_format_time(self):
        self.assertEqual(format_time(datetime.time(9, 0)), '9:00a')
        self.assertEqual(format_time(datetime.time(12, 45)), '12:45p')
        self.assertEqual(format_time(datetime.time(0, 5)), '12:05a')
        self.assertEqual(format_time(None), '')

    def test_single_name_keeps_a_packs_labels_together_in_slot_order(self):
        d = data({4: {1: [ZOE, BOB], 2: [ANN]}, 2: {1: [(9, 'Cy')]}})
        items = single_name_items(d)
        self.assertEqual([(i.pack, i.name) for i in items],
                         [(2, 'Cy'), (4, 'Zoë'), (4, 'Bob'), (4, 'Ann')])
        self.assertEqual((items[1].time, items[1].session), ('9:00a', 'Keynote'))
        self.assertEqual(items[3].session, 'Panel')

    # -- merge, single name
    def test_single_name_merges_consecutive_sessions(self):
        d = data({4: {1: [ZOE], 2: [ZOE], 3: [ZOE]}})
        items = single_name_items(d)
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0].time, items[0].session), ('9:00a', 'Keynote +2'))

    def test_single_name_merge_broken_by_a_different_presenter(self):
        d = data({4: {1: [ZOE], 2: [BOB], 3: [ZOE]}})
        self.assertEqual([i.name for i in single_name_items(d)], ['Zoë', 'Bob', 'Zoë'])

    def test_single_name_merge_broken_by_no_presenter_or_no_rf_row(self):
        # Session 2 has nothing on pack 4 (an empty slot or no RF row at all
        # reach the grouping the same way: no presenter for the pack there).
        d = data({4: {1: [ZOE], 3: [ZOE]}})
        self.assertEqual([i.session for i in single_name_items(d)], ['Keynote', 'Breakout'])

    def test_single_name_merge_never_crosses_a_day(self):
        d = data({4: {3: [ZOE], 4: [ZOE]}})
        items = single_name_items(d)
        self.assertEqual([(i.day_label, i.session) for i in items],
                         [(DAY1, 'Breakout'), (DAY2, 'Opening')])

    def test_merge_needs_the_presenter_last_in_one_session_and_first_in_the_next(self):
        d = data({4: {1: [ZOE, BOB], 2: [ZOE]}})
        self.assertEqual(len(single_name_items(d)), 3)
        d = data({4: {1: [BOB, ZOE], 2: [ZOE, ANN]}})
        self.assertEqual([(i.name, i.session) for i in single_name_items(d)],
                         [('Bob', 'Keynote'), ('Zoë', 'Keynote +1'), ('Ann', 'Panel')])

    # -- running order
    def test_one_selected_session_is_in_the_header_and_has_no_separators(self):
        d = data({4: {1: [ZOE, BOB]}}, sessions=[KEYNOTE])
        (unit,) = running_units(d)
        self.assertEqual(unit.header, (DAY1, '9:00a', 'Keynote'))
        self.assertEqual(unit.groups, ((None, (('Zoë', ''), ('Bob', ''))),))

    def test_separators_only_for_multi_session_labels(self):
        d = data({4: {1: [ZOE], 2: [BOB]}, 5: {2: [ANN]}})
        units = {u.pack: u for u in running_units(d)}
        self.assertEqual(units[4].groups, (('9:00a · Keynote', (('Zoë', ''),)),
                                           ('10:30a · Panel', (('Bob', ''),))))
        self.assertEqual(units[5].groups, ((None, (('Ann', ''),)),))
        self.assertEqual(units[5].header, (DAY1,))

    def test_one_unit_per_pack_per_day_and_the_header_is_counted_per_day(self):
        # Three sessions selected on day 1: the day alone. One on day 2: the
        # day, its time and its name.
        d = data({4: {1: [ZOE], 4: [BOB]}})
        units = running_units(d)
        self.assertEqual([(u.pack, u.header) for u in units],
                         [(4, (DAY1,)), (4, (DAY2, '8:30a', 'Opening'))])

    def test_session_without_start_time_separator_is_just_its_name(self):
        untimed = S(2, 1, 'Panel', '')
        d = data({4: {1: [ZOE], 2: [BOB]}}, sessions=[KEYNOTE, untimed])
        (unit,) = running_units(d)
        self.assertEqual(unit.groups[1][0], 'Panel')

    # -- merge, running order (mirrors the single-name tests)
    def test_running_merges_consecutive_sessions(self):
        d = data({4: {1: [ZOE], 2: [ZOE], 3: [ZOE]}})
        (unit,) = running_units(d)
        self.assertEqual(unit.groups, (('9:00a · Keynote', (('Zoë', 'S1–3'),)),))

    def test_running_merge_broken_by_a_different_presenter(self):
        d = data({4: {1: [ZOE], 2: [BOB], 3: [ZOE]}})
        (unit,) = running_units(d)
        self.assertEqual(unit.groups, (('9:00a · Keynote', (('Zoë', ''),)),
                                       ('10:30a · Panel', (('Bob', ''),)),
                                       ('1:15p · Breakout', (('Zoë', ''),))))

    def test_running_merge_broken_by_no_presenter_or_no_rf_row(self):
        d = data({4: {1: [ZOE], 3: [ZOE]}})
        (unit,) = running_units(d)
        self.assertEqual([g[0] for g in unit.groups], ['9:00a · Keynote', '1:15p · Breakout'])

    def test_running_merge_never_crosses_a_day(self):
        d = data({4: {3: [ZOE], 4: [ZOE]}})
        units = running_units(d)
        self.assertEqual([u.groups for u in units], [((None, (('Zoë', ''),)),)] * 2)

    def test_an_unselected_session_in_between_breaks_the_merge(self):
        # Keynote and Breakout selected, Panel (index 1) between them not.
        d = data({4: {1: [ZOE], 3: [ZOE]}}, sessions=[KEYNOTE, BREAKOUT])
        self.assertEqual([i.session for i in single_name_items(d)], ['Keynote', 'Breakout'])
        (unit,) = running_units(d)
        self.assertEqual([g[0] for g in unit.groups], ['9:00a · Keynote', '1:15p · Breakout'])

    def test_session_span(self):
        from planner.utils.labels.data import session_span
        self.assertEqual(session_span([KEYNOTE, PANEL, BREAKOUT]), 'S1–3')
        self.assertEqual(session_span([PANEL, BREAKOUT]), 'S2–3')
        self.assertEqual(session_span([KEYNOTE, BREAKOUT]), 'S1, S3')

    def test_pack_entries_record_the_run(self):
        d = data({4: {1: [ZOE], 2: [ZOE]}})
        (entry,) = pack_entries(d, 4)
        self.assertEqual((entry.first.id, entry.extra), (1, 1))


# ---------------------------------------------------------------- layout

FIXTURE_17 = [  # mixed-case names of 17 characters or fewer
    'Zoë Müller-Łukasz', 'Dr. Maxwell Owens', 'Christopher Brown', 'Sir Wm. Wadsworth',
    'Jacqueline Mwangi', 'Nguyễn Đặng Thu',
]
WORST = [
    'W' * 40, 'Alexandra Konstantinopoulou-Whitmore the Third', 'Supercalifragilisticexpialidocious',
    'WILLIAM M. MORROW', 'Nguyễn Đặng', 'Ễ Ỗ Ặ Ữ', 'Al', 'Zoë Müller-Łukasz',
]


def running_pages(names, stock=OL, sessions=(KEYNOTE,)):
    packs = {4: {}}
    for i, name in enumerate(names):
        session = sessions[i % len(sessions)]
        packs[4].setdefault(session.id, []).append((100 + i, name))
    pages = []
    for unit in running_units(data(packs, sessions=sessions)):
        pages.extend(L.paginate_running(unit, stock))
    return pages


class LayoutTests(SimpleTestCase):

    def assert_contained(self, layout):
        g = layout.geometry
        for run in layout.runs:
            self.assertTrue(g.safe.contains(run.bbox, 1e-6), (run.text, run.bbox, g.safe))
            if run.role in ('name', 'meta', 'separator'):
                self.assertTrue(g.text.contains(run.bbox, 1e-6), (run.text, run.bbox, g.text))
                self.assertTrue(g.panel.contains(run.bbox, 1e-6))
            if run.role == 'header':
                self.assertTrue(g.band.contains(run.bbox, 1e-6), (run.text, run.bbox, g.band))
            self.assertGreaterEqual(run.size, run.floor - 1e-9, run)

    def test_text_box_numbers_for_ol3016lp(self):
        g = L.geometry(OL)
        self.assertAlmostEqual(g.safe.x, 3.2 * 72 / 25.4, places=6)
        self.assertAlmostEqual(g.band.h, 37.44, places=6)
        self.assertAlmostEqual(g.text.w, 105.698, places=2)
        self.assertAlmostEqual(g.text.h, 77.618, places=2)

    def test_proportional_on_a_bigger_stock(self):
        small, big = L.geometry(OL), L.geometry(big_stock())
        self.assertAlmostEqual(big.band.h / small.band.h, 1.5, places=6)
        self.assertGreater(big.text.w, 1.5 * small.text.w)   # the safe inset is fixed

    def test_single_name_worst_cases_stay_inside(self):
        for stock in (OL, big_stock()):
            for name in WORST:
                item = single_name_items(data({4: {1: [(1, name)]}}, sessions=[KEYNOTE]))[0]
                layout = L.layout_single(item, stock)
                self.assert_contained(layout)
                self.assertLessEqual(layout.name_lines, 2)

    def test_single_name_floor_and_ellipsis(self):
        item = single_name_items(data({4: {1: [(1, WORST[1])]}}, sessions=[KEYNOTE]))[0]
        layout = L.layout_single(item, OL)
        names = [r for r in layout.runs if r.role == 'name']
        self.assertEqual({r.size for r in names}, {L.SINGLE_NAME_FLOOR})
        self.assertTrue(layout.truncated)
        self.assertTrue(names[-1].text.endswith(L.ELLIPSIS))

    def test_running_worst_cases_stay_inside(self):
        for stock in (OL, big_stock()):
            for count in range(1, 13):
                for sessions in ((KEYNOTE,), (KEYNOTE, PANEL, BREAKOUT)):
                    names = (WORST * 2)[:count]
                    for page in running_pages(names, stock, sessions):
                        self.assert_contained(L.layout_running(page, stock))

    def test_running_capacity_on_ol3016lp(self):
        self.assertEqual(L.running_order_capacity(OL), 3)          # worst case
        pages = running_pages(['Ann Lee'] * 6)                      # one session
        self.assertEqual(len(pages), 1)
        pages = running_pages(['Ann Lee'] * 7)
        self.assertEqual(len(pages), 2)
        # Two sessions on a label: four names, split 3 + 1 at most.
        pages = running_pages(['Ann Lee'] * 4, sessions=(KEYNOTE, PANEL))
        self.assertEqual(len(pages), 1)

    def test_separator_clears_the_descenders_above_it(self):
        sessions = (KEYNOTE, PANEL, BREAKOUT)
        for stock in (OL, big_stock()):
            for count in (3, 6, 12):
                for page in running_pages(['Sarah McMillan'] * count, stock, sessions):
                    layout = L.layout_running(page, stock)
                    text = [r for r in layout.runs if r.role != 'header']
                    for above, row in zip(text, text[1:]):
                        if row.role != 'separator':
                            continue
                        name_size = above.size
                        clear = above.bbox.y - row.bbox.top
                        self.assertGreaterEqual(clear + 1e-6, 0, (stock.part, row.text))
                        gap = (above.y - row.y) - (row.size * L.SEPARATOR_LEADING)
                        self.assertGreaterEqual(gap + 1e-6, L.SEPARATOR_GAP * name_size)
                    self.assertEqual(text[0].role, 'separator')

    def test_few_names_grow_and_are_centred(self):
        g = L.geometry(OL)
        for names in (['Ann Lee'], ['Ann Lee', 'Bob Ray'], ['WILLIAM M. MORROW']):
            layout = L.layout_running(running_pages(names)[0], OL)
            lines = [r for r in layout.runs if r.role == 'name']
            size = lines[0].size
            self.assertGreater(size, 16, names)
            self.assertLessEqual(size, g.single_name_max)
            self.assertLessEqual(layout.name_lines, 2 * len(names))
            self.assertFalse(layout.truncated)
            top = max(r.bbox.top for r in lines)
            bottom = min(r.bbox.y for r in lines)
            self.assertAlmostEqual(g.text.top - top, bottom - g.text.y, places=3)
        # A full label stays at the floor.
        layout = L.layout_running(running_pages(['Ann Lee'] * 6)[0], OL)
        self.assertEqual({r.size for r in layout.runs if r.role == 'name'},
                         {L.RUNNING_NAME_FLOOR})

    def test_merged_row_after_another_name_regression(self):
        # Printed RF 01 read "Session 1 +2 / sam / Sarah McMillan": the run
        # belongs to Sarah, so it goes on her row and the separator is plain.
        s1, s2, s3 = (S(10 + i, i, f'Session {i + 1}', '') for i in range(3))
        sam, sarah = (20, 'sam'), (21, 'Sarah McMillan')
        d = data({1: {s1.id: [sam, sarah], s2.id: [sarah], s3.id: [sarah]}},
                 sessions=[s1, s2, s3])
        (unit,) = running_units(d)
        self.assertEqual(unit.groups, (('Session 1', (('sam', ''), ('Sarah McMillan', 'S1–3'))),))
        (page,) = [p for u in running_units(d) for p in L.paginate_running(u, OL)]
        layout = L.layout_running(page, OL)
        texts = [(r.role, r.text) for r in layout.runs if r.role != 'header']
        # "Sarah McMillan · S1–3" is 109.3 pt at the 11 pt floor against a
        # 105.7 pt line, so the suffix wraps and the name stays whole.
        self.assertEqual(texts, [('separator', 'Session 1'), ('name', 'sam'),
                                 ('name', 'Sarah McMillan'), ('suffix', 'S1–3')])
        name, suffix = layout.runs[-2], layout.runs[-1]
        self.assertLess(suffix.y, name.y)
        self.assertEqual(suffix.x - name.x, L.WRAP_INDENT)
        self.assertEqual((suffix.font, suffix.size), (fonts.BOLD, L.geometry(OL).small))
        self.assert_contained(layout)
        self.assertFalse(any('+' in r.text for r in layout.runs))
        # Single-name mode keeps its meta line.
        items = single_name_items(d)
        self.assertEqual([(i.name, i.session) for i in items],
                         [('sam', 'Session 1'), ('Sarah McMillan', 'Session 1 +2')])

    def test_suffix_wraps_before_the_name_does(self):
        g = L.geometry(OL)
        # 101.5 pt of a 105.7 pt line: the name fits, the suffix does not.
        row = L.Row('name', 'Christopher Brown', 'S1–3')
        lines, truncated = L._row_lines(row, g, L.RUNNING_NAME_FLOOR)
        self.assertFalse(truncated)
        self.assertEqual([(l.role, l.text, l.suffix) for l in lines],
                         [('name', 'Christopher Brown', ''), ('suffix', 'S1–3', '')])
        # A short name keeps it inline.
        lines, _ = L._row_lines(L.Row('name', 'Ann Lee', 'S1–3'), g, L.RUNNING_NAME_FLOOR)
        self.assertEqual([(l.role, l.suffix) for l in lines], [('name', ' · S1–3')])
        # Laid out among other names, everything stays inside.
        page = L.RunningPage(4, ('Tue Nov 3',), (
            L.Row('separator', '9:00a · Keynote'), L.Row('name', 'Ann Lee'),
            L.Row('name', 'Christopher Brown', 'S1–3'), L.Row('name', 'Bob Ray', 'S1–2')))
        layout = L.layout_running(page, OL)
        self.assert_contained(layout)
        roles = [r.role for r in layout.runs if r.role != 'header']
        self.assertEqual(roles, ['separator', 'name', 'name', 'suffix', 'name', 'suffix'])
        self.assertEqual(layout.name_lines, 3)

    def test_growing_never_breaks_a_word(self):
        for name in ('Christopher Brown', 'Bartholomew Smith', 'Jacqueline Mwangi'):
            item = single_name_items(data({4: {1: [(1, name)]}}, sessions=[KEYNOTE]))[0]
            for layout in (L.layout_single(item, OL),
                           L.layout_running(running_pages([name])[0], OL)):
                lines = [r.text for r in layout.runs if r.role == 'name']
                self.assertEqual(lines, name.split(' '), name)

    def test_running_disabled_on_a_small_stock(self):
        available, reason = L.running_order_available(small_stock())
        self.assertFalse(available)
        self.assertIn('TEST-1IN', reason)
        self.assertTrue(L.running_order_available(OL)[0])

    def test_17_char_mixed_case_names_are_never_truncated_at_the_floor(self):
        # All-caps is deliberately excluded: "WILLIAM M. MORROW" is 115.9 pt
        # at 11 pt against a 105.7 pt line. It wraps instead (next test).
        for name in FIXTURE_17:
            self.assertLessEqual(len(name), 17)
            page = running_pages([name] * 5)[0]
            layout = L.layout_running(page, OL)
            names = [r for r in layout.runs if r.role == 'name']
            self.assertEqual([r.text for r in names], [name] * 5, name)
            self.assertFalse(layout.truncated)

    def test_all_caps_17_wraps_to_two_lines_without_ellipsis(self):
        caps = 'WILLIAM M. MORROW'
        page = running_pages([caps])[0]
        layout = L.layout_running(page, OL)
        lines = [r for r in layout.runs if r.role == 'name']
        self.assertEqual(len(lines), 2)
        self.assertEqual(' '.join(r.text for r in lines), caps)
        self.assertFalse(layout.truncated)
        self.assertEqual(lines[1].x - lines[0].x, L.WRAP_INDENT)

    def test_wrapped_name_counts_toward_capacity(self):
        self.assertEqual(len(running_pages(['Ann Lee'] * 6)), 1)
        # Five one-line names and one two-line name are seven lines: too many.
        pages = running_pages(['Ann Lee'] * 5 + ['WILLIAM M. MORROW'])
        self.assertEqual(len(pages), 2)
        self.assertEqual([p.part for p in pages], [(1, 2), (2, 2)])

    def test_ellipsis_only_beyond_two_lines(self):
        layout = L.layout_running(running_pages([WORST[1]])[0], OL)
        lines = [r for r in layout.runs if r.role == 'name']
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].text.endswith(L.ELLIPSIS))
        self.assertTrue(layout.truncated)

    def test_overflow_labels_and_repeated_separator(self):
        sessions = (KEYNOTE, PANEL)
        names = ['Ann Lee'] * 12
        pages = running_pages(names, sessions=sessions)
        self.assertGreater(len(pages), 1)
        n = len(pages)
        self.assertEqual([p.part for p in pages], [(i, n) for i in range(1, n + 1)])
        for page in pages:
            self.assertEqual(page.rows[0].kind, 'separator')     # never starts bare
            self.assertEqual(page.rows[-1].kind, 'name')         # never ends on one
        # Every name made it onto a label exactly once.
        self.assertEqual(sum(r.kind == 'name' for p in pages for r in p.rows), 12)

    def test_header_numbers_match_the_tracker_badge(self):
        item = single_name_items(data({4: {1: [ZOE]}}, sessions=[KEYNOTE]))[0]
        texts = [r.text for r in L.layout_single(item, OL).runs if r.role == 'header']
        self.assertIn('RF', texts)
        self.assertIn('04', texts)
        page = running_pages(['Ann Lee'] * 7)[1]
        texts = [r.text for r in L.layout_running(page, OL).runs if r.role == 'header']
        self.assertIn('2/2', texts)


# ---------------------------------------------------------------- fonts

class FontTests(SimpleTestCase):
    NAMES = ['Nguyễn Đặng', 'Zoë Müller-Łukasz']

    def test_every_glyph_is_in_every_label_font(self):
        for font in (fonts.REGULAR, fonts.SEMIBOLD, fonts.BOLD):
            for name in self.NAMES + ['9:00a · Keynote +2 …']:
                self.assertEqual(fonts.missing_glyphs(name, font), [], (font, name))

    def test_decomposed_input_is_composed(self):
        nfd = unicodedata.normalize('NFD', 'Nguyễn Đặng')
        self.assertNotEqual(nfd, 'Nguyễn Đặng')
        self.assertEqual(fonts.normalise(nfd), 'Nguyễn Đặng')
        self.assertEqual(fonts.missing_glyphs(nfd, fonts.BOLD), [])

    def test_pdf_embeds_noto_and_no_builtin_font(self):
        from PyPDF2 import PdfReader
        d = data({4: {1: [(1, n) for n in self.NAMES]}}, sessions=[KEYNOTE])
        for mode in ('single', 'running'):
            pdf, count = generate_labels_pdf(d, mode, OL, Options())
            self.assertGreater(count, 0)
            fonts_used = set()
            for page in PdfReader(BytesIO(pdf)).pages:
                for f in page['/Resources']['/Font'].values():
                    f = f.get_object()
                    fonts_used.add(str(f['/BaseFont']))
                    descendant = f.get('/DescendantFonts') or [f]
                    for d_font in descendant:
                        d_font = d_font.get_object()
                        descriptor = d_font.get('/FontDescriptor')
                        if descriptor is not None:
                            self.assertIn('/FontFile2', descriptor.get_object())
            self.assertTrue(fonts_used)
            self.assertFalse([f for f in fonts_used if 'Helvetica' in f], fonts_used)
            self.assertTrue(all('NotoSans' in f for f in fonts_used), fonts_used)

    def test_alignment_page_renders(self):
        pdf = render_alignment_pdf(OL, Options(dx_mm=1.5, dy_mm=-2))
        self.assertTrue(pdf.startswith(b'%PDF'))


# ---------------------------------------------------------------- database + views

class LabelViewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        from planner.models import (
            MicAssignment, MicSession, Presenter, PresenterSlot, Project, ShowDay, UserProfile,
        )
        cls.owner = User.objects.create_user('owner', 'o@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=cls.owner, defaults={'account_type': 'paid'})
        cls.project = Project.objects.create(name='Main Show', owner=cls.owner)
        cls.day = ShowDay.objects.create(project=cls.project, date=datetime.date(2026, 11, 3))
        cls.keynote = MicSession.objects.create(day=cls.day, name='Keynote', num_mics=12, order=0,
                                                start_time=datetime.time(9, 0))
        cls.panel = MicSession.objects.create(day=cls.day, name='Panel', num_mics=12, order=1,
                                              start_time=datetime.time(10, 30))
        zoe = Presenter.objects.create(project=cls.project, name='Zoë Müller-Łukasz')
        bob = Presenter.objects.create(project=cls.project, name='Bob')

        def slots(session, rf, *presenters):
            a = MicAssignment.objects.get(session=session, rf_number=rf)
            for i, p in enumerate(presenters):
                PresenterSlot.objects.create(assignment=a, presenter=p, order=i)

        slots(cls.keynote, 2, zoe)
        slots(cls.panel, 2, zoe)              # merges with the keynote
        slots(cls.keynote, 10, bob, None)     # one empty slot: skipped
        slots(cls.panel, 3, None)             # another empty slot

        cls.other_owner = User.objects.create_user('other', 'x@example.com', 'pw', is_staff=True)
        cls.other = Project.objects.create(name='Other', owner=cls.other_owner)
        cls.other_day = ShowDay.objects.create(project=cls.other, date=datetime.date(2026, 11, 3))
        cls.other_session = MicSession.objects.create(day=cls.other_day, name='Theirs', num_mics=2)

    def login(self, user, project=None):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = (project or self.project).pk
        session.save()

    def member(self, name, role, plan='paid'):
        from planner.models import ProjectMember, UserProfile
        user = User.objects.create_user(name, f'{name}@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': plan})
        ProjectMember.objects.create(user=user, project=self.project, role=role, invited_by=self.owner)
        return user

    def pdf_url(self, **params):
        query = {'sessions': self.keynote.pk, 'mode': 'single'}
        query.update(params)
        return reverse('planner:mic_labels_pdf') + '?' + '&'.join(f'{k}={v}' for k, v in query.items())

    def summary(self, **params):
        url = self.pdf_url(**params).replace(reverse('planner:mic_labels_pdf'),
                                             reverse('planner:mic_labels_summary'))
        return self.client.get(url)

    def all_urls(self):
        return [reverse('planner:mic_tracker_print'), self.pdf_url(),
                reverse('planner:mic_labels_alignment_pdf'), self.summary_url()]

    def summary_url(self):
        return reverse('planner:mic_labels_summary') + f'?sessions={self.keynote.pk}'

    def both(self):
        return f'{self.keynote.pk},{self.panel.pk}'

    def add_session(self, day, name, order, rf=None, presenter=None):
        from planner.models import MicAssignment, MicSession, PresenterSlot
        session = MicSession.objects.create(day=day, name=name, num_mics=12, order=order)
        if presenter is not None:
            a = MicAssignment.objects.get(session=session, rf_number=rf)
            PresenterSlot.objects.create(assignment=a, presenter=presenter, order=0)
        return session

    # -- data
    def test_scope_data_flattens_the_selected_sessions(self):
        from planner.utils.labels.data import scope_data
        d = scope_data(self.project, [self.keynote.pk, self.panel.pk])
        self.assertEqual([s.name for s in d.sessions], ['Keynote', 'Panel'])
        self.assertEqual([s.index for s in d.sessions], [0, 1])
        self.assertEqual(d.sessions[0].time, '9:00a')
        self.assertEqual(d.skipped, 2)
        self.assertEqual(sorted(d.packs), [2, 10])
        self.assertEqual([(i.pack, i.session) for i in single_name_items(d)],
                         [(2, 'Keynote +1'), (10, 'Keynote')])

    def test_scope_data_one_session_keeps_its_place_in_the_day(self):
        from planner.utils.labels.data import scope_data
        d = scope_data(self.project, [self.panel.pk])
        self.assertEqual(d.skipped, 1)
        self.assertEqual([(s.name, s.index) for s in d.sessions], [('Panel', 1)])

    def test_unselected_session_in_between_breaks_the_merge(self):
        from planner.models import Presenter, ShowDay
        from planner.utils.labels.data import scope_data
        day = ShowDay.objects.create(project=self.project, date=datetime.date(2026, 11, 5))
        amy = Presenter.objects.create(project=self.project, name='Amy')
        a, b, c = (self.add_session(day, n, i, 5, amy) for i, n in enumerate(('A', 'B', 'C')))
        merged = single_name_items(scope_data(self.project, [a.pk, b.pk, c.pk]))
        self.assertEqual([i.session for i in merged], ['A +2'])
        gapped = single_name_items(scope_data(self.project, [a.pk, c.pk]))
        self.assertEqual([i.session for i in gapped], ['A', 'C'])
        units = running_units(scope_data(self.project, [a.pk, c.pk]))
        self.assertEqual([g[0] for g in units[0].groups], ['A', 'C'])

    def test_sessions_across_days(self):
        from planner.models import Presenter, ShowDay
        from planner.utils.labels.data import scope_data
        day2 = ShowDay.objects.create(project=self.project, date=datetime.date(2026, 11, 4))
        cy = Presenter.objects.create(project=self.project, name='Cy')
        opening = self.add_session(day2, 'Opening', 0, 2, cy)
        d = scope_data(self.project, [self.keynote.pk, self.panel.pk, opening.pk])
        units = [u for u in running_units(d) if u.pack == 2]
        # Two selected on Nov 3: the day alone; one on Nov 4: the full header.
        self.assertEqual([u.header for u in units],
                         [('Tue Nov 3',), ('Wed Nov 4', 'Opening')])
        self.login(self.owner)
        body = self.summary(sessions=f'{self.both()},{opening.pk}', mode='running').json()
        self.assertEqual(body['labels'], 3)            # pack 2 on each day, pack 10
        self.assertIn('3-sessions', body['filename'])

    def test_several_sessions_on_one_day(self):
        self.login(self.owner)
        body = self.summary(sessions=self.both(), mode='running').json()
        self.assertEqual(body['labels'], 2)
        self.assertIn('-2026-11-03-', body['filename'])
        body = self.summary(sessions=f'{self.panel.pk},{self.keynote.pk},{self.panel.pk}').json()
        self.assertEqual(body['labels'], 2)            # order and repeats do not matter

    # -- views
    def test_summary_counts_labels_and_skipped_slots(self):
        self.login(self.owner)
        body = self.summary(sessions=self.both()).json()
        self.assertEqual((body['labels'], body['sheets'], body['skipped']), (2, 1, 2))
        self.assertIn('PRINT-AT-100pct', body['filename'])
        body = self.summary(sessions=self.both(), start=12).json()
        self.assertEqual(body['sheets'], 2)

    def test_pdf_response(self):
        self.login(self.owner)
        r = self.client.get(self.pdf_url(sessions=self.both(), mode='running', color='0',
                                         start='3', dx='9', dy='nan'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertEqual(r['X-Frame-Options'], 'SAMEORIGIN')
        self.assertIn('inline;', r['Content-Disposition'])
        self.assertIn('PRINT-AT-100pct.pdf', r['Content-Disposition'])
        r = self.client.get(self.pdf_url(download='1'))
        self.assertIn('attachment;', r['Content-Disposition'])

    def test_bad_parameters(self):
        self.login(self.owner)
        self.assertEqual(self.client.get(self.pdf_url(mode='fancy')).status_code, 400)
        self.assertEqual(self.client.get(self.pdf_url(stock='NOPE')).status_code, 400)
        self.assertEqual(self.client.get(self.pdf_url(sessions='abc')).status_code, 400)
        self.assertEqual(self.client.get(self.pdf_url(sessions='999999')).status_code, 404)

    def test_empty_selection_is_refused_with_a_message(self):
        self.login(self.owner)
        for empty in ('', ',', ' '):
            r = self.client.get(self.pdf_url(sessions=empty))
            self.assertEqual(r.status_code, 400)
            self.assertIn(b'Select at least one session', r.content)
        r = self.summary(sessions='')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Select at least one session', r.json()['error'])
        r = self.client.get(reverse('planner:mic_tracker_print'))
        self.assertContains(r, 'Select at least one session to print.')
        self.assertNotContains(r, 'name="sessions" value="{}" data-day="{}" checked'.format(
            self.keynote.pk, self.day.pk))

    def test_running_order_refused_on_a_stock_too_small(self):
        self.login(self.owner)
        with patch.dict(STOCKS, {'TEST-1IN': small_stock()}):
            r = self.client.get(self.pdf_url(stock='TEST-1IN', mode='running'))
            self.assertEqual(r.status_code, 400)
            r = self.client.get(self.pdf_url(stock='TEST-1IN', mode='single'))
            self.assertEqual(r.status_code, 200)

    def test_owner_editor_viewer_and_free_viewer_can_print(self):
        from accounts.views import accept_invitation_for
        from planner.models import Invitation, UserProfile
        free = User.objects.create_user('freebie', 'free@example.com', 'pw')
        UserProfile.objects.update_or_create(user=free, defaults={'account_type': 'free'})
        invitation = Invitation.objects.create(project=self.project, email='free@example.com',
                                               role='viewer', invited_by=self.owner)
        self.assertTrue(accept_invitation_for(free, invitation))
        free.refresh_from_db()
        self.assertFalse(free.is_superuser)

        users = [self.owner, self.member('ed', 'editor'), self.member('vi', 'viewer'), free]
        for user in users:
            self.assertFalse(user.is_superuser)
            self.login(user)
            for url in self.all_urls():
                self.assertEqual(self.client.get(url).status_code, 200, (user.username, url))

    def test_another_tenants_ids_are_404(self):
        self.login(self.other_owner, self.other)
        self.assertEqual(self.client.get(self.pdf_url()).status_code, 404)
        self.assertEqual(self.client.get(self.summary_url()).status_code, 404)
        # One foreign id among their own is enough to refuse the lot.
        mixed = f'{self.other_session.pk},{self.keynote.pk}'
        self.assertEqual(self.client.get(self.pdf_url(sessions=mixed)).status_code, 404)
        self.assertEqual(self.summary(sessions=mixed).status_code, 404)
        # Their own session works; ours is not offered as a preselection.
        r = self.client.get(self.pdf_url(sessions=self.other_session.pk))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse('planner:mic_tracker_print') + f'?session={self.keynote.pk}')
        self.assertEqual(r.context['selected_session'], 0)
        self.assertNotContains(r, 'Keynote')

    def test_non_member_session_cannot_select_the_project(self):
        # A staff account with no project at all, holding our project's id in
        # its session: the middleware never resolves it, so nothing serves.
        stranger = User.objects.create_user('stranger', 's@example.com', 'pw', is_staff=True)
        self.login(stranger)
        r = self.client.get(reverse('planner:mic_tracker_print'))
        self.assertRedirects(r, reverse('planner:mic_tracker'), fetch_redirect_response=False)
        self.assertEqual(self.client.get(self.pdf_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse('planner:mic_labels_alignment_pdf')).status_code, 404)

    def test_non_staff_get_the_same_login_redirect_as_the_tracker(self):
        plain = User.objects.create_user('plain', 'p@example.com', 'pw')
        self.login(plain)
        tracker = self.client.get(reverse('planner:mic_tracker'))
        for url in self.all_urls():
            r = self.client.get(url)
            self.assertEqual(r.status_code, tracker.status_code, url)
            self.assertIn('/login/', r['Location'])

    def test_print_button_shows_for_viewers_but_grp_does_not(self):
        viewer = self.member('vi2', 'viewer')
        self.login(viewer)
        r = self.client.get(reverse('planner:mic_tracker'))
        self.assertContains(r, 'class="btn-mtt btn-mtt-ghost a2-print-labels"', count=2)
        self.assertContains(r, reverse('planner:mic_tracker_print') + f'?session={self.keynote.pk}')
        self.assertNotContains(r, f'openGroupManager({self.keynote.pk})')
        self.login(self.owner)
        r = self.client.get(reverse('planner:mic_tracker'))
        self.assertContains(r, f'openGroupManager({self.keynote.pk})')
        self.assertContains(r, 'a2-print-labels', count=2)

    def test_header_print_button_opens_the_page_with_nothing_preselected(self):
        viewer = self.member('vi3', 'viewer')
        self.login(viewer)
        r = self.client.get(reverse('planner:mic_tracker'))
        url = reverse('planner:mic_tracker_print')
        self.assertContains(r, f'<a href="{url}" class="btn-mtt btn-mtt-export">🖨 Print Labels</a>',
                            html=True)
        r = self.client.get(url)
        self.assertEqual(r.context['selected_session'], 0)

    def test_print_page_preselects_the_session(self):
        self.login(self.owner)
        r = self.client.get(reverse('planner:mic_tracker_print') + f'?session={self.panel.pk}')
        self.assertEqual(r.context['selected_session'], self.panel.pk)
        box = '<input type="checkbox" name="sessions" value="{}" data-day="{}"{}>'
        self.assertContains(r, box.format(self.panel.pk, self.day.pk, ' checked'))
        self.assertContains(r, box.format(self.keynote.pk, self.day.pk, ''))
        self.assertContains(r, 'Print at 100%')
        self.assertTrue(r.context['running_available'])
