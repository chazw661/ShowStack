"""Mic Planner: Review cards checked off (MicPlanReviewCheck, mic_plan/checks).
Check / note / uncheck; the counts on the tab, the "To review" tile and the
dashboard card; a check survives Re-generate, Re-read and Replace while the
card's fingerprint holds and drops when its numbers change; blockers still
block Send and are listed on its preview; the PDF's Checked list; viewer
403, another project 404. Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_review_checks --settings=audiopatch.test_settings
"""

import io
import re

import pdfplumber
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import checks, importer, planning, push
from planner.models import MicPlan, MicPlanReviewCheck, ShowflowImport
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase


class MaterialTests(SimpleTestCase):

    def test_numbers_are_material_versions_and_stamps_are_not(self):
        self.assertEqual(['12', '10', '42', '3'],
                         checks.material('Line 12: Avery is ready at 10:42, 3 min after walking on.'))
        self.assertEqual(['5'], checks.material('Plan v8, sent v12 on 2026-11-13T14:02:11Z: RF 5 at 14:02:11'))

    def test_the_suggested_fix_is_not_material(self):
        base = 'Break at line 312 too short to turn over 1 pack.'
        for advice in (' Fix: 1 de-mic helper at the 8:45a break (line 312).',
                       ' Fix for these 3 mics: pre-mic lead 12 min (now 10), or a second A2.',
                       ' Fix: see line 40.', ' No pre-mic lead up to 240 min or extra A2 puts these on time.'):
            self.assertEqual(checks.material(base), checks.material(base + advice), advice)

    def test_fingerprint_follows_kind_part_line_person_and_numbers(self):
        keys = {7: 'avery able'}
        card = {'kind': 'late', 'part_no': 1, 'line': '12', 'person': 7, 'text': 'Ready 3 min late.'}
        fp = checks.fingerprint(card, keys)
        self.assertEqual(fp, checks.fingerprint(dict(card, text='Now ready 3 min late (reworded).'), keys))
        for change in ({'text': 'Ready 4 min late.'}, {'kind': 'tight'}, {'part_no': 2}, {'line': '13'},
                       {'person': 8}):
            self.assertNotEqual(fp, checks.fingerprint(dict(card, **change), keys), change)


class CheckBase(MicPlanBase):

    pages = F.MAIN_PAGES

    def setUp(self):
        super().setUp()
        self.settings_obj = planning.project_settings(self.project)
        self.use(self.editor)
        self.load(self.pages)

    def load(self, pages, replace=None):
        part = importer.stage_upload(self.day, F.build_pdf(pages), 'f.pdf', self.owner)
        importer.confirm(part, replace=replace)
        return part

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self.settings_obj, k, v)
        self.settings_obj.save()

    def generate(self, mode='keep'):
        return planning.generate(self.day, self.owner, mode=mode)

    def cards(self):
        return checks.day_cards(self.day)

    def post(self, card, action='check', note='', day=None, user=None):
        if user is not None:
            self.use(user)
        return self.client.post(reverse('planner:mic_plan_review_check', args=[(day or self.day).pk]),
                                {'fp': card['fp'], 'action': action, 'note': note})

    def page(self):
        return self.client.get(reverse('planner:mic_plan'), {'day': self.day.pk,
                                                             'part': self.parts()[0].pk})

    def check_all(self):
        for c in self.cards():
            checks.set_check(self.day, c, 'ok', self.editor)

    def kinds(self, cards):
        return sorted({c['kind'] for c in cards})


class RegenerateKeepsChecksTests(CheckBase):
    """The property Charlie asked for: on each fixture day, check every card,
    Re-generate with no data change, and every card is still checked. A kind
    that fails gets its fingerprint fixed, not this test."""

    def assert_regenerate_keeps(self, mode='keep'):
        self.generate()
        cards = self.cards()
        self.assertTrue(cards, 'the fixture day should have Review cards')
        self.check_all()
        for _ in range(2):
            self.generate(mode)
            after = self.cards()
            self.assertEqual(self.kinds(cards), self.kinds(after))
            self.assertEqual([], [(c['kind'], c['text']) for c in checks.unchecked(after)])
        self.assertEqual(len({c['fp'] for c in cards}), MicPlanReviewCheck.objects.filter(day=self.day).count())
        return cards

    def test_cued_day(self):
        self.assert_regenerate_keeps()

    def test_cued_day_start_over(self):
        self.assert_regenerate_keeps(mode='over')

    def test_cue_free_day(self):
        ShowflowImport.objects.filter(day=self.day).delete()
        self.load(F.CUE_FREE_PAGES)
        self.set(wireless_channels=2, handheld_channels=0, spare_handhelds=0)     # cards to check
        self.assert_regenerate_keeps()

    def test_client_e_day(self):
        ShowflowImport.objects.filter(day=self.day).delete()
        self.load(F.CLIENT_E_PAGES)
        self.set(wireless_channels=14, handheld_channels=3, spare_handhelds=1)
        self.assert_regenerate_keeps()

    def test_showflow_numbers_compare(self):
        ShowflowImport.objects.filter(day=self.day).delete()
        self.load(F.MIC_NUMBER_PAGES)
        cards = self.assert_regenerate_keeps()
        self.assertIn(planning.SHOWFLOW_CARD, self.kinds(cards))

    def test_showflow_numbers_follow_client_f(self):
        ShowflowImport.objects.filter(day=self.day).delete()
        self.load(F.CLIENT_F_PAGES)
        self.set(showflow_numbers='follow')
        self.assert_regenerate_keeps()

    def test_slow_a2_late_and_spill(self):
        self.set(mic_min=8, demic_min=6, margin_min=10, premic_lead_min=5, a2_count=1)
        cards = self.assert_regenerate_keeps()
        self.assertIn('late', self.kinds(cards))

    def test_client_e_slow_a2(self):
        ShowflowImport.objects.filter(day=self.day).delete()
        self.load(F.CLIENT_E_PAGES)
        self.set(mic_min=8, demic_min=6, margin_min=10, premic_lead_min=5, a2_count=1)
        self.assert_regenerate_keeps()

    def test_rig_with_over(self):
        self.set(wireless_channels=2, handheld_channels=0, spare_handhelds=0)
        cards = self.assert_regenerate_keeps()
        self.assertTrue(push.short_of_rig(MicPlan.objects.get(day=self.day)))
        self.assertTrue([c for c in cards if c['blocks']])


class CheckViewTests(CheckBase):

    def setUp(self):
        super().setUp()
        self.set(wireless_channels=2, handheld_channels=0, spare_handhelds=0)     # OVER: blockers
        self.generate()

    def test_check_note_and_uncheck(self):
        card = self.cards()[0]
        resp = self.post(card, note='  Spoke to   the stage manager ')
        self.assertEqual(302, resp.status_code)
        self.assertTrue(resp['Location'].endswith('#review'))
        check = MicPlanReviewCheck.objects.get(day=self.day, fingerprint=card['fp'])
        self.assertEqual(('Spoke to the stage manager', 'mp_editor', card['kind']),
                         (check.note, check.checked_by_name, check.kind))
        self.post(card, action='note', note='Agreed with the A2')
        check.refresh_from_db()
        self.assertEqual(('Agreed with the A2', 'mp_editor'), (check.note, check.checked_by_name))
        self.post(card, action='uncheck')
        self.assertFalse(MicPlanReviewCheck.objects.filter(day=self.day).exists())

    def test_note_is_one_line_and_capped(self):
        card = self.cards()[0]
        self.post(card, note='a\nb ' + 'x' * 400)
        note = MicPlanReviewCheck.objects.get(day=self.day).note
        self.assertEqual(checks.NOTE_MAX, len(note))
        self.assertTrue(note.startswith('a b x'))

    def test_unknown_card_is_refused(self):
        resp = self.post({'fp': 'f' * 40})
        self.assertEqual(302, resp.status_code)
        self.assertFalse(MicPlanReviewCheck.objects.exists())

    def test_viewer_403(self):
        card = self.cards()[0]
        self.assertEqual(403, self.post(card, user=self.viewer).status_code)
        self.assertFalse(MicPlanReviewCheck.objects.exists())

    def test_another_project_404(self):
        card = self.cards()[0]
        self.assertEqual(404, self.post(card, day=self.other_day).status_code)
        self.use(self.other_owner)
        self.assertEqual(404, self.post(card).status_code)
        self.assertFalse(MicPlanReviewCheck.objects.exists())

    def test_counts_on_tab_tile_and_dashboard(self):
        cards = self.cards()
        total = len(cards)
        self.assertGreater(total, 2)
        for c in cards[:2]:
            self.post(c)
        open_n = total - 2
        html = self.page().content.decode()
        self.assertIn('Review ({} of {})'.format(open_n, total), html)
        tile = re.search(r'<b>(\d+)</b><span>To review</span>', html)
        self.assertEqual(str(open_n), tile.group(1))
        self.assertIn('Checked (2)', html)
        stats = self.client.get(reverse('planner:dashboard_stats')).json()
        mine = next(d for d in stats['mic_planner'] if d['day'] == self.day.pk)
        self.assertEqual(open_n, mine['review'])

    def test_viewer_sees_checks_without_controls(self):
        card = self.cards()[0]
        self.post(card, note='Looked at it')
        self.use(self.viewer)
        html = self.page().content.decode()
        self.assertIn('Checked by mp_editor', html)
        self.assertIn('Looked at it', html)
        self.assertNotIn(reverse('planner:mic_plan_review_check', args=[self.day.pk]), html)

    def test_blocker_still_blocks_send_when_checked(self):
        blockers = checks.blocking(self.cards())
        self.assertTrue(blockers)
        for c in blockers:
            self.post(c, note='Known')
        self.assertTrue(push.short_of_rig(MicPlan.objects.get(day=self.day)))
        resp = self.client.get(reverse('planner:mic_plan_push', args=[self.day.pk]))
        html = resp.content.decode()
        self.assertIn('id="mp-short"', html)
        self.assertIn('Blocking cards', html)
        self.assertIn('(checked by mp_editor)', html)
        self.assertNotIn('>Send to Mic Tracker</button>', html)
        page = self.page().content.decode()
        self.assertIn('Still blocks Send to Mic Tracker', page)

    def test_checked_conflict_is_still_refused_and_listed(self):
        plan = MicPlan.objects.get(day=self.day)
        plan.flags = plan.flags + [{'kind': 'conflict', 'row': None, 'person': None, 'rf': 1,
                                    'text': 'RF 1 is worn by two people at 9:05.'}]
        plan.save(update_fields=['flags'])
        card = next(c for c in self.cards() if c['kind'] == 'conflict')
        self.assertTrue(card['blocks'])
        self.post(card)
        with self.assertRaisesMessage(push.PushRefused, 'RF conflict'):
            push.preview(self.day)
        html = self.client.get(reverse('planner:mic_plan_push', args=[self.day.pk])).content.decode()
        self.assertIn('id="mp-refused"', html)
        self.assertIn('RF 1 is worn by two people', html)
        self.assertIn('(checked by mp_editor)', html)

    def test_pdf_lists_unchecked_then_checked_with_note(self):
        cards = self.cards()
        self.post(cards[0], note='Cleared with the producer')
        resp = self.client.get(reverse('planner:mic_plan_pdf', args=[self.day.pk]))
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
        review = text[text.rindex('Review'):]
        self.assertIn('Checked (1)', review)
        self.assertIn('mp_editor', review)
        self.assertIn('Cleared with the producer', review)
        self.assertLess(review.index('Flag'), review.index('Checked (1)'))


class SurvivalTests(CheckBase):

    def setUp(self):
        super().setUp()
        self.generate()

    def test_survives_reread(self):
        self.check_all()
        n = MicPlanReviewCheck.objects.count()
        importer.reread(self.parts()[0])
        self.assertEqual(n, MicPlanReviewCheck.objects.count())       # stale plan: nothing pruned
        self.generate()
        self.assertEqual([], checks.unchecked(self.cards()))

    def test_survives_replace_with_the_same_file(self):
        self.check_all()
        before = {c['fp'] for c in self.cards()}
        self.load(F.MAIN_PAGES, replace=self.parts()[0])
        self.assertEqual(len(before), MicPlanReviewCheck.objects.count())
        self.generate()
        after = self.cards()
        self.assertEqual(before, {c['fp'] for c in after})
        self.assertEqual([], checks.unchecked(after))

    def test_reappears_when_its_numbers_change_and_the_stale_check_goes(self):
        self.set(wireless_channels=3, handheld_channels=0, spare_handhelds=0)
        self.generate()
        short = [c for c in self.cards() if c['kind'] == 'shortage']
        self.assertTrue(short)
        self.check_all()
        self.set(wireless_channels=2)
        self.generate()
        now = [c for c in self.cards() if c['kind'] == 'shortage']
        self.assertTrue([c for c in now if c['check'] is None])
        live = {c['fp'] for c in self.cards()}
        self.assertFalse(MicPlanReviewCheck.objects.exclude(fingerprint__in=live).exists())

    def test_a_new_card_shows_unchecked(self):
        self.check_all()
        plan = MicPlan.objects.get(day=self.day)
        plan.flags = plan.flags + [{'kind': 'spill', 'row': None, 'person': None, 'text': 'Busy 6 min after.'}]
        plan.save(update_fields=['flags'])
        self.assertEqual(['spill'], [c['kind'] for c in checks.unchecked(self.cards())])
