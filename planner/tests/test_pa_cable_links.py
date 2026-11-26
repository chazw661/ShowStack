"""Daisy-chain links on a PA cable run (``PACableLink``).

A run is its home run, amp to the first speaker. A linked run carries on
from speaker to speaker, each link a physical cable of its own: its own
type, length and quantity, counted by every total through
``pa_cable_math.entry_pieces``.

Two rules these tests pin:

* a link's Qty is its own, as a fan-out's is. The run's Count never
  multiplies it;
* a link is never merged into the home run's footage. A 75' home run and a
  25' link are a 100' and a 25', not one 100'.

That a run with NO links totals exactly as before is
``test_pa_cable_unlinked_totals``.

Run with::

    python manage.py test planner.tests.test_pa_cable_links \\
        --settings=audiopatch.test_settings
"""
import csv
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from planner.admin import PACableAdmin
from planner.admin_site import showstack_admin_site
from planner.connections.graph import digest, project_graph
from planner.forms import PACableLinkForm
from planner.models import PACableLink, PACableSchedule, Project, ProjectMember
from planner.tests.connection_fixtures import ConnectionFixtures
from planner.tests.test_wiring_dxf import read as read_dxf
from planner.utils import pa_cable_math
from planner.utils.pdf_exports import pa_cable_pdf, system_report
from planner.views_wiring import tab_view

CHANGELIST = 'admin:planner_pacableschedule_changelist'
ADD = 'admin:planner_pacableschedule_add'
CHANGE = 'admin:planner_pacableschedule_change'
HOSTILE = '<img src=x onerror=alert(1)> & "quoted"'


class _Linked(ConnectionFixtures):
    """One project, one run: 2 x NL 8 75' from an amp, then three links."""

    def setUp(self):
        super().setUp()
        self.user.is_superuser = self.user.is_staff = True
        self.user.save()
        self.login(self.user)
        self.amp_a = self.amp('SL LA12X #1', rack='SL Racks')
        self.run = self.text_cable(label=self.zone('HL'), destination='K2 Left',
                                   amp=self.amp_a, cable='NL_8', count=2, length=75)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def link(self, order, cable='NL_4', length=25, quantity=1, note='', run=None):
        return PACableLink.objects.create(
            cable_schedule=run or self.run, order=order, cable=cable,
            length=length, quantity=quantity, note=note)

    def chain(self):
        """25' x2, 110' x1, then three jumpers."""
        return [self.link(1, length=25, quantity=2, note='over the truss'),
                self.link(2, length=110, quantity=1),
                self.link(3, cable='NL4_JUMPER', length=None, quantity=3)]

    def queryset(self):
        return PACableSchedule.objects.filter(project=self.project)

    def summary(self):
        return self.client.get(reverse(CHANGELIST)).context

    def admin_post(self, links=(), initial=0, **data):
        out = {'source': f'amp:{self.amp_a.pk}', 'destination': 'K2 Left',
               'count': 2, 'cable': 'NL_8', 'length': 75, 'color': '#FFFFFF',
               'notes': '', 'drawing_ref': ''}
        for prefix in ('fan_outs', 'fan_out_extensions', 'couplers'):
            out.update({f'{prefix}-TOTAL_FORMS': 0, f'{prefix}-INITIAL_FORMS': 0})
        out.update({'links-TOTAL_FORMS': len(links), 'links-INITIAL_FORMS': initial})
        for i, row in enumerate(links):
            out.update({f'links-{i}-{key}': value for key, value in row.items()})
        out.update(data)
        return out


class EntryPiecesTests(_Linked, TestCase):

    def test_the_home_run_then_each_link_in_order(self):
        self.link(2, length=110)
        self.link(1, length=25, quantity=2)
        pieces = [(p.cable, p.length, p.count, p.link is not None)
                  for p in pa_cable_math.entry_pieces(self.run)]
        self.assertEqual(pieces, [('NL_8', 75, 2, False), ('NL_4', 25, 2, True),
                                  ('NL_4', 110, 1, True)])

    def test_a_run_with_no_links_is_one_piece(self):
        self.assertEqual([tuple(p) for p in pa_cable_math.entry_pieces(self.run)],
                         [('NL_8', 75, 2, None)])

    def test_an_unsaved_run_is_one_piece(self):
        row = PACableSchedule(project=self.project, cable='NL_4', count=1, length=50)
        self.assertEqual(len(list(pa_cable_math.entry_pieces(row))), 1)

    def test_how_a_link_reads(self):
        a, _, jumper = self.chain()
        self.assertEqual((a.summary, jumper.summary), ("2× NL 4 25'", '3× NL4 Jumper'))
        self.assertEqual(self.run.link_summary, "2× NL 4 25' → 1× NL 4 110' → 3× NL4 Jumper")
        self.assertEqual(self.text_cable(destination='X').link_summary, '')

    def test_renumber_makes_them_one_to_n_in_their_order(self):
        a, b, c = self.link(7), self.link(3), self.link(3)
        PACableLink.renumber(self.run)
        self.assertEqual(list(self.run.links.values_list('pk', 'order')),
                         [(b.pk, 1), (c.pk, 2), (a.pk, 3)])

    def test_deleting_the_run_deletes_its_links(self):
        self.chain()
        self.run.delete()
        self.assertFalse(PACableLink.objects.exists())


class LinkedTotalsTests(_Linked, TestCase):
    """Every total counts every link, each under its own type."""

    def test_the_changelist_summary(self):
        self.chain()
        context = self.summary()
        got = {name: {k: entry[k] for k in ('total_runs', 'total_length', 'hundreds',
                                            'fifties', 'twenty_fives', 'quantity_with_safety')}
               for name, entry in context['cable_summary'].items()}
        self.assertEqual(got, {
            # 3 jumpers, by quantity: no length, +20% on the count.
            'NL4 Jumper': {'total_runs': 3, 'total_length': 0, 'hundreds': 0, 'fifties': 0,
                           'twenty_fives': 0, 'quantity_with_safety': 4},
            # 2 x 25' and 1 x 110' (a 100' and a 25'): three cables, 160'.
            'NL 4': {'total_runs': 3, 'total_length': 160, 'hundreds': 1, 'fifties': 0,
                     'twenty_fives': 3, 'quantity_with_safety': 0},
            # The home run alone: 2 x 75' is two 100's.
            'NL 8': {'total_runs': 2, 'total_length': 150, 'hundreds': 2, 'fifties': 0,
                     'twenty_fives': 0, 'quantity_with_safety': 0},
        })
        self.assertEqual(context['grand_total'], 310)

    def test_a_link_is_never_merged_into_the_home_run(self):
        """75' + 25' of the same type is a 100' and a 25', not one 100'."""
        self.link(1, cable='NL_8', length=25, quantity=2)
        entry = self.summary()['cable_summary']['NL 8']
        self.assertEqual((entry['hundreds'], entry['twenty_fives'], entry['total_runs'],
                          entry['total_length']), (2, 2, 4, 200))

    def test_count_does_not_multiply_a_link(self):
        """A link's Qty is its own, as a fan-out's is."""
        self.chain()
        before = dict(self.summary()['cable_summary']['NL 4'])
        PACableSchedule.objects.filter(pk=self.run.pk).update(count=9)
        self.assertEqual(self.summary()['cable_summary']['NL 4'], before)
        self.assertEqual(self.summary()['cable_summary']['NL 8']['total_runs'], 9)

    def test_the_quick_order_list(self):
        self.chain()
        self.assertEqual(pa_cable_pdf._quick_order_rows(self.queryset()), [
            ['NL4 Jumper', '—', '4'],
            ['NL 4', "100'", '2'],
            ['NL 4', "25'", '4'],
            ['NL 8', "100'", '3'],
        ])

    def test_the_quick_order_list_and_the_summary_agree(self):
        self.chain()
        summary = self.summary()['cable_summary']
        on_screen = {(name, stock): entry[key + '_with_safety']
                     for name, entry in summary.items() if not entry['is_jumper']
                     for stock, key in ((100, 'hundreds'), (50, 'fifties'), (25, 'twenty_fives'))
                     if entry[key]}
        on_screen[('NL4 Jumper', None)] = summary['NL4 Jumper']['quantity_with_safety']
        in_pdf = {(name, int(length[:-1]) if length != '—' else None): int(qty)
                  for name, length, qty in pa_cable_pdf._quick_order_rows(self.queryset())}
        self.assertEqual(in_pdf, on_screen)

    def csv_rows(self):
        admin_obj = PACableAdmin(PACableSchedule, showstack_admin_site)
        request = self.client.get(reverse(CHANGELIST)).wsgi_request
        response = admin_obj.export_cable_schedule(request, self.queryset())
        return list(csv.reader(io.StringIO(response.content.decode('utf-8'))))

    def test_the_csv_lists_each_link_under_its_run_and_totals_it(self):
        self.chain()
        rows = self.csv_rows()
        at = rows.index(['HL', 'SL LA12X #1', 'K2 Left', '2', 'NL 8', '', '', ''])
        self.assertEqual(rows[at + 1:at + 4], [
            ['', '', "— Link 1 · 25'", '2', 'NL 4', '', 'over the truss', ''],
            ['', '', "— Link 2 · 110'", '1', 'NL 4', '', '', ''],
            ['', '', '— Link 3', '3', 'NL4 Jumper', '', '', ''],
        ])
        totals = {row[0]: row[1:3] for row in rows if len(row) == 9}
        self.assertEqual(totals['NL 8'], ['2', '150.0'])
        self.assertEqual(totals['NL 4'], ['3', '160.0'])
        self.assertEqual(totals['NL4 Jumper'], ['3', '0.0'])
        self.assertEqual(totals['GRAND TOTAL'], ['8', '310.0'])

    def test_the_system_report_lists_each_link_under_its_run(self):
        self.chain()
        with mock.patch.object(system_report, '_data_table') as table:
            system_report._section_pa_cable(self.project, system_report._styles(),
                                            PACableSchedule)
        _headers, rows, _widths = table.call_args[0]
        self.assertEqual(rows, [
            ['HL', 'SL LA12X #1', 'K2 Left', 'NL 8', '75', '2', '-'],
            ['', '', '— Link 1 (over the truss)', 'NL 4', '25', '2', '-'],
            ['', '', '— Link 2', 'NL 4', '110', '1', '-'],
            ['', '', '— Link 3', 'NL4 Jumper', '', '3', '-'],
        ])

    def test_the_pa_cable_pdf_lists_each_link_under_its_run(self):
        self.chain()
        S = pa_cable_pdf.kit.styles()
        rows = [[getattr(cell, 'text', cell) for cell in row]
                for row in pa_cable_pdf._cable_rows(self.queryset(), S)]
        self.assertEqual([row[2:6] + [row[7]] for row in rows[1:]], [
            ['— Link 1', '2', "25'", 'NL 4', 'over the truss'],
            ['— Link 2', '1', "110'", 'NL 4', '-'],
            ['— Link 3', '3', '-', 'NL4 Jumper', '-'],
        ])

    def test_markup_in_a_note_is_escaped_in_the_pdfs(self):
        self.link(1, note=HOSTILE)
        S = pa_cable_pdf.kit.styles()
        note = pa_cable_pdf._cable_rows(self.queryset(), S)[1][7].text
        self.assertIn('&lt;img', note)
        self.assertNotIn('<img', note)
        self.assertTrue(pa_cable_pdf.generate_pa_cable_pdf(self.queryset()).startswith(b'%PDF-'))


class LinkFormTests(_Linked, TestCase):

    def form(self, **data):
        base = {'order': 1, 'quantity': 1, 'cable': 'NL_4', 'length': 25, 'note': ''}
        base.update(data)
        return PACableLinkForm(data=base)

    def test_a_cable_link_needs_a_length(self):
        form = self.form(length='')
        self.assertFalse(form.is_valid())
        self.assertIn('length', form.errors)

    def test_a_jumper_link_has_none_and_stores_none(self):
        form = self.form(cable='NL4_JUMPER', length='')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['length'])
        # A length typed before the type was switched is not kept either.
        form = self.form(cable='NL4_JUMPER', length=40)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['length'])

    def test_a_quantity_or_length_of_zero_is_refused(self):
        self.assertIn('quantity', self.form(quantity=0).errors)
        self.assertIn('length', self.form(length=0).errors)

    def test_the_select_tells_the_script_which_types_are_jumpers(self):
        self.assertIn('data-jumper-values', str(self.form()['cable']))
        self.assertIn('NL4_JUMPER', str(self.form()['cable']))


class LinkAdminTests(_Linked, TestCase):

    def test_the_form_has_the_toggle_the_links_inline_and_its_script(self):
        body = self.client.get(reverse(CHANGE, args=[self.run.pk])).content.decode()
        self.assertIn('id="pa-linked-toggle"', body)
        self.assertIn('id="links-group"', body)
        self.assertIn('pa_cable_links', body)
        self.assertIn('name="links-TOTAL_FORMS"', body)
        # No blank row is offered: the toggle adds the first.
        self.assertIn('name="links-TOTAL_FORMS" value="0"', body)
        self.assertIn('id="pa-linked-toggle"', self.client.get(reverse(ADD)).content.decode())

    def test_adding_a_linked_run(self):
        self.run.delete()
        response = self.client.post(reverse(ADD), self.admin_post(links=[
            {'order': 1, 'quantity': 2, 'cable': 'NL_4', 'length': 25, 'note': 'over the truss'},
            {'order': 2, 'quantity': 2, 'cable': 'NL4_JUMPER', 'length': '', 'note': ''},
        ]))
        self.assertEqual(response.status_code, 302)
        run = PACableSchedule.objects.get(project=self.project)
        self.assertEqual(
            list(run.links.values_list('order', 'quantity', 'cable', 'length', 'note')),
            [(1, 2, 'NL_4', 25, 'over the truss'), (2, 2, 'NL4_JUMPER', None, '')])

    def test_the_posted_order_is_kept_and_renumbered(self):
        a, b = self.link(1, length=25), self.link(2, length=50)
        self.client.post(reverse(CHANGE, args=[self.run.pk]), self.admin_post(initial=2, links=[
            {'id': a.pk, 'cable_schedule': self.run.pk, 'order': 5, 'quantity': 1,
             'cable': 'NL_4', 'length': 25, 'note': ''},
            {'id': b.pk, 'cable_schedule': self.run.pk, 'order': 2, 'quantity': 1,
             'cable': 'NL_4', 'length': 50, 'note': ''},
            {'cable_schedule': self.run.pk, 'order': 9, 'quantity': 1,
             'cable': 'NL_4', 'length': 10, 'note': ''},
        ]))
        self.assertEqual(list(self.run.links.values_list('length', 'order')),
                         [(50, 1), (25, 2), (10, 3)])

    def test_a_link_with_no_length_is_sent_back(self):
        response = self.client.post(reverse(CHANGE, args=[self.run.pk]), self.admin_post(links=[
            {'cable_schedule': self.run.pk, 'order': 1, 'quantity': 1, 'cable': 'NL_4',
             'length': '', 'note': ''}]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter this link&#x27;s length, or choose a Jumper type.')
        self.assertFalse(self.run.links.exists())

    def test_turning_linked_off_deletes_the_links_on_save(self):
        """What the toggle posts when it is switched off: every row marked."""
        a, b = self.link(1), self.link(2)
        self.client.post(reverse(CHANGE, args=[self.run.pk]), self.admin_post(initial=2, links=[
            {'id': link.pk, 'cable_schedule': self.run.pk, 'order': link.order, 'quantity': 1,
             'cable': 'NL_4', 'length': 25, 'note': '', 'DELETE': 'on'} for link in (a, b)]))
        self.assertFalse(self.run.links.exists())
        self.assertTrue(PACableSchedule.objects.filter(pk=self.run.pk).exists())

    def test_the_changelist_shows_the_chain_as_chips_in_order(self):
        self.chain()
        body = self.client.get(reverse(CHANGELIST)).content.decode()
        chips = ['<span class="cb-chip cb-link">%s</span>' % text for text in
                 ('2× NL 4 25&#x27;', '1× NL 4 110&#x27;', '3× NL4 Jumper')]
        self.assertIn(''.join(chips), body)
        self.assertIn('>Links<', body.replace('</a>', '<'))

    def test_the_changelist_query_count_does_not_grow_with_links(self):
        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(reverse(CHANGELIST)).status_code, 200)
            return len(ctx)

        self.chain()
        few = count_queries()
        for n in range(6):
            run = self.text_cable(destination=f'Fill {n}', amp=self.amp_a)
            for order in (1, 2, 3):
                self.link(order, run=run)
        self.assertEqual(count_queries(), few)

    def test_duplicate_copies_the_links(self):
        self.chain()
        self.client.post(reverse(CHANGELIST), {'action': 'duplicate_cable_runs',
                                               '_selected_action': [self.run.pk]})
        copy = PACableSchedule.objects.exclude(pk=self.run.pk).get(project=self.project)
        fields = ('order', 'quantity', 'cable', 'length', 'note')
        self.assertEqual(list(copy.links.values_list(*fields)),
                         list(self.run.links.values_list(*fields)))
        self.assertEqual(self.run.links.count(), 3)

    def test_duplicating_the_project_copies_the_links(self):
        self.chain()
        copy = self.project.duplicate('Copy')
        run = PACableSchedule.objects.get(project=copy)
        self.assertEqual(run.link_summary, self.run.link_summary)
        self.assertEqual(self.run.links.count(), 3)

    def test_a_viewer_reads_the_links_and_cannot_change_them(self):
        link = self.link(1, note='over the truss')
        viewer = get_user_model().objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.login(viewer)
        url = reverse(CHANGE, args=[self.run.pk])
        body = self.client.get(url).content.decode()
        self.assertIn('over the truss', body)
        self.assertNotIn('name="links-0-note"', body)
        self.client.post(url, self.admin_post(initial=1, links=[
            {'id': link.pk, 'cable_schedule': self.run.pk, 'order': 1, 'quantity': 7,
             'cable': 'NL_4', 'length': 99, 'note': 'changed', 'DELETE': 'on'}]))
        link.refresh_from_db()
        self.assertEqual((link.quantity, link.length, link.note), (1, 25, 'over the truss'))

    def test_an_editor_can_add_a_link(self):
        editor = get_user_model().objects.create_user('ed', password='pw', is_staff=True)
        ProjectMember.objects.create(user=editor, project=self.project, role='editor',
                                     invited_by=self.user)
        self.login(editor)
        response = self.client.post(reverse(CHANGE, args=[self.run.pk]), self.admin_post(links=[
            {'cable_schedule': self.run.pk, 'order': 1, 'quantity': 2, 'cable': 'NL_4',
             'length': 25, 'note': ''}]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.run.links.count(), 1)

    def test_another_projects_run_cannot_be_given_a_link(self):
        """The inline hangs off the run in the URL, and that run is not yours."""
        other = get_user_model().objects.create_user('other', password='pw', is_staff=True)
        theirs = Project.objects.create(name='Theirs', owner=other)
        self.client.force_login(other)
        session = self.client.session
        session['current_project_id'] = theirs.pk
        session.save()
        self.client.post(reverse(CHANGE, args=[self.run.pk]), self.admin_post(links=[
            {'cable_schedule': self.run.pk, 'order': 1, 'quantity': 1, 'cable': 'NL_4',
             'length': 25, 'note': 'not mine'}]))
        self.assertFalse(PACableLink.objects.exists())


class LinkedWiringTests(_Linked, TestCase):
    """The Speaker cables tab, its Connections table, the PDF and the DXF all
    print one label, ``graph._pa_cable_label``."""

    LABEL = "HL · 2× NL 8 75' → 2× NL 4 25' (over the truss) → 1× NL 4 110' → 3× NL4 Jumper"

    def pa_edge(self, graph=None):
        graph = graph or project_graph(self.project)
        [edge] = [e for e in graph['edges'] if 'speaker' in e.get('transports', ())]
        return edge

    def test_the_label_carries_the_chain_and_each_note(self):
        self.chain()
        self.assertEqual(self.pa_edge()['label'], self.LABEL)

    def test_the_cable_lists_its_links(self):
        self.chain()
        cable = self.pa_edge()['cable']
        self.assertEqual((cable['type'], cable['length_ft'], cable['count']), ('NL 8', 75, 2))
        self.assertEqual(cable['links'], [
            {'type': 'NL 4', 'length_ft': 25, 'count': 2, 'note': 'over the truss'},
            {'type': 'NL 4', 'length_ft': 110, 'count': 1, 'note': ''},
            {'type': 'NL4 Jumper', 'length_ft': None, 'count': 3, 'note': ''},
        ])

    def test_a_run_with_no_links_is_as_it_was(self):
        edge = self.pa_edge()
        self.assertEqual(edge['label'], "HL · 2× NL 8 75'")
        self.assertNotIn('links', edge['cable'])
        before = digest(project_graph(self.project))
        self.link(1)
        self.assertNotEqual(digest(project_graph(self.project)), before)

    def view(self):
        return tab_view(self.project, project_graph(self.project), 'speakers', True)

    def test_a_chain_that_fits_is_written_on_the_line(self):
        self.chain()
        self.assertEqual(self.view()['connections'], [])
        body = self.client.get(reverse('planner:wiring_diagram'),
                               {'view': 'speakers'}).content.decode()
        self.assertIn('3× NL4 Jumper', body)
        self.assertIn('(over the truss)', body)

    def test_a_chain_too_long_for_the_line_is_keyed_and_in_the_table_in_full(self):
        """The layout's existing rule: a label wider than the tab allows is
        drawn as a key, and the Connections table says it in full."""
        self.chain()
        for order in range(4, 10):
            self.link(order, length=25, note='to the next delay tower')
        [row] = self.view()['connections']
        self.assertTrue(row['cable'].startswith(self.LABEL + " → 1× NL 4 25' (to the next"))
        self.assertEqual(row['cable'].count('→'), 9)

    def test_the_speaker_cables_tab_renders_with_a_hostile_note(self):
        self.link(1, note=HOSTILE)
        response = self.client.get(reverse('planner:wiring_diagram'), {'view': 'speakers'})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn('<img src=x', body)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', body)

    def test_the_wiring_pdf_builds_with_a_hostile_note(self):
        self.chain()
        self.link(4, note=HOSTILE)
        response = self.client.get(reverse('planner:wiring_diagram_pdf'), {'tabs': 'speakers'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF-'))

    def test_the_dxf_writes_the_chain_with_ascii_arrows_on_request(self):
        self.chain()
        url = reverse('planner:wiring_diagram_dxf')
        response = self.client.get(url, {'tabs': 'speakers', 'arrows': 'ascii'})
        self.assertEqual(response.status_code, 200)
        doc = read_dxf(response.content)
        text = ' '.join(e.dxf.text for e in doc.modelspace() if e.dxftype() == 'TEXT')
        self.assertIn("NL 8 75' -> 2", text)
        self.assertIn('(over the truss)', text)
        self.assertNotIn('→', text)
