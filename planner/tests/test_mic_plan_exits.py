"""Mic Plan PR 5.2: cue-free off times from exit lines, and people added by
hand (from a "not listed" line, or People's Add person). Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_exits --settings=audiopatch.test_settings
"""

from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import parser, planning, solver
from planner.mic_plan.extract import extract
from planner.models import MicPlan, Presenter, ShowflowImport, ShowflowPerson, ShowflowRow
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase


class DescriptionCandidateTests(SimpleTestCase):

    def test_names_after_the_intro_split_with_suffixes_kept(self):
        self.assertEqual(['Cy Dorn', 'Eli Fay', 'Hal Grey'], parser.description_candidates(
            'Amy introduces the 3 presenters. Cy Dorn, Eli Fay, Hal Grey'))
        self.assertEqual(['Lu Barr', 'Jo Hu, MD', 'Qi Xu'], parser.description_candidates(
            'Amy enters and introduces the 3 presenters. Lu Barr, Jo Hu, MD, Qi Xu'))
        self.assertEqual(['Dr. Ann Lee, MD', 'Bo Park', 'Cy Dorn, PhD'], parser.description_candidates(
            'Please welcome Dr. Ann Lee, MD, Bo Park and Cy Dorn, PhD.'))

    def test_a_label_before_a_dash_is_dropped(self):
        self.assertEqual(['Nia Bell', 'Gus Hale'], parser.description_candidates(
            "VOG: Now, please give a big welcome to your MC'S - Nia Bell & Gus Hale"))

    def test_titles_companies_and_lone_first_names_are_not_offered(self):
        self.assertEqual([], parser.description_candidates('Ned welcomes Bo and Zed to stage'))
        self.assertEqual(['Ann Lee'], parser.description_candidates(
            'Please welcome Vice President, Acme Consulting, Ann Lee'))


class GroupExitTests(SimpleTestCase):

    def test_group_words(self):
        self.assertEqual(('all', []), parser.group_exit('Presenters Exit'))
        self.assertEqual(('all', ['kit']), parser.group_exit('Panel Exits (Kit Stays)'))
        self.assertEqual(('all', ['kit', 'ames']), parser.group_exit('Panelists exit (Kit Ames stays)'))
        self.assertEqual(('both', []), parser.group_exit('Bo thanks Zed; both exit'))
        self.assertIsNone(parser.group_exit('Max Exits'))
        self.assertIsNone(parser.group_exit('Enter: BSL Exit: BSR'))          # a stage note


class FixtureExitTests(MicPlanBase):
    """The Client E fixture, cue-free, with exit lines as Client E writes them."""

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload('CLIENT_E_PAGES')
        self.part = ShowflowImport.objects.get(day=self.day)

    def lines(self, name, kind):
        rows = {r.order: r.line_no for r in self.part.rows.all()}
        return [rows[o] for o in self.person(name).flags.get(kind, {}).get(str(self.part.pk), [])]

    def apps(self):
        data, _, _ = planning.build_day(self.day)
        plan = solver.solve(data, solver.Settings())
        ix = solver._Index(data)
        names = {p.key: p.name for p in data.people}
        out = {}
        for a in plan.appearances:
            out.setdefault(names[a.person], []).append((solver.hm(a.on), solver.hm(a.off), ix.line(a.off_row)))
        return out, plan

    def test_exit_and_re_entry_lines_are_read(self):
        self.assertEqual(['304', '308'], self.lines('Max Pine', 'exits'))      # "Ned welcomes Vic ... Max exits"
        self.assertEqual(['306'], self.lines('Max Pine', 'enters'))             # "Max re-enters with Dr. ..."
        self.assertEqual(['307'], self.lines('Ola Brand', 'exits'))            # "Ola exits when ..."
        self.assertEqual(['308'], self.lines('Dr. Una Reyes', 'exits'))        # "Max and Dr. Reyes Exit"
        self.assertEqual(['309'], self.lines('Gil Ware', 'exits'))
        self.assertEqual(['310'], self.lines('Ned Quill', 'exits'))            # on another person's walk-on row

    def test_the_opening_session_keeps_its_exits(self):
        apps, _ = self.apps()
        self.assertEqual([('8:04a', '8:15a', '304'), ('8:22a', '8:30a', '308')], apps['Max Pine'])
        self.assertEqual([('8:08a', '8:26a', '307')], apps['Ola Brand'])
        self.assertEqual([('8:11a', '8:38a', '310')], apps['Ned Quill'])
        self.assertEqual([('8:30a', '8:34a', '309')], apps['Gil Ware'])
        # Named once, no exit line: on to the end of the segment (8:45).
        self.assertEqual([('8:38a', '8:45a', '310')], apps['Bo Lark'])

    def test_panelists_exit_ends_the_panel_except_whoever_stays(self):
        apps, plan = self.apps()
        for name in ('Dr. Lou Penn', 'Dr. Sol Tate', 'Ann Pike', 'Vic Dahl'):
            self.assertEqual('320', apps[name][-1][2], name)
        self.assertEqual('315', apps['Kit Ames'][-1][2])                 # stays: off at the segment end
        self.assertFalse([f for f in plan.flags if f['kind'] == 'who_both'])

    def test_an_exit_naming_nobody_known_is_flagged_on_a_cue_free_part(self):
        rows, _, _, _ = extract(F.build_pdf(F.CLIENT_E_PAGES))
        rows[3]['description'] += ' Zoe Exits'
        flags = [f for f in parser.analyse(rows).flags if f[0] == 'who_exits']
        self.assertEqual(['Line 303: who exits? "Zoe" is not a person ShowStack recognised, so nobody comes '
                          'off here.'], [f[2] for f in flags])


class AddPeopleTests(MicPlanBase):

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload('CLIENT_E_PAGES')
        self.part = ShowflowImport.objects.get(day=self.day)
        self.row311 = self.part.rows.get(line_no='311')
        self.client.post(reverse('planner:mic_plan_generate', args=[self.day.pk]), {'replace': '1'})

    def add(self, names, row=None, off=None, from_flag=True, day=None):
        data = {'row': (row or self.row311).pk, 'name': names}
        if off is not None:
            data['off'] = off.pk
        if from_flag:
            data['from_flag'] = '1'
        return self.client.post(reverse('planner:mic_plan_people_add', args=[(day or self.day).pk]), data)

    def flags(self, kind):
        self.part.refresh_from_db()
        return [w for w in self.part.warnings if w['kind'] == kind]

    def page(self):
        return self.client.get(reverse('planner:mic_plan') + '?day={}'.format(self.day.pk))

    def test_the_card_offers_the_names_on_the_line(self):
        page = self.page()
        card, = [c for c in page.context['cards'] if c['kind'] == 'description_names']
        self.assertEqual(['Cy Dorn', 'Eli Fay', 'Hal Grey'], card['candidates'])
        self.assertContains(page, 'Add people from this line')
        self.assertContains(page, 'value="Eli Fay"')

    def test_adding_from_the_flag_creates_matches_links_clears_and_marks_stale(self):
        eli = Presenter.objects.create(project=self.project, name='Eli Fay')
        self.assertFalse(MicPlan.objects.get(day=self.day).stale)
        self.assertEqual(1, len(self.flags('description_names')))
        resp = self.add(['Cy Dorn', 'Eli Fay, MD', 'Ned Quill', ''])
        self.assertEqual(302, resp.status_code)
        cy = self.person('Cy Dorn')
        entry, = cy.flags['added']
        self.assertEqual(('311', None, True, self.editor.pk), (entry['line'], entry['off'], entry['from_flag'],
                                                                entry['by']))
        self.assertEqual(eli, self.person('Eli Fay, MD').presenter)        # by name, the suffix aside
        ned = self.person('Ned Quill')                                       # already on the day: matched
        self.assertEqual(1, ShowflowPerson.objects.filter(day=self.day, display_name='Ned Quill').count())
        self.assertEqual(['311'], [e['line'] for e in ned.flags['added']])
        self.assertEqual([], self.flags('description_names'))                # the flag clears
        self.assertTrue(MicPlan.objects.get(day=self.day).stale)

    def test_added_people_are_in_the_plan_on_at_the_line_off_by_the_rule(self):
        self.add(['Cy Dorn'])
        self.client.post(reverse('planner:mic_plan_generate', args=[self.day.pk]), {'replace': '1'})
        app = MicPlan.objects.get(day=self.day).appearances.get(person_name='Cy Dorn')
        self.assertEqual(('311', '311'), (app.on_line, app.off_line))       # its last line; off at the segment end
        self.assertEqual('8:45a', solver.hm(app.off_min))

    def test_added_people_survive_re_read_and_replace(self):
        self.add(['Cy Dorn'])
        self.client.post(reverse('planner:mic_plan_reread', args=[self.part.pk]))
        self.assertEqual(['311'], [e['line'] for e in self.person('Cy Dorn').flags['added']])
        self.assertEqual([], self.flags('description_names'))
        self.upload('CLIENT_E_PAGES', 'again.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': f'replace:{self.part.pk}'})
        cy = self.person('Cy Dorn')
        self.assertNotIn('added_missing', cy.flags)
        self.assertEqual([], [w for w in pending.__class__.objects.get(pk=pending.pk).warnings
                              if w['kind'] == 'description_names'])
        data, _, _ = planning.build_day(self.day)
        self.assertEqual([cy.pk], [a.person for a in data.added])

    def test_a_line_gone_after_replace_keeps_them_and_says_so(self):
        self.add(['Cy Dorn'])
        self.upload('CLIENT_E_WITHOUT_311', 'revised.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': f'replace:{self.part.pk}'})
        cy = self.person('Cy Dorn')
        self.assertEqual(['311'], cy.flags['added_missing'])
        self.assertFalse(cy.flags.get('gone'))
        page = self.page()
        self.assertContains(page, 'Line 311 no longer in this showflow: Cy Dorn was added on at it by hand.')
        self.assertEqual([], list(planning.build_day(self.day)[0].added))

    def test_add_person_with_an_off_line_then_edit_and_remove(self):
        on, off = self.part.rows.get(line_no='305'), self.part.rows.get(line_no='307')
        self.add(['Lu Barr'], row=on, off=off, from_flag=False)
        lu = self.person('Lu Barr')
        entry, = lu.flags['added']
        self.assertEqual(('305', '307', False), (entry['line'], entry['off'], entry['from_flag']))
        self.assertEqual([solver.Added(lu.pk, on.pk, off.pk)], list(planning.build_day(self.day)[0].added))
        url = reverse('planner:mic_plan_person_added', args=[lu.pk])
        later = self.part.rows.get(line_no='308')
        self.client.post(url, {'entry': entry['id'], 'row': later.pk, 'off': ''})
        lu.refresh_from_db()
        self.assertEqual(('308', None), (lu.flags['added'][0]['line'], lu.flags['added'][0]['off']))
        self.assertEqual(entry['id'], lu.flags['added'][0]['id'])
        self.client.post(url, {'entry': entry['id'], 'action': 'remove'})
        self.assertFalse(ShowflowPerson.objects.filter(pk=lu.pk).exists())  # only ever added by hand

    def test_removing_an_added_appearance_keeps_a_person_the_showflow_names(self):
        self.add(['Ned Quill'])
        ned = self.person('Ned Quill')
        self.client.post(reverse('planner:mic_plan_person_added', args=[ned.pk]),
                         {'entry': ned.flags['added'][0]['id'], 'action': 'remove'})
        ned.refresh_from_db()
        self.assertNotIn('added', ned.flags)
        self.assertTrue(ned.flags['rows'])

    def test_an_off_line_before_the_on_line_is_refused(self):
        on, off = self.part.rows.get(line_no='307'), self.part.rows.get(line_no='305')
        self.add(['Lu Barr'], row=on, off=off, from_flag=False)
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='Lu Barr').exists())

    def test_viewer_403_and_another_project_404(self):
        self.use(self.viewer)
        self.assertEqual(403, self.add(['Cy Dorn']).status_code)
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='Cy Dorn').exists())
        self.use(self.editor)
        self.add(['Lu Barr'], row=self.part.rows.get(line_no='305'), from_flag=False)
        lu = self.person('Lu Barr')
        self.use(self.viewer)
        url = reverse('planner:mic_plan_person_added', args=[lu.pk])
        self.assertEqual(403, self.client.post(url, {'entry': lu.flags['added'][0]['id'], 'action': 'remove'})
                         .status_code)
        self.use(self.other_owner, self.other)
        self.assertEqual(404, self.add(['Cy Dorn']).status_code)
        self.assertEqual(404, self.client.post(url, {'entry': lu.flags['added'][0]['id'], 'action': 'remove'})
                         .status_code)
        # A row of another project's day is not a line of this day.
        other_row = ShowflowRow.objects.filter(showflow_import__day=self.day).first()
        self.use(self.other_owner, self.other)
        resp = self.client.post(reverse('planner:mic_plan_people_add', args=[self.other_day.pk]),
                                {'row': other_row.pk, 'name': ['Cy Dorn']})
        self.assertEqual(302, resp.status_code)
        self.assertFalse(ShowflowPerson.objects.filter(display_name='Cy Dorn').exists())
