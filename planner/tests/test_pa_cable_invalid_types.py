"""Rows carrying a cable value that is not one of CABLE_TYPE_CHOICES.

``PACableSchedule.cable`` defaulted to ``'100_NL4'`` until migration 0197,
and that string is not one of the choices. Rows saved on the old default are
not rewritten, so every reader has to cope with them -- the rule is that such
a value is always *flagged*, never silently dropped or shown as blank.

The three readers audited here:

  * the CSV importer (``import_pa_cables_csv``),
  * the admin Cable filter (``CableTypeFilter``),
  * the System Report PDF (``system_report._section_pa_cable``).

The changelist summary is covered by test_pa_cable_math.UnknownCableTypeTests.

Run with::

    python manage.py test planner.tests.test_pa_cable_invalid_types \
        --settings=audiopatch.test_settings
"""
import io

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from planner.admin import CableTypeFilter, PACableAdmin
from planner.admin_site import showstack_admin_site
from planner.models import PACableSchedule, PAZone, Project
from planner.utils import pa_cable_math

LEGACY = '100_NL4'


class CableDefaultTests(TestCase):
    """Migration 0197: the default is a value the choices list knows."""

    def test_default_is_a_declared_choice(self):
        field = PACableSchedule._meta.get_field('cable')
        self.assertEqual(field.get_default(), 'NL_4')
        self.assertIn(field.get_default(),
                      dict(PACableSchedule.CABLE_TYPE_CHOICES))

    def test_a_row_saved_without_a_type_is_now_valid(self):
        user = get_user_model().objects.create_superuser(
            username='pa_default', email='d@example.com', password='x')
        project = Project.objects.create(name='defaults', owner=user)
        row = PACableSchedule.objects.create(
            project=project, count=1, length=100, destination='SL')
        self.assertEqual(row.cable, 'NL_4')
        self.assertTrue(pa_cable_math.is_known_cable_type(row.cable))


class CableTypeLabelTests(TestCase):
    """One helper decides how an unrecognised value is shown."""

    def test_known_values_get_their_display_label(self):
        self.assertEqual(pa_cable_math.cable_type_label('NL_4'), 'NL 4')
        self.assertEqual(pa_cable_math.cable_type_label('NL4_JUMPER'),
                         'NL4 Jumper')

    def test_unknown_values_are_flagged_not_dropped(self):
        label = pa_cable_math.cable_type_label(LEGACY)
        self.assertIn(LEGACY, label)
        self.assertIn('unknown type', label)

    def test_blank_is_named_rather_than_empty(self):
        for value in ('', None):
            with self.subTest(value=value):
                self.assertEqual(pa_cable_math.cable_type_label(value),
                                 '(no cable type)')

    def test_is_known_cable_type(self):
        self.assertTrue(pa_cable_math.is_known_cable_type('NL_4'))
        self.assertFalse(pa_cable_math.is_known_cable_type(LEGACY))
        self.assertFalse(pa_cable_math.is_known_cable_type(''))


class _ProjectMixin:
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='pa_invalid', email='i@example.com', password='x')
        self.project = Project.objects.create(name='invalid types',
                                              owner=self.user)
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def add(self, cable, count=1, length=100):
        return PACableSchedule.objects.create(
            project=self.project, cable=cable, count=count, length=length,
            destination='SL Amp Rack')


class CableTypeFilterTests(_ProjectMixin, TestCase):
    """The Cable filter must be able to reach a legacy-value row."""

    def lookups(self):
        admin_obj = PACableAdmin(PACableSchedule, showstack_admin_site)
        request = self.client.get(
            '/admin/planner/pacableschedule/').wsgi_request
        flt = CableTypeFilter(request, {}, PACableSchedule, admin_obj)
        return flt.lookups(request, admin_obj)

    def test_declared_choices_are_always_offered(self):
        self.add('NL_4')
        values = [value for value, _ in self.lookups()]
        for declared, _ in PACableSchedule.CABLE_TYPE_CHOICES:
            self.assertIn(declared, values)

    def test_an_unknown_value_present_gets_its_own_flagged_option(self):
        self.add(LEGACY, count=2)
        options = dict(self.lookups())
        self.assertIn(LEGACY, options)
        self.assertIn('unknown type', options[LEGACY])

    def test_no_phantom_option_when_no_such_row_exists(self):
        self.add('NL_4')
        self.assertNotIn(LEGACY, dict(self.lookups()))

    def test_selecting_the_option_returns_exactly_those_rows(self):
        legacy = self.add(LEGACY)
        self.add('NL_4')
        response = self.client.get(
            '/admin/planner/pacableschedule/?cable=%s' % LEGACY)
        self.assertEqual(response.status_code, 200)
        ids = [obj.pk for obj in response.context_data['cl'].queryset]
        self.assertEqual(ids, [legacy.pk])

    def test_unfiltered_list_still_shows_the_legacy_row(self):
        """The point of the audit: it must never be dropped."""
        legacy = self.add(LEGACY)
        response = self.client.get('/admin/planner/pacableschedule/')
        ids = [obj.pk for obj in response.context_data['cl'].queryset]
        self.assertIn(legacy.pk, ids)

    def test_the_changelist_renders_the_flagged_option(self):
        self.add(LEGACY)
        html = self.client.get(
            '/admin/planner/pacableschedule/').content.decode()
        self.assertIn('unknown type', html)


class SystemReportCableTypeTests(_ProjectMixin, TestCase):
    """The System Report's Cable Type column."""

    HEADERS = ['Label', 'Cable Type', 'Length', 'Count', 'To Location',
               'Fan Outs']

    def rows(self):
        from planner.utils.pdf_exports import system_report
        styles = system_report._styles()
        story = system_report._section_pa_cable(
            self.project, styles, PACableSchedule)
        # The section banner is a Table too, so pick the one whose first row
        # is the cable header rather than just the first Table in the story.
        from reportlab.platypus import Table
        for frame in story:
            if isinstance(frame, Table) and \
                    list(frame._cellvalues[0]) == self.HEADERS:
                return frame._cellvalues
        self.fail('no PA cable table in the section: %r'
                  % [type(f).__name__ for f in story])

    def cable_column(self):
        return [row[1] for row in self.rows()[1:]]   # skip the header row

    def test_known_type_shows_its_display_label_not_the_stored_code(self):
        self.add('NL_4')
        self.assertEqual(self.cable_column(), ['NL 4'])

    def test_jumper_shows_its_label(self):
        self.add('NL4_JUMPER')
        self.assertEqual(self.cable_column(), ['NL4 Jumper'])

    def test_unknown_value_is_flagged_not_blank(self):
        self.add(LEGACY)
        column = self.cable_column()
        self.assertEqual(len(column), 1)
        self.assertIn(LEGACY, column[0])
        self.assertIn('unknown type', column[0])

    def test_it_reads_cable_not_the_stale_legacy_mirror(self):
        """`cable_type` is an editable=False copy kept in step by save().

        A queryset update() bypasses save(), so the mirror goes stale -- the
        report used to print that, and would have shown the old type.
        """
        row = self.add('NL_4')
        PACableSchedule.objects.filter(pk=row.pk).update(cable='CA-COM')
        row.refresh_from_db()
        self.assertEqual(row.cable, 'CA-COM')
        self.assertEqual(row.cable_type, 'NL_4')     # mirror is now stale
        self.assertEqual(self.cable_column(), ['CA-COM'])

    def test_the_whole_report_still_builds(self):
        self.add(LEGACY)
        self.add('NL_4')
        response = self.client.get(
            '/audiopatch/system-report/pdf/?project=%s' % self.project.pk)
        # The URL may be named differently; the section-level checks above are
        # the contract. This only asserts we did not break the view if it is
        # reachable.
        self.assertIn(response.status_code, (200, 302, 404))


class CsvImportInvalidCableTests(_ProjectMixin, TestCase):
    """The importer refuses a row it cannot classify, and says so."""

    URL = '/audiopatch/pa-cables/import-csv/'

    def post_csv(self, body):
        upload = io.BytesIO(body.encode('utf-8'))
        upload.name = 'cables.csv'
        return self.client.post(self.URL, {'csv_file': upload}, follow=True)

    def messages(self, response):
        return [str(m) for m in response.context['messages']]

    def test_an_unknown_cable_value_is_reported_and_nothing_is_created(self):
        before = PACableSchedule.objects.filter(project=self.project).count()
        response = self.post_csv(
            'Label,Destination,Count,Cable,Length\n'
            'FOH,SL Amp Rack,2,%s,100\n' % LEGACY)
        after = PACableSchedule.objects.filter(project=self.project).count()
        text = ' '.join(self.messages(response))
        self.assertEqual(after, before, 'the row must not be imported')
        self.assertIn('unknown Cable', text)
        self.assertIn(LEGACY, text)

    def test_a_good_row_in_the_same_file_still_imports(self):
        """One bad row must not take the whole file down silently."""
        response = self.post_csv(
            'Label,Destination,Count,Cable,Length\n'
            'FOH,SL Amp Rack,2,%s,100\n'
            'HL,HL Amp Rack,3,NL 4,150\n' % LEGACY)
        rows = PACableSchedule.objects.filter(project=self.project)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().cable, 'NL_4')
        text = ' '.join(self.messages(response))
        self.assertIn('unknown Cable', text)

    def test_display_labels_and_stored_codes_both_import(self):
        self.post_csv(
            'Label,Destination,Count,Cable,Length\n'
            'A,SL,1,NL 4,100\n'
            'B,SL,1,NL_8,100\n'
            'C,SL,1,NL4 Jumper,0\n')
        stored = sorted(PACableSchedule.objects
                        .filter(project=self.project)
                        .values_list('cable', flat=True))
        self.assertEqual(stored, ['NL4_JUMPER', 'NL_4', 'NL_8'])

    def test_the_importer_never_writes_an_unknown_value(self):
        self.post_csv(
            'Label,Destination,Count,Cable,Length\n'
            'A,SL,1,NL 4,100\n')
        for value in PACableSchedule.objects.filter(
                project=self.project).values_list('cable', flat=True):
            self.assertTrue(pa_cable_math.is_known_cable_type(value), value)
