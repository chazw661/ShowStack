"""A linked-mode PA cable must name its array and amp in every export.

Issue #73 gave ``PACableSchedule`` two entry modes. A 'text' cable carries its
values in ``label`` (a PAZone FK) and ``destination`` (a CharField). A 'linked'
cable leaves both of those empty and points at a Soundvision ``SpeakerArray``
and an ``Amp`` instead, and the effective values are resolved by two
properties:

    array_speaker_display  ->  speaker_array.display_name  or  label.name
    destination_display    ->  amp.name                    or  destination

The PA Cable changelist columns use those properties, and the System Report
started to in #99. The PA Cable PDF and the Cable Schedule CSV did not: they
read the raw ``label`` and ``destination`` columns, so a linked cable exported
with both its Array/Speaker and Destination cells empty -- the run was listed,
with its cable type, count and length, but with nothing to say what it ran
from or to.

Run with::

    python manage.py test planner.tests.test_pa_cable_linked_exports \\
        --settings=audiopatch.test_settings
"""
import csv
import io

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from planner.admin import PACableAdmin
from planner.admin_site import showstack_admin_site
from planner.models import (Amp, AmpLocation, AmpModel, PACableSchedule,
                            PACoupler, PAFanOut, PAZone, Project,
                            SoundvisionPrediction, SpeakerArray)
from planner.utils.pdf_exports import pa_cable_pdf


class _CableMixin:
    """One project holding one free-text cable and one linked cable."""

    ARRAY_NAME = 'K2 Main L'
    AMP_NAME = 'SL LA12X #2'

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='pa_linked', email='l@example.com', password='x')
        self.project = Project.objects.create(name='linked exports',
                                              owner=self.user)
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

        self.zone = PAZone.objects.create(project=self.project, name='Main R')
        loc = AmpLocation.objects.create(project=self.project,
                                         name='SL LA Racks')
        model = AmpModel.objects.create(manufacturer="L'Acoustics",
                                        model_name='LA12X', channel_count=4)
        self.amp = Amp.objects.create(project=self.project, name=self.AMP_NAME,
                                      location=loc, amp_model=model)
        pred = SoundvisionPrediction.objects.create(project=self.project,
                                                    file_name='show.pdf')
        self.array = SpeakerArray.objects.create(
            prediction=pred, source_name=self.ARRAY_NAME,
            array_base_name=self.ARRAY_NAME,
            configuration='vertical_flown', bumper_type='K2-BUMP')

    def add_text_cable(self, **kw):
        kw.setdefault('label', self.zone)
        kw.setdefault('destination', 'SR Amp Rack')
        return PACableSchedule.objects.create(
            project=self.project, entry_mode='text', cable='NL_4',
            count=2, length=100, **kw)

    def add_linked_cable(self, **kw):
        return PACableSchedule.objects.create(
            project=self.project, entry_mode='linked',
            speaker_array=self.array, amp=self.amp, cable='XLR',
            count=1, length=200, **kw)

    def queryset(self):
        return PACableSchedule.objects.filter(project=self.project)


class LinkedCableModelTests(_CableMixin, TestCase):
    """The premise: a linked cable really does leave the raw columns empty."""

    def test_a_linked_cable_has_no_label_and_no_destination(self):
        cable = self.add_linked_cable()
        self.assertIsNone(cable.label)
        self.assertEqual(cable.destination, '')
        # ...but it is not anonymous; the properties resolve it.
        self.assertEqual(cable.array_speaker_display, self.ARRAY_NAME)
        self.assertEqual(cable.destination_display, self.AMP_NAME)


class PaCablePdfLinkedModeTests(_CableMixin, TestCase):
    """The PA Cable Schedule PDF."""

    def rows(self):
        """``_cable_rows`` output flattened to plain strings."""
        S = pa_cable_pdf.kit.styles()
        out = []
        for row in pa_cable_pdf._cable_rows(self.queryset(), S):
            out.append([
                getattr(cell, 'text', cell).replace('<b>', '').replace(
                    '</b>', '')
                for cell in row
            ])
        return out

    def test_a_linked_cable_names_its_array_and_amp(self):
        self.add_linked_cable()
        row = self.rows()[0]
        self.assertEqual(row[0], self.ARRAY_NAME)   # Array/Speaker
        self.assertEqual(row[1], self.AMP_NAME)     # Destination

    def test_a_linked_cable_no_longer_exports_two_blanks(self):
        """The regression itself: '-' in both cells is what the bug looked like."""
        self.add_linked_cable()
        row = self.rows()[0]
        self.assertNotEqual(row[0], '-')
        self.assertNotEqual(row[1], '-')

    def test_a_free_text_cable_is_unchanged(self):
        self.add_text_cable()
        row = self.rows()[0]
        self.assertEqual(row[0], 'Main R')
        self.assertEqual(row[1], 'SR Amp Rack')

    def test_both_modes_in_one_export(self):
        self.add_text_cable()
        self.add_linked_cable()
        got = sorted((r[0], r[1]) for r in self.rows())
        self.assertEqual(got, [(self.ARRAY_NAME, self.AMP_NAME),
                               ('Main R', 'SR Amp Rack')])

    def test_a_cable_with_neither_still_renders_a_placeholder(self):
        """An empty row must not crash or print 'None'."""
        PACableSchedule.objects.create(
            project=self.project, cable='NL_4', count=1, length=10)
        row = self.rows()[0]
        self.assertEqual(row[0], '-')
        self.assertEqual(row[1], '-')

    def test_the_heading_names_the_column_it_holds(self):
        self.add_linked_cable()
        pdf = pa_cable_pdf.generate_pa_cable_pdf(self.queryset())
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'%%EOF', pdf[-32:])

    def test_the_export_view_renders_the_linked_name(self):
        """End to end through the real view, including its select_related."""
        self.add_linked_cable()
        response = self.client.get('/audiopatch/pa-cables/all/pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))


class PaCableCsvLinkedModeTests(_CableMixin, TestCase):
    """The "Export Cable Schedule to CSV" admin action."""

    def export(self):
        admin_obj = PACableAdmin(PACableSchedule, showstack_admin_site)
        request = self.client.get(
            '/admin/planner/pacableschedule/').wsgi_request
        response = admin_obj.export_cable_schedule(request, self.queryset())
        self.assertEqual(response['Content-Type'], 'text/csv')
        text = response.content.decode('utf-8')
        return list(csv.reader(io.StringIO(text)))

    def section(self, rows, first_cell):
        """The rows under the heading whose first cell is `first_cell`."""
        for i, row in enumerate(rows):
            if row and row[0] == first_cell:
                return rows[i + 1:]
        self.fail('no %r section in the CSV' % first_cell)

    def cable_rows(self, rows):
        """The run rows: between the column headings and the blank line."""
        body = self.section(rows, 'Array/Speaker')
        out = []
        for row in body:
            if not any(cell.strip() for cell in row):
                break
            out.append(row)
        return out

    def test_a_linked_cable_names_its_array_and_amp(self):
        self.add_linked_cable()
        row = self.cable_rows(self.export())[0]
        self.assertEqual(row[0], self.ARRAY_NAME)
        self.assertEqual(row[1], self.AMP_NAME)

    def test_a_linked_cable_no_longer_exports_two_blanks(self):
        self.add_linked_cable()
        row = self.cable_rows(self.export())[0]
        self.assertNotEqual(row[0], '')
        self.assertNotEqual(row[1], '')

    def test_a_free_text_cable_is_unchanged(self):
        self.add_text_cable()
        row = self.cable_rows(self.export())[0]
        self.assertEqual(row[0], 'Main R')
        self.assertEqual(row[1], 'SR Amp Rack')

    def test_both_modes_in_one_export(self):
        self.add_text_cable()
        self.add_linked_cable()
        got = sorted((r[0], r[1]) for r in self.cable_rows(self.export()))
        self.assertEqual(got, [(self.ARRAY_NAME, self.AMP_NAME),
                               ('Main R', 'SR Amp Rack')])


class PaCableCsvColumnAlignmentTests(_CableMixin, TestCase):
    """Each value sits under its own heading.

    The heading row named eight columns and the data rows wrote seven, so
    everything after 'Cable' was one cell to the left of its own name and the
    last heading was always empty. 'Count2' was the phantom -- no such field.
    """

    export = PaCableCsvLinkedModeTests.export
    section = PaCableCsvLinkedModeTests.section
    cable_rows = PaCableCsvLinkedModeTests.cable_rows

    HEADINGS = ['Array/Speaker', 'Destination', 'Count', 'Cable', 'Fan Out',
                'Notes', 'Drawing Ref']

    def test_the_heading_row_is_what_we_expect(self):
        rows = self.export()
        for row in rows:
            if row and row[0] == 'Array/Speaker':
                self.assertEqual(row, self.HEADINGS)
                return
        self.fail('no column heading row in the CSV')

    def test_every_value_lands_under_its_own_heading(self):
        cable = self.add_text_cable(notes='Clr. 1 Top 2', drawing_ref='D-14')
        PAFanOut.objects.create(cable_schedule=cable, fan_out_type='NL4_Y',
                                quantity=3)
        row = self.cable_rows(self.export())[0]
        by_name = dict(zip(self.HEADINGS, row))
        self.assertEqual(by_name['Array/Speaker'], 'Main R')
        self.assertEqual(by_name['Destination'], 'SR Amp Rack')
        self.assertEqual(by_name['Count'], '2')
        self.assertEqual(by_name['Cable'], 'NL 4')
        self.assertEqual(by_name['Fan Out'], 'NL4 Y x3')
        self.assertEqual(by_name['Notes'], 'Clr. 1 Top 2')
        self.assertEqual(by_name['Drawing Ref'], 'D-14')

    def test_the_row_is_as_wide_as_the_heading(self):
        self.add_text_cable(notes='n', drawing_ref='d')
        row = self.cable_rows(self.export())[0]
        self.assertEqual(len(row), len(self.HEADINGS))

    def test_no_phantom_count2_heading(self):
        self.add_text_cable()
        flat = [cell for row in self.export() for cell in row]
        self.assertNotIn('Count2', flat)


class PaCableCsvFanOutSummaryTests(_CableMixin, TestCase):
    """The FAN OUT SUMMARY totals every cable, not just the last one.

    The tally loop sat one indent level out, in the method body instead of the
    per-cable loop, so it ran once against whichever cable the loop left
    behind.
    """

    export = PaCableCsvLinkedModeTests.export
    section = PaCableCsvLinkedModeTests.section

    def summary(self):
        rows = self.section(self.export(), 'FAN OUT SUMMARY')
        out = {}
        for row in rows[1:]:          # skip that section's own heading row
            if not any(cell.strip() for cell in row):
                break
            out[row[0]] = int(row[1])
        return out

    def test_fan_outs_on_several_cables_are_all_counted(self):
        a = self.add_text_cable()
        b = self.add_linked_cable()
        c = self.add_text_cable(destination='FOH Amp Rack')
        PAFanOut.objects.create(cable_schedule=a, fan_out_type='NL4_Y',
                                quantity=2)
        PAFanOut.objects.create(cable_schedule=b, fan_out_type='NL4_Y',
                                quantity=3)
        PAFanOut.objects.create(cable_schedule=c, fan_out_type='NL8_Y',
                                quantity=1)
        # Pre-fix this returned only the fan-outs of the final row in the
        # queryset -- one of the three.
        self.assertEqual(self.summary(), {'NL4 Y': 5, 'NL8 Y': 1})

    def test_a_cable_with_no_fan_outs_contributes_nothing(self):
        a = self.add_text_cable()
        self.add_linked_cable()
        PAFanOut.objects.create(cable_schedule=a, fan_out_type='NL4_Y',
                                quantity=2)
        self.assertEqual(self.summary(), {'NL4 Y': 2})

    def test_the_export_survives_a_project_with_no_fan_outs_at_all(self):
        self.add_text_cable()
        self.add_linked_cable()
        rows = self.export()
        self.assertNotIn('FAN OUT SUMMARY',
                         [cell for row in rows for cell in row])

    def test_couplers_still_reach_the_cable_summary(self):
        """The coupler tally runs over its own queryset; keep it working."""
        cable = self.add_text_cable()
        PACoupler.objects.create(cable_schedule=cable,
                                 coupler_type='NL4_COUPLER', quantity=2)
        body = self.section(self.export(),
                            'CABLE SUMMARY WITH ORDERING CALCULATIONS')
        for row in body[1:]:
            if row and row[0] == 'NL 4':
                self.assertEqual(int(row[-1]), 2)   # Couplers Needed
                return
        self.fail('no NL 4 row in the cable summary')
