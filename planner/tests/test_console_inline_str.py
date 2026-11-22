"""Console channels and buses keep their names after a Console page load.

The four console inlines used to set ``self.model.__str__ = lambda self: ""``
on every request and never undo it, so after any Console page load every
channel and bus printed as "" for the rest of that worker's life: delete
confirmations, and the "Changed ... for console input" lines in admin history.
Every test here loads the Console page first, then reads the names in the same
process.

Also here: the PDF footer canvas. Both ``NumberedCanvas`` classes took their
project name from an attribute assigned on the shared class per request; each
build now gets its own subclass.

    python manage.py test planner.tests.test_console_inline_str \\
        --settings=audiopatch.test_settings

The browser half is test_console_inline_str_browser.py; escaping is in
test_xss_server.py.
"""
import io
import re
from html import unescape
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PyPDF2 import PdfReader
from reportlab.platypus import Flowable, PageBreak, Paragraph

from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput, ConsoleStereoOutput,
    Project, ProjectMember,
)
from planner.tests.test_console_b_patch import PLAIN_STATIC, BFixture, make_user
from planner.utils.pdf_exports import report_kit, system_report

MODELS = (ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput)


class ChannelFixture(BFixture):
    """BFixture's FOH (Ch 1 Kick, Ch 2 Snare, Ch 5 Vox) plus one of each bus."""

    def setUp(self):
        super().setUp()
        self.aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='3',
                                                   name='Drum Wedge')
        self.matrix = ConsoleMatrixOutput.objects.create(console=self.foh, matrix_number='2',
                                                         name='Delay')
        self.stereo = ConsoleStereoOutput.objects.create(console=self.foh, stereo_type='L',
                                                         name='Main')
        self.url = reverse('admin:planner_console_change', args=[self.foh.pk])

    def viewer(self):
        viewer = make_user('viewer1', 'free', 'Viewer')
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.owner)
        return viewer

    def load_console_page(self, user=None):
        if user is not None:
            self.login(user)
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        return page

    def console_post(self, change=None, extra=None):
        """Post the Console page with every row as loaded, then ``change``
        ({POST key: value}) on top."""
        page = self.load_console_page()
        form = page.context['adminform'].form
        data = {'_continue': '1'}
        for name in form.fields:
            data[name] = self._posted(form[name].value())
        for inline in page.context['inline_admin_formsets']:
            fs = inline.formset
            data.update({f'{fs.prefix}-TOTAL_FORMS': len(fs.forms),
                         f'{fs.prefix}-INITIAL_FORMS': fs.initial_form_count(),
                         f'{fs.prefix}-MIN_NUM_FORMS': 0, f'{fs.prefix}-MAX_NUM_FORMS': 1000})
            for i, f in enumerate(fs.forms):
                for name in f.fields:
                    data[f'{fs.prefix}-{i}-{name}'] = self._posted(f[name].value())
        data = {k: v for k, v in data.items() if v is not False}
        data.update(change or {})
        for key in extra or ():
            data.pop(key, None)
        return self.client.post(self.url, data)

    @staticmethod
    def _posted(value):
        if value is None:
            return ''
        if value is True:
            return 'on'
        return value

    def row(self, prefix, pk):
        """The formset index of the row with this pk on the Console page."""
        page = self.load_console_page()
        for inline in page.context['inline_admin_formsets']:
            if inline.formset.prefix == prefix:
                for i, f in enumerate(inline.formset.forms):
                    if f.instance.pk == pk:
                        return i
        raise AssertionError(f'{prefix} row {pk} is not on the page')

    def last_log(self):
        return LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Console),
            object_id=str(self.foh.pk)).order_by('-pk').first()


@override_settings(STORAGES=PLAIN_STATIC)
class StrFormatTests(ChannelFixture, TestCase):

    def test_with_the_console_loaded_the_console_leads(self):
        self.assertEqual(str(self.kick), 'FOH · Ch 1 · Kick')
        self.assertEqual(str(self.aux), 'FOH · Aux 3 · Drum Wedge')
        self.assertEqual(str(self.matrix), 'FOH · Matrix 2 · Delay')
        self.assertEqual(str(self.stereo), 'FOH · Stereo Left · Main')

    def test_without_it_no_query_is_run_and_the_rest_still_reads(self):
        rows = [model.objects.get(pk=obj.pk) for model, obj in
                zip(MODELS, (self.kick, self.aux, self.matrix, self.stereo))]
        with self.assertNumQueries(0):
            texts = [str(r) for r in rows]
        self.assertEqual(texts, ['Ch 1 · Kick', 'Aux 3 · Drum Wedge', 'Matrix 2 · Delay',
                                 'Stereo Left · Main'])

    def test_select_related_brings_the_console_in_with_no_extra_query(self):
        rows = list(ConsoleInput.objects.select_related('console').filter(console=self.foh)
                    .order_by('pk'))
        with self.assertNumQueries(0):
            texts = [str(r) for r in rows]
        self.assertEqual(texts, ['FOH · Ch 1 · Kick', 'FOH · Ch 2 · Snare', 'FOH · Ch 5 · Vox'])

    def test_an_unnamed_row_has_no_dangling_part(self):
        foh = self.foh
        self.assertEqual(str(ConsoleInput(console=foh, input_ch='7')), 'FOH · Ch 7')
        self.assertEqual(str(ConsoleInput(console=foh, input_ch='7', source='  ')), 'FOH · Ch 7')
        self.assertEqual(str(ConsoleAuxOutput(console=foh, aux_number='4')), 'FOH · Aux 4')
        self.assertEqual(str(ConsoleAuxOutput(console=foh, aux_number='4', name='')),
                         'FOH · Aux 4')
        self.assertEqual(str(ConsoleMatrixOutput(console=foh, matrix_number='1')),
                         'FOH · Matrix 1')
        self.assertEqual(str(ConsoleStereoOutput(console=foh, stereo_type='M')), 'FOH · Mono')
        for model in MODELS:
            self.assertNotIn('None', str(model(console=foh)))

    def test_an_input_without_a_channel_number_falls_back(self):
        self.assertEqual(str(ConsoleInput(dante_number='5', source='Kick')), 'Dante 5 · Kick')
        self.assertEqual(str(ConsoleInput(pk=41)), 'Input 41')
        self.assertEqual(str(ConsoleInput()), 'Input New')

    def test_a_blank_row_never_prints_as_nothing(self):
        for model in MODELS:
            self.assertTrue(str(model()).strip(), model.__name__)


@override_settings(STORAGES=PLAIN_STATIC)
class AfterAConsolePageLoadTests(ChannelFixture, TestCase):

    def test_str_is_still_meaningful_as_an_editor_then_as_a_viewer(self):
        before = {model: model.__str__ for model in MODELS}
        for user in (self.owner, self.viewer()):
            self.load_console_page(user)
            self.assertEqual(str(self.kick), 'FOH · Ch 1 · Kick')
            self.assertEqual(str(self.aux), 'FOH · Aux 3 · Drum Wedge')
            self.assertEqual(str(self.matrix), 'FOH · Matrix 2 · Delay')
            self.assertEqual(str(self.stereo), 'FOH · Stereo Left · Main')
            for model in MODELS:
                # The class itself is what the request must not touch.
                self.assertIs(model.__str__, before[model], model.__name__)
                self.assertTrue(str(model.objects.filter(console=self.foh).first()))

    def test_the_add_page_leaves_the_models_alone_too(self):
        before = {model: model.__str__ for model in MODELS}
        self.assertEqual(self.client.get(reverse('admin:planner_console_add')).status_code, 200)
        for model in MODELS:
            self.assertIs(model.__str__, before[model], model.__name__)
        self.assertEqual(str(self.kick), 'FOH · Ch 1 · Kick')

    def test_the_inline_rows_carry_the_label_in_the_markup(self):
        """It is in the page (hidden by base_site.html's td.original rule --
        the browser test checks that), not blanked at the source. No console
        name here: the formset's rows are loaded without it."""
        html = unescape(self.load_console_page().content.decode())
        labels = [' '.join(p.split()) for p in
                  re.findall(r'<td class="original">\s*<p>(.*?)</p>', html, re.S)]
        self.assertEqual(labels, ['Ch 1 · Kick', 'Ch 2 · Snare', 'Ch 5 · Vox',
                                  'Aux 3 · Drum Wedge', 'Matrix 2 · Delay',
                                  'Stereo Left · Main'])

    def test_console_delete_confirmation_names_every_channel_and_bus(self):
        self.load_console_page()
        page = self.client.get(reverse('admin:planner_console_delete', args=[self.foh.pk]))
        self.assertEqual(page.status_code, 200)
        html = unescape(page.content.decode())
        for line in ('Console input: FOH · Ch 1 · Kick', 'Console input: FOH · Ch 2 · Snare',
                     'Console input: FOH · Ch 5 · Vox',
                     'Console aux output: FOH · Aux 3 · Drum Wedge',
                     'Console matrix output: FOH · Matrix 2 · Delay',
                     'Console stereo output: FOH · Stereo Left · Main'):
            self.assertIn(line, html)

    def test_the_delete_confirmation_costs_no_query_per_channel(self):
        """The admin's collector hands each channel its console (so the name
        leads), and __str__ never fetches one: 3 inputs or 60, the same
        number of queries."""
        url = reverse('admin:planner_console_delete', args=[self.foh.pk])
        self.load_console_page()
        self.client.get(url)                                   # warm the caches
        with CaptureQueriesContext(connection) as few:
            self.client.get(url)
        ConsoleInput.objects.bulk_create(
            ConsoleInput(console=self.foh, input_ch=str(n), source=f'Extra {n}')
            for n in range(10, 67))
        with CaptureQueriesContext(connection) as many:
            page = self.client.get(url)
        self.assertIn('FOH · Ch 66 · Extra 66', unescape(page.content.decode()))
        self.assertEqual(len(many), len(few))

    def test_project_delete_confirmation_names_them_too(self):
        admin = make_user('root1')
        admin.is_superuser = True
        admin.save()
        self.load_console_page(admin)
        page = self.client.get(reverse('admin:planner_project_delete', args=[self.project.pk]))
        self.assertEqual(page.status_code, 200)
        html = unescape(page.content.decode())
        for line in ('Console input: FOH · Ch 1 · Kick', 'Console input: MON · Ch 1 · Kick',
                     'Console aux output: FOH · Aux 3 · Drum Wedge',
                     'Console matrix output: FOH · Matrix 2 · Delay',
                     'Console stereo output: FOH · Stereo Left · Main'):
            self.assertIn(line, html)


@override_settings(STORAGES=PLAIN_STATIC)
class AdminHistoryTests(ChannelFixture, TestCase):
    """Channels have no admin page of their own: their names reach history
    through the Console's log entry, in its change message."""

    def history(self):
        page = self.client.get(reverse('admin:planner_console_history', args=[self.foh.pk]))
        self.assertEqual(page.status_code, 200)
        return unescape(page.content.decode())

    def test_editing_a_channel_after_a_page_load_names_it(self):
        i = self.row('consoleinput_set', self.kick.pk)
        r = self.console_post({f'consoleinput_set-{i}-source': 'Kick In'})
        self.assertEqual(r.status_code, 302, getattr(r, 'context', None)
                         and r.context['adminform'].form.errors)
        self.kick.refresh_from_db()
        self.assertEqual(self.kick.source, 'Kick In')
        log = self.last_log()
        self.assertEqual(log.object_repr, 'FOH')
        message = log.get_change_message()
        self.assertIn('Ch 1 · Kick In', message)
        self.assertNotIn('“”', message)
        self.assertIn('Ch 1 · Kick In', self.history())

    def test_editing_each_bus_names_it(self):
        change = {
            f"consoleauxoutput_set-{self.row('consoleauxoutput_set', self.aux.pk)}-name": 'Wedge 2',
            f"consolematrixoutput_set-{self.row('consolematrixoutput_set', self.matrix.pk)}-name":
                'Delay L',
            f"consolestereooutput_set-{self.row('consolestereooutput_set', self.stereo.pk)}-name":
                'Mains',
        }
        self.assertEqual(self.console_post(change).status_code, 302)
        message = self.last_log().get_change_message()
        for text in ('Aux 3 · Wedge 2', 'Matrix 2 · Delay L', 'Stereo Left · Mains'):
            self.assertIn(text, message)
        self.assertNotIn('“”', message)

    def test_adding_a_channel_names_it(self):
        page = self.load_console_page()
        total = next(len(i.formset.forms) for i in page.context['inline_admin_formsets']
                     if i.formset.prefix == 'consoleinput_set')
        r = self.console_post({
            'consoleinput_set-TOTAL_FORMS': total + 1,
            f'consoleinput_set-{total}-input_ch': '9',
            f'consoleinput_set-{total}-source': 'Hat',
            f'consoleinput_set-{total}-console': self.foh.pk,
            f'consoleinput_set-{total}-id': '',
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ConsoleInput.objects.filter(console=self.foh, source='Hat').exists())
        log = self.last_log()
        self.assertEqual(log.object_repr, 'FOH')
        self.assertIn('Ch 9 · Hat', log.get_change_message())
        self.assertIn('Ch 9 · Hat', self.history())

    def test_deleting_a_channel_names_it(self):
        i = self.row('consoleinput_set', self.vox.pk)
        r = self.console_post({f'consoleinput_set-{i}-DELETE': 'on'})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ConsoleInput.objects.filter(pk=self.vox.pk).exists())
        message = self.last_log().get_change_message()
        self.assertIn('Ch 5 · Vox', message)
        self.assertNotIn('“”', message)


# ---------------------------------------------------------------------------
# PDF footer canvas
# ---------------------------------------------------------------------------
def page_texts(pdf_bytes):
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf_bytes)).pages]


class _BuildAnother(Flowable):
    """Draws nothing; while it is being drawn, builds another PDF -- the
    position a second request is in when two builds overlap."""

    def __init__(self, build):
        super().__init__()
        self.build = build
        self.width = self.height = 0

    def wrap(self, *args):
        return 0, 0

    def draw(self):
        build, self.build = self.build, None        # once, not on every pass
        if build:
            build()


class SystemReportFooterTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('footer_owner', password='pw', is_staff=True,
                                              is_superuser=True)
        self.alpha = Project.objects.create(name='Alpha Tour', owner=self.owner)
        self.bravo = Project.objects.create(name='Bravo Gala', owner=self.owner)
        for project in (self.alpha, self.bravo):
            Console.objects.create(project=project, name='FOH')

    def report(self, project):
        request = RequestFactory().get('/audiopatch/system-report/pdf/')
        request.user = self.owner
        request.current_project = project
        response = system_report.export_system_report(request)
        self.assertEqual(response.status_code, 200)
        return page_texts(response.content)

    def footers(self, pages):
        """Pages past the cover carry the footer; the cover never does."""
        self.assertGreater(len(pages), 1)
        return pages[1:]

    def test_two_reports_in_sequence_each_carry_their_own_project(self):
        alpha = self.report(self.alpha)
        bravo = self.report(self.bravo)
        again = self.report(self.alpha)
        for pages, own, other in ((alpha, 'Alpha Tour', 'Bravo Gala'),
                                  (bravo, 'Bravo Gala', 'Alpha Tour'),
                                  (again, 'Alpha Tour', 'Bravo Gala')):
            for text in self.footers(pages):
                self.assertIn(own, text)
                self.assertNotIn(other, text)
                self.assertIn('showstack.io', text)

    def test_a_build_leaves_the_shared_canvas_class_as_it_was(self):
        self.report(self.alpha)
        self.assertEqual(system_report.NumberedCanvas._report_project_name, '')
        self.assertEqual(system_report.NumberedCanvas._footer_from_page, 2)

    def test_a_report_built_during_another_does_not_rename_its_footer(self):
        inner = {}
        real = system_report._section_soundvision

        def section(project, styles, model):
            story = real(project, styles, model)
            if project.pk == self.alpha.pk:
                story.append(_BuildAnother(
                    lambda: inner.setdefault('pages', self.report(self.bravo))))
            return story

        with mock.patch.object(system_report, '_section_soundvision', section):
            alpha = self.report(self.alpha)
        self.assertIn('pages', inner)
        for text in self.footers(alpha):
            self.assertIn('Alpha Tour', text)
            self.assertNotIn('Bravo Gala', text)
        for text in self.footers(inner['pages']):
            self.assertIn('Bravo Gala', text)
            self.assertNotIn('Alpha Tour', text)


class ReportKitFooterTests(TestCase):
    """report_kit.build_pdf: the footer of every single-module PDF."""

    def build(self, name, extra=()):
        st = report_kit.styles()
        story = [Paragraph('Page one', st['body']), *extra, PageBreak(),
                 Paragraph('Page two', st['body'])]
        buffer = io.BytesIO()
        report_kit.build_pdf(buffer, story, project_name=name)
        return page_texts(buffer.getvalue())

    def test_two_in_sequence_each_carry_their_own_project(self):
        alpha, bravo = self.build('Alpha Tour'), self.build('Bravo Gala')
        for pages, own, other in ((alpha, 'Alpha Tour', 'Bravo Gala'),
                                  (bravo, 'Bravo Gala', 'Alpha Tour')):
            self.assertEqual(len(pages), 2)
            for text in pages:
                self.assertIn(own, text)
                self.assertNotIn(other, text)

    def test_a_build_leaves_the_shared_canvas_class_as_it_was(self):
        self.build('Alpha Tour')
        self.assertEqual(report_kit.NumberedCanvas._project_name, '')
        self.assertIs(report_kit.NumberedCanvas._skip_first, True)

    def test_one_built_during_another_does_not_rename_its_footer(self):
        inner = {}
        alpha = self.build('Alpha Tour', extra=[_BuildAnother(
            lambda: inner.setdefault('pages', self.build('Bravo Gala')))])
        self.assertIn('pages', inner)
        for text in alpha:
            self.assertIn('Alpha Tour', text)
            self.assertNotIn('Bravo Gala', text)
        for text in inner['pages']:
            self.assertIn('Bravo Gala', text)

    def test_skip_first_is_per_build(self):
        st = report_kit.styles()
        story = [Paragraph('Cover', st['body']), PageBreak(), Paragraph('Body', st['body'])]
        buffer = io.BytesIO()
        report_kit.build_pdf(buffer, story, project_name='Alpha Tour', skip_first_footer=True)
        cover, body = page_texts(buffer.getvalue())
        self.assertNotIn('Alpha Tour', cover)
        self.assertIn('Alpha Tour', body)
        self.assertEqual(len(self.build('Bravo Gala')), 2)
        for text in self.build('Bravo Gala'):
            self.assertIn('Bravo Gala', text)
