"""The console PDF: page order, Patch column, Source Hardware, unused rows.

Under test: planner/utils/pdf_exports/console_pdf.py (console_sections is
what gets printed) and planner/utils/console_order.py, the order it shares
with the Console page.

Run with::

    python manage.py test planner.tests.test_console_pdf \\
        --settings=audiopatch.test_settings
"""

import random
import re
from html.parser import HTMLParser
from io import BytesIO

from django.urls import reverse
from PyPDF2 import PdfReader

from planner.models import (
    ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput, ConsoleStereoOutput,
)
from planner.tests.test_console_patch import PatchBase
from planner.utils.pdf_exports.console_pdf import console_sections

ST_LABELS = ['ST 7', 'ST6', 'ST 1']


class _PageRows(HTMLParser):
    """Each channel row on the Console page, in page order, with its Patch
    cell read back as text the way feed_label writes it.

    rows: [(inline prefix, number or name, [feed text, ...])]
    """

    KEY = re.compile(r'^(consoleinput_set|consoleauxoutput_set|consolematrixoutput_set|'
                     r'consolestereooutput_set)-\d+-(input_ch|aux_number|matrix_number|name)$')
    PARTS = ('ss-patch-tag-b', 'ss-patch-dev', 'ss-patch-port', 'ss-patch-caption')

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cur, self.stack = [], None, None, []
        self.reading = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.row = None
        m = self.KEY.match(attrs.get('name') or '')
        if tag == 'input' and m and (self.row is None or not self.row[1]):
            if self.row is not None:
                self.rows.pop()
            self.row = (m.group(1), attrs.get('value') or '', [])
            self.rows.append(self.row)
        # A viewer's inline is read-only: the number is the cell's text.
        if tag == 'td' and 'field-input_ch' in (attrs.get('class') or '') and self.row is None:
            self.row = ('consoleinput_set', '', [])
            self.rows.append(self.row)
            self.reading = True
        if tag != 'span':
            return
        classes = (attrs.get('class') or '').split()
        if 'ss-patch-feed' in classes:
            self.cur = {'conflict': 'ss-patch-conflict' in classes}
            self.stack = []
        if self.cur is not None:
            self.stack.append(next((c for c in classes if c in self.PARTS), None))

    def handle_endtag(self, tag):
        if tag == 'td':
            self.reading = False
        if tag != 'span' or self.cur is None:
            return
        self.stack.pop()
        if not self.stack:
            f, self.cur = self.cur, None
            text = f.get('ss-patch-dev', '') + f.get('ss-patch-port', '')
            if 'ss-patch-tag-b' in f:
                text = 'B: ' + text
            if f.get('ss-patch-caption'):
                text += ' — ' + f['ss-patch-caption']
            if f['conflict']:
                text += ' — CONFLICT'
            self.row[2].append(text)

    def handle_data(self, data):
        if self.reading and data.strip():
            p, key, feeds = self.rows[-1]
            self.row = self.rows[-1] = (p, key + data.strip(), feeds)
        if self.cur is not None:
            part = next((p for p in reversed(self.stack) if p), None)
            if part:
                self.cur[part] = self.cur.get(part, '') + data


class ConsolePdfBase(PatchBase):

    def sections(self, console=None):
        return {s['title']: s for s in console_sections(console or self.foh)}

    def column(self, title, header, console=None):
        s = self.sections(console)[title]
        i = s['headers'].index(header)
        return [row[i] for row in s['rows']]

    def page_rows(self, console=None):
        url = reverse('admin:planner_console_change', args=[(console or self.foh).pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        parser = _PageRows()
        parser.feed(response.content.decode())
        return parser.rows


class OrderTests(ConsolePdfBase):

    def setUp(self):
        super().setUp()
        numbers = [str(n) for n in range(1, 145)] + ST_LABELS
        random.Random(7).shuffle(numbers)
        # Dante # as text too, so sorting on it would give 1, 10, 100 ...
        ConsoleInput.objects.bulk_create(
            ConsoleInput(console=self.foh, input_ch=n, dante_number=n[:3], source=f'Src {n}')
            for n in numbers)
        auxes = [str(n) for n in range(1, 25)]
        random.Random(8).shuffle(auxes)
        ConsoleAuxOutput.objects.bulk_create(
            ConsoleAuxOutput(console=self.foh, aux_number=n, name=f'Aux {n}') for n in auxes)
        ConsoleMatrixOutput.objects.bulk_create(
            ConsoleMatrixOutput(console=self.foh, matrix_number=n, name=f'Mtx {n}')
            for n in reversed([str(n) for n in range(1, 13)]))
        for t in ('R', 'M', 'L'):
            ConsoleStereoOutput.objects.create(console=self.foh, stereo_type=t, name=f'St {t}')

    def test_inputs_1_to_144_as_numbers_then_labels(self):
        order = self.column('Console Inputs', 'Input Ch')
        self.assertEqual(order[:144], [str(n) for n in range(1, 145)])
        self.assertEqual(sorted(order[144:]), sorted(ST_LABELS))

    def test_order_is_the_console_pages(self):
        page = self.page_rows()
        for prefix, title, header in (
                ('consoleinput_set', 'Console Inputs', 'Input Ch'),
                ('consoleauxoutput_set', 'Aux Outputs', 'Aux'),
                ('consolematrixoutput_set', 'Matrix Outputs', 'Matrix'),
                ('consolestereooutput_set', 'Stereo Outputs', 'Name')):
            on_page = [key for p, key, _ in page if p == prefix and key]
            self.assertEqual(self.column(title, header), on_page, title)
        # ... which puts the labels after 144, in a fixed order.
        self.assertEqual([k for p, k, _ in page if p == 'consoleinput_set'][143], '144')

    def test_aux_and_matrix_sort_as_numbers(self):
        self.assertEqual(self.column('Aux Outputs', 'Aux'), [str(n) for n in range(1, 25)])
        self.assertEqual(self.column('Matrix Outputs', 'Matrix'),
                         [str(n) for n in range(1, 13)])

    def test_a_non_numeric_bus_number_follows_the_numbers(self):
        # The page used to cast aux numbers outright: "A1" sorted as 0 on
        # SQLite and was a DataError on Postgres.
        ConsoleAuxOutput.objects.create(console=self.foh, aux_number='A1', name='Odd')
        self.assertEqual(self.column('Aux Outputs', 'Aux')[-1], 'A1')
        self.assertEqual([k for p, k, _ in self.page_rows()
                          if p == 'consoleauxoutput_set' and k][-1], 'A1')


class PatchColumnTests(ConsolePdfBase):

    def test_patch_values_match_the_page(self):
        host = self.ch(self.foh, 1, 'Host Mic')
        self.ch(self.foh, 2, 'Lectern', source_b='Lectern B')
        self.ch(self.foh, 3, 'Spare')
        self.ch(self.foh, 4, 'Spare')
        self.ch(self.foh, 5, 'Shared')
        self.ch(self.mon, 1, 'Shared')
        renamed = self.ch(self.foh, 6, 'Guitar')
        self.port(self.box_a, 1, 'Host Mic', host)        # linked
        self.port(self.box_b, 1, 'Host Mic', host)        # linked twice: conflict
        self.port(self.box_b, 2, 'Lectern B')             # B, by name
        self.port(self.box_a, 2, 'Spare')                 # ambiguous on this console
        self.port(self.box_a, 3, 'Shared')                # ambiguous across consoles
        self.port(self.box_a, 4, 'Bass', renamed)         # linked, name not saved
        aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='1', name='Wedge 1')
        ConsoleMatrixOutput.objects.create(console=self.foh, matrix_number='1', name='Delay')
        left = ConsoleStereoOutput.objects.create(console=self.foh, stereo_type='L', name='Main')
        self.out(self.box_a, 1, 'Wedge 1', aux)
        self.out(self.box_b, 1, 'Wedge 1', aux)           # one aux, two outputs: normal
        self.out(self.box_a, 2, 'Delay')                  # by name
        self.out(self.box_a, 3, 'Main', left)

        sections = self.sections()
        printed = {}
        for title, header in (('Console Inputs', 'Input Ch'), ('Aux Outputs', 'Aux'),
                              ('Matrix Outputs', 'Matrix'), ('Stereo Outputs', 'Name')):
            s = sections[title]
            key, patch = s['headers'].index(header), s['headers'].index('Patch')
            for row in s['rows']:
                printed[(title, row[key])] = row[patch].split('\n') if row[patch] else []

        prefixes = {'consoleinput_set': 'Console Inputs', 'consoleauxoutput_set': 'Aux Outputs',
                    'consolematrixoutput_set': 'Matrix Outputs',
                    'consolestereooutput_set': 'Stereo Outputs'}
        on_page = {(prefixes[p], k): feeds for p, k, feeds in self.page_rows() if k}
        self.assertEqual(printed, on_page)

        # And the page says what we think it says.
        self.assertEqual(printed[('Console Inputs', '1')],
                         ['Stage Box A · In 1 — CONFLICT', 'Stage Box B · In 1 — CONFLICT'])
        self.assertEqual(printed[('Console Inputs', '2')], ['B: Stage Box B · In 2 — by name'])
        self.assertEqual(printed[('Console Inputs', '3')],
                         ['Stage Box A · In 2 — ambiguous (ch 3, ch 4)'])
        self.assertEqual(printed[('Console Inputs', '5')],
                         ['Stage Box A · In 3 — ambiguous (FOH, MON)'])
        self.assertEqual(printed[('Console Inputs', '6')],
                         ['Stage Box A · In 4 — name not saved'])
        self.assertEqual(printed[('Aux Outputs', '1')],
                         ['Stage Box A · Out 1', 'Stage Box B · Out 1'])
        self.assertEqual(printed[('Matrix Outputs', '1')], ['Stage Box A · Out 2 — by name'])
        self.assertEqual(printed[('Stereo Outputs', 'Main')], ['Stage Box A · Out 3'])

    def test_read_only_page_cells_match_too(self):
        # A viewer's cell is links, not the picker button: same text.
        from planner.models import ProjectMember
        from planner.tests.test_console_patch_picker import staff
        host = self.ch(self.foh, 1, 'Host Mic')
        self.port(self.box_a, 1, 'Host Mic', host)
        self.port(self.box_b, 5, 'Host Mic')
        viewer = staff('v')
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.client.force_login(viewer)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        page = {k: f for p, k, f in self.page_rows() if p == 'consoleinput_set' and k}
        both = ['Stage Box A · In 1', 'Stage Box B · In 5 — by name']
        self.assertEqual(page['1'], both)
        self.assertEqual(self.column('Console Inputs', 'Patch'), ['\n'.join(both)])


class UnusedRowTests(ConsolePdfBase):

    def test_rows_with_no_source_and_no_patch_are_left_out(self):
        for n in range(1, 145):
            ConsoleInput.objects.create(console=self.foh, input_ch=str(n), dante_number=str(n))
        ConsoleInput.objects.filter(console=self.foh, input_ch='3').update(source='Kick')
        ConsoleInput.objects.filter(console=self.foh, input_ch='4').update(source_b='Spare B')
        ConsoleInput.objects.filter(console=self.foh, input_ch='5').update(dca='1')
        ConsoleInput.objects.filter(console=self.foh, input_ch='6').update(mute='2')
        ConsoleInput.objects.filter(console=self.foh, input_ch='7').update(
            source_hardware='Shure AD2')
        ConsoleInput.objects.filter(console=self.foh, input_ch='8').update(color='Red')
        ConsoleInput.objects.filter(console=self.foh, input_ch='9').update(source='   ')
        unnamed = ConsoleInput.objects.get(console=self.foh, input_ch='10')
        self.port(self.box_a, 1, '', unnamed)             # patched, no source yet

        self.assertEqual(self.column('Console Inputs', 'Input Ch'),
                         ['3', '4', '5', '6', '7', '10'])
        self.assertEqual(self.column('Console Inputs', 'Patch')[-1], 'Stage Box A · In 1')

    def test_outputs_with_no_name_and_no_patch_are_left_out(self):
        for n in range(1, 5):
            ConsoleAuxOutput.objects.create(console=self.foh, aux_number=str(n),
                                            mono_stereo='Mono', dante_number=n)
        ConsoleAuxOutput.objects.filter(aux_number='2').update(name='Wedge')
        ConsoleAuxOutput.objects.filter(aux_number='3').update(omni_out='12')
        self.out(self.box_a, 1, '', ConsoleAuxOutput.objects.get(aux_number='4'))
        for t in ('L', 'R'):
            ConsoleStereoOutput.objects.create(console=self.foh, stereo_type=t)
        self.assertEqual(self.column('Aux Outputs', 'Aux'), ['2', '3', '4'])
        self.assertEqual(self.column('Stereo Outputs', 'Buss'), [])

    def test_the_pdf_prints_source_hardware_and_patch_even_when_blank(self):
        ConsoleInput.objects.create(console=self.foh, input_ch='1', source='Kick')
        response = self.client.get(reverse('planner:console_pdf_export', args=[self.foh.pk]))
        self.assertEqual(response.status_code, 200)
        text = ''.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
        for header in ('Input Ch', 'Source', 'Src Hardware', 'Patch'):
            self.assertIn(header, text)
        self.assertNotIn('Group', text)                   # blank and optional: dropped
        self.assertIn('Kick', text)

    def test_an_unused_console_still_exports(self):
        ConsoleInput.objects.create(console=self.foh, input_ch='1')
        response = self.client.get(reverse('planner:console_pdf_export', args=[self.foh.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.column('Console Inputs', 'Input Ch'), [])
