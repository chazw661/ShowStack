"""Mic Plan PR 4: the A2 schedule screen, plan.json?head=1 for its poll, the
PDF (schedule, pack sheet, review), the overlapping-parts warning (#169) and
the pack chart's per-part header strips (#168). Made-up names.

PDF text is read with pdfplumber (a dependency), never pypdf.

Run with::

    python manage.py test planner.tests.test_mic_plan_a2 --settings=audiopatch.test_settings
"""

from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase as PlainTestCase

import pdfplumber
from django.urls import reverse
from PIL import Image

from planner.mic_plan import page, schedule
from planner.mic_plan.display import overlap_warning
from planner.models import MicPlan, ProjectLogo, ShowDay, ShowflowImport
from planner.tests.test_mic_plan_edits import EditBase


def seg(row, part, t0, t1, is_break=False, name=None, line=None):
    return {'row': row, 'part': part, 'line': line or str(row), 'name': name or 'Seg {}'.format(row),
            't0': t0, 't1': t1, 'is_break': is_break, 'busy': [], 'spill': 0, 'spill_into': ''}


def pdf_text(content):
    with pdfplumber.open(BytesIO(content)) as doc:
        return '\n'.join(p.extract_text() or '' for p in doc.pages), doc.pages


# --------------------------------------------------------------------------
# Pure: sessions, overlaps, strips, the A2 choice
# --------------------------------------------------------------------------

class SessionTests(PlainTestCase):

    def test_a_break_starts_a_session(self):
        segs = [seg(1, 10, 480, 540), seg(2, 10, 540, 560, is_break=True), seg(3, 10, 560, 600)]
        self.assertEqual({1: 0, 2: 1, 3: 1}, schedule.sessions(segs))

    def test_a_part_after_every_earlier_part_starts_a_session(self):
        segs = [seg(1, 10, 480, 540), seg(2, 10, 540, 600), seg(3, 11, 780, 840)]
        self.assertEqual({1: 0, 2: 0, 3: 1}, schedule.sessions(segs))

    def test_a_break_at_the_top_of_the_day_is_session_one(self):
        segs = [seg(1, 10, 420, 480, is_break=True), seg(2, 10, 480, 540)]
        self.assertEqual({1: 0, 2: 0}, schedule.sessions(segs))

    def test_the_a2_asked_for_or_the_first(self):
        self.assertEqual(2, schedule.a2_choice('2', 2))
        for junk in (None, '', 'x', '0', '3', '-1'):
            self.assertEqual(1, schedule.a2_choice(junk, 2), junk)


class OverlapTests(PlainTestCase):

    def test_parts_that_run_at_once_overlap_and_touching_ones_do_not(self):
        touching = [seg(1, 10, 480, 600), seg(2, 11, 600, 700)]
        self.assertEqual([], page.overlapping_parts(touching))
        both = [seg(1, 10, 480, 600), seg(2, 11, 540, 700), seg(3, 12, 800, 900)]
        self.assertEqual([(10, 11)], page.overlapping_parts(both))

    def test_the_warning_names_the_part_numbers(self):
        plan = SimpleNamespace(segments=[seg(1, 10, 480, 600), seg(2, 11, 540, 700)])
        parts = [SimpleNamespace(pk=10), SimpleNamespace(pk=11)]
        self.assertEqual([overlap_warning(1, 2)], page.overlap_warnings(plan, parts))
        self.assertIn("Parts 1 and 2 overlap in time", overlap_warning(1, 2))


class ChartStripTests(PlainTestCase):
    """#168: bands of different parts never share a strip when parts overlap."""

    def chart(self, segments):
        plan = SimpleNamespace(segments=segments, packs=[{'rf': 1, 'pool': 'body'}], changes=[], settings={})
        parts = [SimpleNamespace(pk=10), SimpleNamespace(pk=11)]
        return page.pack_chart(plan, [], [], parts)

    def test_one_strip_without_overlap(self):
        chart = self.chart([seg(1, 10, 480, 540), seg(2, 10, 540, 600), seg(3, 11, 600, 660)])
        self.assertEqual([''], [s['label'] for s in chart['strips']])
        self.assertEqual(3, len(chart['strips'][0]['bands']))

    def test_one_strip_per_part_when_parts_overlap_and_no_band_overlaps_in_a_strip(self):
        chart = self.chart([seg(1, 10, 480, 510, name='Opening'), seg(2, 10, 510, 540),
                            seg(3, 11, 480, 525, name='Opening Session'), seg(4, 11, 525, 540)])
        self.assertEqual(['Part 1', 'Part 2'], [s['label'] for s in chart['strips']])
        for strip in chart['strips']:
            spans = sorted((b['left'], b['left'] + b['width']) for b in strip['bands'])
            for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
                self.assertLessEqual(a1, b0 + 1e-6)


# --------------------------------------------------------------------------
# Views and PDF
# --------------------------------------------------------------------------

class A2Base(EditBase):

    def a2_url(self, **query):
        url = reverse('planner:mic_plan_a2', args=[self.day.pk])
        return url + ('?' + '&'.join('{}={}'.format(k, v) for k, v in query.items()) if query else '')

    def pdf_url(self, **query):
        url = reverse('planner:mic_plan_pdf', args=[self.day.pk])
        return url + ('?' + '&'.join('{}={}'.format(k, v) for k, v in query.items()) if query else '')

    def head_url(self):
        return reverse('planner:mic_plan_json', args=[self.day.pk]) + '?head=1'

    def pdf(self, **query):
        resp = self.client.get(self.pdf_url(**query))
        self.assertEqual(200, resp.status_code)
        self.assertEqual('application/pdf', resp['Content-Type'])
        self.assertTrue(resp.content.startswith(b'%PDF'))
        return pdf_text(resp.content)

    def two_a2s(self):
        self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 2, 'mic_min': 3, 'demic_min': 3, 'premic_lead_min': 30, 'margin_min': 5})
        self.generate()


class ScheduleScreenTests(A2Base):

    def test_the_schedule_shows_every_action_of_the_a2_by_segment(self):
        resp = self.client.get(self.a2_url())
        self.assertEqual(200, resp.status_code)
        sched = resp.context['sched']
        plan = self.plan()
        self.assertEqual(plan.actions.count(), sched['count'])
        shown = [seg['row'] for sess in sched['sessions'] for seg in sess['segments']]
        self.assertEqual(sorted(s['row'] for s in plan.segments), sorted(shown))
        self.assertContains(resp, 'DE-MIC')
        self.assertContains(resp, 'Plan v{}'.format(plan.version))
        self.assertContains(resp, 'data-version="{}"'.format(plan.version))
        self.assertIn('no-store', resp['Cache-Control'])

    def test_it_is_read_only_for_everyone_and_viewers_may_open_it(self):
        for user in (self.editor, self.viewer, self.owner):
            self.use(user)
            resp = self.client.get(self.a2_url())
            self.assertEqual(200, resp.status_code)
            self.assertNotContains(resp, '<form')
            self.assertNotContains(resp, 'csrfmiddlewaretoken')

    def test_another_projects_day_is_404_everywhere(self):
        self.use(self.other_owner, self.other)
        self.assertEqual(404, self.client.get(self.a2_url()).status_code)
        self.assertEqual(404, self.client.get(self.pdf_url()).status_code)
        self.assertEqual(404, self.client.get(self.head_url()).status_code)

    def test_a_day_without_a_plan_says_so(self):
        day2 = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        resp = self.client.get(reverse('planner:mic_plan_a2', args=[day2.pk]))
        self.assertContains(resp, 'No plan for')
        self.assertEqual(404, self.client.get(reverse('planner:mic_plan_pdf', args=[day2.pk])).status_code)

    def test_the_a2_filter_shows_only_that_a2(self):
        self.two_a2s()
        plan = self.plan()
        self.assertEqual(2, plan.settings['a2_count'])
        counts = {n: plan.actions.filter(a2_index=n).count() for n in (1, 2)}
        self.assertTrue(counts[1] and counts[2], counts)
        sched = self.client.get(self.a2_url(a2=2)).context['sched']
        self.assertEqual((2, counts[2]), (sched['a2'], sched['count']))
        resp = self.client.get(self.a2_url(a2=9))
        self.assertEqual((1, counts[1]), (resp.context['sched']['a2'], resp.context['sched']['count']))
        self.assertContains(resp, 'aria-current="page">A2 1</a>')

    def test_one_a2_has_no_picker(self):
        self.assertNotContains(self.client.get(self.a2_url()), 'aria-label="Which A2"')

    def test_moves_are_marked_pinned(self):
        self.edit('move_rf', self.key('Kim Keynote'), rf=7, pool='body')
        resp = self.client.get(self.a2_url())
        self.assertContains(resp, 'PINNED')
        self.assertContains(resp, 'edited: 1 change')

    def test_the_mic_plan_page_links_to_the_schedule_in_a_new_window_and_the_pdf(self):
        resp = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(resp, 'href="{}" target="_blank" rel="noopener"'.format(self.a2_url()))
        self.assertContains(resp, 'href="{}" target="_blank"'.format(self.pdf_url()))
        self.assertNotContains(resp, 'window.open')

    def test_a_stale_plan_shows_the_stale_banner(self):
        MicPlan.objects.filter(pk=self.plan().pk).update(stale=True)
        resp = self.client.get(self.a2_url())
        self.assertContains(resp, 'id="a2-stale" role="status">')       # not hidden


class VersionPollTests(A2Base):
    """What the schedule's 30 s poll reads: a newer version raises the
    banner (mic_plan_a2.js only compares versions)."""

    def test_head_is_the_version_and_stale_flag_never_cached(self):
        plan = self.plan()
        resp = self.client.get(self.head_url())
        self.assertEqual({'version': plan.version, 'stale': False}, resp.json())
        self.assertIn('no-store', resp['Cache-Control'])

    def test_an_edit_or_re_generate_changes_the_version_the_page_was_built_with(self):
        built = self.client.get(self.a2_url()).context['plan'].version
        self.edit('move_rf', self.key('Kim Keynote'), rf=7, pool='body')
        after_edit = self.client.get(self.head_url()).json()['version']
        self.assertNotEqual(built, after_edit)
        self.generate()
        self.assertNotEqual(after_edit, self.client.get(self.head_url()).json()['version'])

    def test_a_stale_plan_reports_stale(self):
        MicPlan.objects.filter(pk=self.plan().pk).update(stale=True)
        self.assertTrue(self.client.get(self.head_url()).json()['stale'])


class PdfTests(A2Base):

    def test_one_a2(self):
        text, pages = self.pdf()
        plan = self.plan()
        self.assertIn('A2 schedule', text)
        self.assertNotIn('A2 schedule — A2', text)
        self.assertIn('Pack sheet', text)
        self.assertIn('Review', text)
        self.assertIn('MIC', text)
        self.assertIn('DE-MIC', text)
        self.assertIn('Settings: Recycle at breaks', text)
        # Header and footer on every page.
        for p in pages:
            t = p.extract_text()
            self.assertIn('Mic Plan — MP Show', t)
            self.assertIn('Plan v{} · Printed'.format(plan.version), t)
        self.assertGreaterEqual(len(pages), 1)

    def test_two_a2s_each_get_a_section_and_a2_n_only_one(self):
        self.two_a2s()
        text, _ = self.pdf()
        self.assertIn('A2 schedule — A2 1', text)
        self.assertIn('A2 schedule — A2 2', text)
        text, _ = self.pdf(a2=2)
        self.assertNotIn('A2 schedule — A2 1', text)
        self.assertIn('A2 schedule — A2 2', text)

    def test_a_cue_free_plan_says_it_is_based_on_line_estimates(self):
        day2 = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        self.upload('CLIENT_E_PAGES', day=day2)
        self.client.post(reverse('planner:mic_plan_generate', args=[day2.pk]))
        self.assertEqual('line estimates', MicPlan.objects.get(day=day2).cue_mode)
        resp = self.client.get(reverse('planner:mic_plan_pdf', args=[day2.pk]))
        text, _ = pdf_text(resp.content)
        self.assertIn('Based on line estimates', text)
        self.assertIn('times from line estimates', text)
        self.assertContains(self.client.get(reverse('planner:mic_plan_a2', args=[day2.pk])),
                            'Based on line estimates')
        text, _ = self.pdf()                     # the cued day does not say it
        self.assertNotIn('Based on line estimates', text)

    def test_a_plan_with_edits_and_a_conflict(self):
        self.edit('move_rf', self.key('Dana Able'), rf=3, pool='body')
        self.edit('move_rf', self.key('Chris Baker'), rf=3, pool='body')
        self.assertTrue(any(f['kind'] == 'conflict' for f in self.plan().flags))
        text, _ = self.pdf()
        self.assertIn('edited: 2 changes', text)
        self.assertIn('PINNED', text)
        self.assertIn('CONFLICT', text)
        self.assertIn('RF 3 on two people', text)
        review = text[text.rindex('Review'):]
        self.assertRegex(review, r'Line \S+')

    def test_the_viewers_time_zone_is_used_for_printed_times(self):
        text, _ = self.pdf(tz='America/New_York')
        self.assertRegex(text, r'Printed \w{3} \d+, \d{4} \d\d:\d\d E[SD]T')
        text, _ = self.pdf(tz='Not/AZone')
        self.assertRegex(text, r'Printed \w{3} \d+, \d{4} \d\d:\d\d UTC')

    def test_the_project_logo_is_printed_when_set(self):
        _, pages = self.pdf()
        self.assertEqual(0, len(pages[0].images))
        png = BytesIO()
        Image.new('RGB', (200, 60), (20, 40, 80)).save(png, 'PNG')
        ProjectLogo.objects.create(project=self.project, kind='on_light', content=png.getvalue(),
                                   content_type='image/png', sha256='x' * 64, width=200, height=60)
        _, pages = self.pdf()
        self.assertTrue(all(len(p.images) == 1 for p in pages))

    def test_viewers_may_download_it(self):
        self.use(self.viewer)
        self.pdf()


class OverlapWarningTests(A2Base):
    """#169: overlapping parts are one stage; the plan says so everywhere."""

    def setUp(self):
        super().setUp()
        plan = self.plan()
        other = ShowflowImport.objects.create(day=self.day, status='active', part_order=1,
                                              source_filename='second.pdf')
        # The plan's last segment as if it belonged to a second part running
        # at the same time as the first.
        segs = list(plan.segments)
        first = segs[0]
        segs.append(dict(first, row=first['row'] + 100000, part=other.pk, name='Breakout'))
        plan.segments = segs
        plan.save(update_fields=['segments'])
        self.text = overlap_warning(1, 2)

    def test_the_mic_plan_page_the_schedule_and_the_pdf_warn(self):
        self.assertContains(self.client.get(reverse('planner:mic_plan')), "Parts 1 and 2 overlap in time")
        self.assertContains(self.client.get(self.a2_url()), "Parts 1 and 2 overlap in time")
        text, _ = self.pdf()
        self.assertIn('Parts 1 and 2 overlap in time', ' '.join(text.split()))

    def test_the_pack_chart_gets_a_strip_per_part(self):
        resp = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(resp, '<span class="slab">Part 1</span>')
        self.assertContains(resp, '<span class="slab">Part 2</span>')
