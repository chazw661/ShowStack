"""Every PDF's footer on a multi-page build: this project's name and
"Page N of M" on each page.

The footer text rides on the canvas class, which ReportLab instantiates
itself. Both NumberedCanvas classes used to have it assigned on the shared
class per request; each build now gets its own subclass
(``report_kit.NumberedCanvas.for_build`` and the system report's
``SystemReportCanvas``). That mechanism is tested in test_console_inline_str;
this module checks each export that goes through it, one by one, with enough
rows to run past a page, and each one again straight after another project's
build.

    python manage.py test planner.tests.test_pdf_footers \\
        --settings=audiopatch.test_settings
"""
import io
import re

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from PyPDF2 import PdfReader

from planner.models import (
    Amp, AmpLocation, AmpModel, CommBeltPack, Console, ConsoleInput, Device, DeviceInput,
    DeviceOutput, Location, PACableSchedule, Project, SoundvisionPrediction, SpeakerArray,
    SpeakerCabinet,
)
from planner.utils.pdf_exports import system_report
from planner.utils.pdf_exports.amplifier_pdf import export_all_amps_pdf
from planner.utils.pdf_exports.comm_pdf import generate_comm_beltpacks_pdf
from planner.utils.pdf_exports.console_pdf import export_console_pdf
from planner.utils.pdf_exports.device_pdf import export_all_devices_pdf, export_device_pdf
from planner.utils.pdf_exports.ip_address_report_pdf import generate_ip_address_report_pdf
from planner.utils.pdf_exports.location_pdf import export_all_locations_pdf, export_location_pdf
from planner.utils.pdf_exports.pa_cable_pdf import generate_pa_cable_pdf
from planner.utils.pdf_exports.soundvision_pdf import generate_soundvision_pdf

OWN, OTHER = 'Alpha Tour', 'Bravo Gala'


def pdf_bytes(result):
    """The exports return an HttpResponse, a BytesIO or bytes."""
    if isinstance(result, bytes):
        return result
    if hasattr(result, 'getvalue'):
        return result.getvalue()
    return result.content


def pages_of(result):
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf_bytes(result))).pages]


class Show:
    """One project with enough of everything for each export to pass a page."""

    def __init__(self, name, owner):
        self.project = p = Project.objects.create(name=name, owner=owner)
        self.location = Location.objects.create(project=p, name='Stage Left')
        Location.objects.create(project=p, name='Front of House')

        self.console = Console.objects.create(project=p, name='FOH', location=self.location,
                                              primary_ip_address='10.0.0.1')
        ConsoleInput.objects.bulk_create(
            ConsoleInput(console=self.console, input_ch=str(n), source=f'Source {n}')
            for n in range(1, 145))
        for n in range(2, 90):
            Console.objects.create(project=p, name=f'Desk {n:02d}', location=self.location,
                                   primary_ip_address=f'10.0.1.{n}')

        self.device = self.make_device('Stage Box 01', 96, 48)
        for n in range(2, 5):
            self.make_device(f'Stage Box {n:02d}', 32, 16)

        rack = AmpLocation.objects.create(project=p, name='Amp Rack SL')
        model, _ = AmpModel.objects.get_or_create(
            manufacturer='L-Acoustics', model_name='Footer Test Amp',
            defaults={'channel_count': 4})
        for n in range(1, 25):
            Amp.objects.create(project=p, location=rack, amp_model=model, name=f'Amp {n:02d}')

        for n in range(1, 91):
            PACableSchedule.objects.create(project=p, cable='NL_4', count=1, length=50,
                                           destination=f'Hang {n}')

        for n in range(1, 91):
            CommBeltPack.objects.create(project=p, bp_number=n, system_type='WIRELESS')

        self.prediction = SoundvisionPrediction.objects.create(project=p, file_name='main.pdf')
        for a in range(1, 9):
            array = SpeakerArray.objects.create(
                prediction=self.prediction, source_name=f'K2 {a}', array_base_name=f'K2 {a}',
                configuration='', bumper_type='K2-BUMP')
            SpeakerCabinet.objects.bulk_create(
                SpeakerCabinet(array=array, position_number=c, speaker_model='K2')
                for c in range(1, 13))

    def make_device(self, name, ins, outs):
        d = Device.objects.create(project=self.project, name=name, location=self.location,
                                  input_count=ins, output_count=outs)
        DeviceInput.objects.filter(device=d).delete()
        DeviceOutput.objects.filter(device=d).delete()
        DeviceInput.objects.bulk_create(
            DeviceInput(device=d, input_number=n, signal_name=f'In {n}')
            for n in range(1, ins + 1))
        DeviceOutput.objects.bulk_create(
            DeviceOutput(device=d, output_number=n, signal_name=f'Out {n}')
            for n in range(1, outs + 1))
        return d


class PdfFooterTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('footers', password='pw', is_staff=True,
                                             is_superuser=True)
        cls.own = Show(OWN, cls.owner)
        cls.other = Show(OTHER, cls.owner)

    def request(self, show):
        request = RequestFactory().get('/')
        request.user = self.owner
        request.current_project = show.project
        return request

    def assert_footers(self, build, first_footer_page=1):
        """``build(show)`` makes the PDF. Built for the other project first,
        then for this one: every footer names this project only and counts
        "Page N of M" with M the real page count, on a build of 2+ pages."""
        other = pages_of(build(self.other))
        own = pages_of(build(self.own))
        for pages, name, not_name in ((other, OTHER, OWN), (own, OWN, OTHER)):
            total = len(pages)
            self.assertGreaterEqual(total, 2, 'the fixture must run past one page')
            for number, text in enumerate(pages, 1):
                footer = re.findall(r'Page (\d+) of (\d+)', text)
                if number < first_footer_page:
                    self.assertEqual(footer, [])
                    continue
                self.assertEqual(footer, [(str(number), str(total))])
                self.assertIn(f'Page {number} of {total}', text)
                # The footer line itself: the name sits just before the count.
                self.assertRegex(text, re.escape(name) + r'\s*Page %d of %d' % (number, total))
                self.assertNotIn(not_name, text)
                self.assertIn('showstack.io', text)
        return own

    def test_console_pdf_footer(self):
        self.assert_footers(lambda s: export_console_pdf(s.console))

    def test_device_pdf_footer(self):
        self.assert_footers(lambda s: export_device_pdf(s.device))

    def test_all_devices_pdf_footer(self):
        self.assert_footers(lambda s: export_all_devices_pdf(s.project))

    def test_amplifier_pdf_footer(self):
        self.assert_footers(lambda s: export_all_amps_pdf(s.project))

    def test_pa_cable_pdf_footer(self):
        self.assert_footers(lambda s: generate_pa_cable_pdf(
            PACableSchedule.objects.filter(project=s.project).order_by('pk')))

    def test_comm_pdf_footer(self):
        self.assert_footers(lambda s: generate_comm_beltpacks_pdf(project=s.project))

    def test_ip_address_pdf_footer(self):
        self.assert_footers(lambda s: generate_ip_address_report_pdf(project=s.project))

    def test_location_pdf_footer(self):
        self.assert_footers(lambda s: export_location_pdf(self.request(s), s.location.pk))

    def test_all_locations_pdf_footer(self):
        self.assert_footers(lambda s: export_all_locations_pdf(self.request(s)))

    def test_soundvision_pdf_footer(self):
        self.assert_footers(lambda s: generate_soundvision_pdf(s.prediction))

    def test_system_report_footer(self):
        """The cover (page 1) is clean; the count still includes it."""
        pages = self.assert_footers(
            lambda s: system_report.export_system_report(self.request(s)),
            first_footer_page=2)
        self.assertGreaterEqual(len(pages), 5)
