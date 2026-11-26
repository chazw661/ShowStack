"""Runs without links total exactly as they did before links existed.

Links (``PACableLink``) made every total go through
``pa_cable_math.entry_pieces``. A run with no links is one piece, its home
run, so nothing about it may move. ``GOLDEN`` was captured from main at
0aa3a8e, before ``entry_pieces`` was written, from the fixture below: runs
with fan-outs, extensions, couplers, a jumper, a 0' run and a stored cable
value that is not a choice. Each of the four places that total or list PA
cable is compared with it whole:

    the changelist summary     PACableAdmin.changelist_view
    the Quick Order List       pa_cable_pdf._quick_order_rows
    the CSV export             PACableAdmin.export_cable_schedule
    the System Report          system_report._section_pa_cable

If one of these fails, the totals of every existing show changed. Fix the
code, not GOLDEN.

Run with::

    python manage.py test planner.tests.test_pa_cable_unlinked_totals \\
        --settings=audiopatch.test_settings
"""
import csv
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from planner.admin import PACableAdmin
from planner.admin_site import showstack_admin_site
from planner.models import (AmpLocation, PACableSchedule, PACoupler, PAFanOut,
                            PAFanOutExtension, PAZone, Project)
from planner.utils.pdf_exports import pa_cable_pdf, system_report

GOLDEN = {'changelist': {'cable_summary': {'100_NL4': {'couplers': 0,
                                              'fifties': 0,
                                              'fifties_with_safety': 0,
                                              'hundreds': 0,
                                              'hundreds_with_safety': 0,
                                              'is_jumper': False,
                                              'quantity_with_safety': 0,
                                              'total_length': 25,
                                              'total_runs': 1,
                                              'twenty_fives': 1,
                                              'twenty_fives_with_safety': 2},
                                  'CA-COM': {'couplers': 1,
                                             'fifties': 0,
                                             'fifties_with_safety': 0,
                                             'hundreds': 3,
                                             'hundreds_with_safety': 4,
                                             'is_jumper': False,
                                             'quantity_with_safety': 0,
                                             'total_length': 330,
                                             'total_runs': 3,
                                             'twenty_fives': 3,
                                             'twenty_fives_with_safety': 4},
                                  'NL 4': {'couplers': 2,
                                           'fifties': 5,
                                           'fifties_with_safety': 6,
                                           'hundreds': 2,
                                           'hundreds_with_safety': 3,
                                           'is_jumper': False,
                                           'quantity_with_safety': 0,
                                           'total_length': 450,
                                           'total_runs': 5,
                                           'twenty_fives': 0,
                                           'twenty_fives_with_safety': 0},
                                  'NL 8': {'couplers': 1,
                                           'fifties': 1,
                                           'fifties_with_safety': 2,
                                           'hundreds': 2,
                                           'hundreds_with_safety': 3,
                                           'is_jumper': False,
                                           'quantity_with_safety': 0,
                                           'total_length': 210,
                                           'total_runs': 2,
                                           'twenty_fives': 0,
                                           'twenty_fives_with_safety': 0},
                                  'NL4 Jumper': {'couplers': 0,
                                                 'fifties': 0,
                                                 'fifties_with_safety': 0,
                                                 'hundreds': 0,
                                                 'hundreds_with_safety': 0,
                                                 'is_jumper': True,
                                                 'quantity_with_safety': 8,
                                                 'total_length': 0,
                                                 'total_runs': 6,
                                                 'twenty_fives': 0,
                                                 'twenty_fives_with_safety': 0},
                                  'XLR': {'couplers': 0,
                                          'fifties': 0,
                                          'fifties_with_safety': 0,
                                          'hundreds': 0,
                                          'hundreds_with_safety': 0,
                                          'is_jumper': False,
                                          'quantity_with_safety': 0,
                                          'total_length': 0,
                                          'total_runs': 4,
                                          'twenty_fives': 0,
                                          'twenty_fives_with_safety': 0}},
                'coupler_summary': {'CACOM Coupler': {'total_quantity': 1, 'with_overage': 2},
                                    'NL4 Coupler': {'total_quantity': 2, 'with_overage': 3},
                                    'NL8 Coupler': {'total_quantity': 1, 'with_overage': 2}},
                'fan_out_summary': {'NL4 Y': {'total_quantity': 2, 'with_overage': 3},
                                    'NL8 Y': {'total_quantity': 1, 'with_overage': 2}},
                'grand_total': 1015},
 'csv': [["L'ACOUSTICS PA CABLE SCHEDULE"],
         [],
         ['Cable Label', 'From', 'To', 'Count', 'Cable', 'Fan Out', 'Notes', 'Drawing Ref'],
         ['HL', 'SL Racks', 'K2 Left', '2', 'NL 4', 'NL4 Y x2', '', ''],
         ['HR', 'SL Racks', 'K2 Right', '1', 'NL 8', 'NL8 Y x1', '', ''],
         ['SUB', 'SL Racks', 'KS28 stack', '6', 'NL4 Jumper', '', '', ''],
         ['FF', 'SL Racks', 'Front fills', '3', 'CA-COM', '', '', ''],
         ['DLY', 'SL Racks', 'Delay 1', '1', '100_NL4', '', '', ''],
         ['MON', 'SL Racks', 'Wedges', '4', 'XLR', '', '', ''],
         [],
         ['CABLE SUMMARY WITH ORDERING CALCULATIONS'],
         ['Cable Type',
          'Total Runs',
          'Total Length (ft)',
          '20% Overage',
          'Total w/Overage',
          "100' Lengths",
          "25' Lengths",
          'Remainder (ft)',
          'Couplers Needed'],
         ['NL 4', '2', '300.0', '60.0', '360.0', '3', '2', '10.0', '2'],
         ['NL 8', '1', '60.0', '12.0', '72.0', '0', '2', '22.0', '1'],
         ['NL4 Jumper', '6', '18.0', '3.6', '21.6', '0', '0', '21.6', '0'],
         ['CA-COM', '3', '330.0', '66.0', '396.0', '3', '3', '21.0', '1'],
         ['100_NL4', '1', '25.0', '5.0', '30.0', '0', '1', '5.0', '0'],
         ['XLR', '4', '0.0', '0.0', '0.0', '0', '0', '0.0', '0'],
         [],
         ['GRAND TOTAL', '17', '733.0', '146.6', '879.6', '', '', '', ''],
         [],
         ['FAN OUT SUMMARY'],
         ['Type', 'Total Quantity', '20% Overage', 'Total w/Overage'],
         ['NL4 Y', '2', '2 × 20%', '3'],
         ['NL8 Y', '1', '1 × 20%', '2']],
 'quick_order': [['NL4 Jumper', '—', '8'],
                 ['NL 4', "100'", '3'],
                 ['NL 4', "50'", '6'],
                 ['CA-COM', "100'", '4'],
                 ['CA-COM', "25'", '4'],
                 ['NL 8', "100'", '3'],
                 ['NL 8', "50'", '2'],
                 ['100_NL4', "25'", '2'],
                 ['NL4 Y', 'Fan Out', '3'],
                 ['NL8 Y', 'Fan Out', '2'],
                 ['NL4 Coupler', 'Coupler', '3'],
                 ['NL8 Coupler', 'Coupler', '2'],
                 ['CACOM Coupler', 'Coupler', '2']],
 'system_report': [['Cable Label', 'From', 'To', 'Cable Type', 'Length', 'Count', 'Fan Outs'],
                   ['HL', 'SL Racks', 'K2 Left', 'NL 4', '150', '2', 'NL4 Y x2'],
                   ['HR', 'SL Racks', 'K2 Right', 'NL 8', '60', '1', 'NL8 Y x1'],
                   ['SUB', 'SL Racks', 'KS28 stack', 'NL4 Jumper', '3', '6', '-'],
                   ['FF', 'SL Racks', 'Front fills', 'CA-COM', '110', '3', '-'],
                   ['DLY', 'SL Racks', 'Delay 1', '100_NL4 (unknown type)', '25', '1', '-'],
                   ['MON', 'SL Racks', 'Wedges', 'XLR', '', '4', '-']]}


def build(project):
    """Six runs, no links."""
    rack = AmpLocation.objects.create(project=project, name='SL Racks')
    zones = {name: PAZone.objects.create(project=project, name=name, sort_order=i)
             for i, name in enumerate(('HL', 'HR', 'SUB', 'FF', 'DLY', 'MON'))}

    def run(zone, to, cable, count, length):
        return PACableSchedule.objects.create(
            project=project, label=zones[zone], amp_location=rack, destination=to,
            cable=cable, count=count, length=length)

    hl = run('HL', 'K2 Left', 'NL_4', 2, 150)
    fan = PAFanOut.objects.create(cable_schedule=hl, fan_out_type='NL4_Y', quantity=2)
    PAFanOutExtension.objects.create(cable_schedule=hl, fan_out=fan,
                                     extension_cable='NL4', extension_length=50, quantity=3)
    PAFanOutExtension.objects.create(cable_schedule=hl, fan_out=fan,
                                     extension_cable='NL8', extension_length=150, quantity=1)
    PACoupler.objects.create(cable_schedule=hl, coupler_type='NL4_COUPLER', quantity=2)

    hr = run('HR', 'K2 Right', 'NL_8', 1, 60)
    PAFanOut.objects.create(cable_schedule=hr, fan_out_type='NL8_Y', quantity=1)
    PACoupler.objects.create(cable_schedule=hr, coupler_type='NL8_COUPLER', quantity=1)

    run('SUB', 'KS28 stack', 'NL4_JUMPER', 6, 3)

    ff = run('FF', 'Front fills', 'CA-COM', 3, 110)
    PACoupler.objects.create(cable_schedule=ff, coupler_type='CACOM_COUPLER', quantity=1)

    run('DLY', 'Delay 1', '100_NL4', 1, 25)      # not one of the choices
    run('MON', 'Wedges', 'XLR', 4, 0)


class UnlinkedTotalsTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='pa_totals', email='t@example.com', password='x')
        self.project = Project.objects.create(name='unlinked totals', owner=self.user)
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        build(self.project)

    def queryset(self):
        return PACableSchedule.objects.filter(project=self.project)

    def changelist(self):
        context = self.client.get('/admin/planner/pacableschedule/').context
        return {key: context[key] for key in
                ('cable_summary', 'fan_out_summary', 'coupler_summary', 'grand_total')}

    def csv_rows(self):
        admin_obj = PACableAdmin(PACableSchedule, showstack_admin_site)
        request = self.client.get('/admin/planner/pacableschedule/').wsgi_request
        response = admin_obj.export_cable_schedule(request, self.queryset())
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8'))))
        return [row for row in rows if not (row and row[0].startswith('Generated:'))]

    def system_report(self):
        with mock.patch.object(system_report, '_data_table') as table:
            system_report._section_pa_cable(
                self.project, system_report._styles(), PACableSchedule)
        headers, rows, _widths = table.call_args[0]
        return [headers] + rows

    def test_the_changelist_summary(self):
        self.assertEqual(self.changelist(), GOLDEN['changelist'])

    def test_the_quick_order_list(self):
        self.assertEqual(pa_cable_pdf._quick_order_rows(self.queryset()), GOLDEN['quick_order'])

    def test_the_csv_export(self):
        self.assertEqual(self.csv_rows(), GOLDEN['csv'])

    def test_the_system_report(self):
        self.assertEqual(self.system_report(), GOLDEN['system_report'])
