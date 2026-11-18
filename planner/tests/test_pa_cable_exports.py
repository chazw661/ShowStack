"""Every PA cable export names a run's Cable Label, From and To.

PR 2b-1 made one entry mode. Three properties resolve what a run is, and the
changelist, the CSV, the PA Cable PDF and the System Report all read them, so
no export can disagree with the screen:

    cable_label_display  ->  label.name
    from_display         ->  amp.name, else amp_location.name
    to_display           ->  destination, else the linked arrays' names

Three kinds of row are exported side by side: an old free-text row (label
and destination, no From), an old linked row (amp and a linked array, no
label or destination -- what migration 0234 left it as) and a new run.

(Before #99 / issue #73, the PDF and CSV read the raw columns, so a linked
row exported with both cells blank; the "never two blanks" tests keep that
fixed.)

Run with::

    python manage.py test planner.tests.test_pa_cable_exports \\
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
    """One project: an amp in a rack, a Soundvision array, a cable label."""

    ARRAY_NAME = 'K2 Main L'
    AMP_NAME = 'SL LA12X #2'
    RACK_NAME = 'SL LA Racks'

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
        self.rack = AmpLocation.objects.create(project=self.project, name=self.RACK_NAME)
        model = AmpModel.objects.create(manufacturer="L'Acoustics",
                                        model_name='LA12X', channel_count=4)
        self.amp = Amp.objects.create(project=self.project, name=self.AMP_NAME,
                                      location=self.rack, amp_model=model)
        pred = SoundvisionPrediction.objects.create(project=self.project,
                                                    file_name='show.pdf')
        self.array = SpeakerArray.objects.create(
            prediction=pred, source_name=self.ARRAY_NAME,
            array_base_name=self.ARRAY_NAME,
            configuration='vertical_flown', bumper_type='K2-BUMP')

    def add_text_cable(self, **kw):
        """An old free-text row: a label and a destination, no From."""
        kw.setdefault('label', self.zone)
        kw.setdefault('destination', 'SR Amp Rack')
        return PACableSchedule.objects.create(
            project=self.project, cable='NL_4', count=2, length=100, **kw)

    def add_linked_cable(self, **kw):
        """An old linked row as migrated: an amp and an array, nothing typed."""
        row = PACableSchedule.objects.create(
            project=self.project, entry_mode='linked', amp=self.amp,
            cable='XLR', count=1, length=200, **kw)
        row.speaker_arrays.add(self.array)
        return row

    def add_new_run(self, **kw):
        kw.setdefault('destination', 'KIVA DELAY 2 & 3')
        return PACableSchedule.objects.create(
            project=self.project, label=self.zone, amp=self.amp, cable='NL_4',
            count=1, length=50, **kw)

    def queryset(self):
        return PACableSchedule.objects.filter(project=self.project)


class DisplayPropertyTests(_CableMixin, TestCase):

    def test_an_old_linked_row(self):
        cable = self.add_linked_cable()
        self.assertEqual((cable.cable_label_display, cable.from_display, cable.to_display),
                         ('', self.AMP_NAME, self.ARRAY_NAME))

    def test_an_old_free_text_row(self):
        cable = self.add_text_cable()
        self.assertEqual((cable.cable_label_display, cable.from_display, cable.to_display),
                         ('Main R', '', 'SR Amp Rack'))

    def test_a_new_run(self):
        cable = self.add_new_run()
        self.assertEqual((cable.cable_label_display, cable.from_display, cable.to_display),
                         ('Main R', self.AMP_NAME, 'KIVA DELAY 2 & 3'))

    def test_a_run_from_a_rack_only(self):
        cable = self.add_text_cable(amp_location=self.rack)
        self.assertEqual(cable.from_display, self.RACK_NAME)

    def test_picking_an_amp_sets_its_rack(self):
        other = AmpLocation.objects.create(project=self.project, name='Other')
        cable = self.add_new_run(amp_location=other)
        cable.refresh_from_db()
        self.assertEqual(cable.amp_location, self.rack)

    def test_typed_to_wins_over_linked_arrays(self):
        cable = self.add_new_run()
        cable.speaker_arrays.add(self.array)
        self.assertEqual(cable.to_display, 'KIVA DELAY 2 & 3')


class PaCablePdfTests(_CableMixin, TestCase):
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

    def test_all_three_kinds_of_row(self):
        self.add_text_cable()
        self.add_linked_cable()
        self.add_new_run()
        got = sorted((r[0], r[1], r[2]) for r in self.rows())
        self.assertEqual(got, [('-', self.AMP_NAME, self.ARRAY_NAME),
                               ('Main R', '-', 'SR Amp Rack'),
                               ('Main R', self.AMP_NAME, 'KIVA DELAY 2 &amp; 3')])

    def test_a_linked_row_never_exports_two_blanks(self):
        self.add_linked_cable()
        row = self.rows()[0]
        self.assertNotEqual(row[1], '-')
        self.assertNotEqual(row[2], '-')

    def test_a_cable_with_nothing_still_renders_a_placeholder(self):
        """An empty row must not crash or print 'None'."""
        PACableSchedule.objects.create(
            project=self.project, cable='NL_4', count=1, length=10)
        self.assertEqual(self.rows()[0][:3], ['-', '-', '-'])

    def test_markup_in_a_name_is_escaped_for_the_paragraph(self):
        self.add_new_run(destination='<b>Fill</b> & <i>sub</i>')
        pdf = pa_cable_pdf.generate_pa_cable_pdf(self.queryset())   # would raise on bad markup
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn('&lt;b&gt;Fill', self.rows()[0][2])

    def test_it_renders(self):
        self.add_linked_cable()
        pdf = pa_cable_pdf.generate_pa_cable_pdf(self.queryset())
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'%%EOF', pdf[-32:])

    def test_the_export_view_renders(self):
        """End to end through the real view, including its select_related."""
        self.add_linked_cable()
        self.add_new_run()
        response = self.client.get('/audiopatch/pa-cables/all/pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))


class PaCableCsvTests(_CableMixin, TestCase):
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
        body = self.section(rows, 'Cable Label')
        out = []
        for row in body:
            if not any(cell.strip() for cell in row):
                break
            out.append(row)
        return out

    def test_all_three_kinds_of_row(self):
        self.add_text_cable()
        self.add_linked_cable()
        self.add_new_run()
        got = sorted((r[0], r[1], r[2]) for r in self.cable_rows(self.export()))
        self.assertEqual(got, [('', self.AMP_NAME, self.ARRAY_NAME),
                               ('Main R', '', 'SR Amp Rack'),
                               ('Main R', self.AMP_NAME, 'KIVA DELAY 2 & 3')])

    def test_a_linked_row_never_exports_two_blanks(self):
        self.add_linked_cable()
        row = self.cable_rows(self.export())[0]
        self.assertNotEqual(row[1], '')
        self.assertNotEqual(row[2], '')


class PaCableCsvColumnAlignmentTests(_CableMixin, TestCase):
    """Each value sits under its own heading.

    The heading row named eight columns and the data rows wrote seven, so
    everything after 'Cable' was one cell to the left of its own name and the
    last heading was always empty. 'Count2' was the phantom -- no such field.
    """

    export = PaCableCsvTests.export
    section = PaCableCsvTests.section
    cable_rows = PaCableCsvTests.cable_rows

    HEADINGS = ['Cable Label', 'From', 'To', 'Count', 'Cable', 'Fan Out',
                'Notes', 'Drawing Ref']

    def test_the_heading_row_is_what_we_expect(self):
        rows = self.export()
        for row in rows:
            if row and row[0] == 'Cable Label':
                self.assertEqual(row, self.HEADINGS)
                return
        self.fail('no column heading row in the CSV')

    def test_every_value_lands_under_its_own_heading(self):
        cable = self.add_text_cable(notes='Clr. 1 Top 2', drawing_ref='D-14')
        PAFanOut.objects.create(cable_schedule=cable, fan_out_type='NL4_Y',
                                quantity=3)
        row = self.cable_rows(self.export())[0]
        by_name = dict(zip(self.HEADINGS, row))
        self.assertEqual(by_name['Cable Label'], 'Main R')
        self.assertEqual(by_name['From'], '')
        self.assertEqual(by_name['To'], 'SR Amp Rack')
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

    export = PaCableCsvTests.export
    section = PaCableCsvTests.section

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
