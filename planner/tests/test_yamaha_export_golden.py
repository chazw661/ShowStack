"""The Yamaha Rivage CSV export is byte-identical with patches set.

The export carries channel and bus names only: InPatch is always NONE /
# Blank, and no patch -- A or B -- or Source (B) is ever written. The golden
files under fixtures/yamaha_golden/ were written by this test's fixture on
the code before the B-patch change (``SS_REGENERATE_YAMAHA_GOLDEN=1``);
every file in the zip, its name and order must match them byte for byte.

    python manage.py test planner.tests.test_yamaha_export_golden \\
        --settings=audiopatch.test_settings
"""
import io
import os
import zipfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase

from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput,
    ConsoleStereoOutput, Device, DeviceInput, Project,
)
from planner.utils.yamaha_export import export_yamaha_csvs

GOLDEN = Path(__file__).parent / 'fixtures' / 'yamaha_golden'
ORDER = GOLDEN / '_order.txt'


class YamahaExportGoldenTests(TestCase):

    def setUp(self):
        owner = User.objects.create_user('golden', 'g@example.com', 'pw')
        self.project = Project.objects.create(name='Golden', owner=owner)
        self.console = Console.objects.create(project=self.project, name='FOH')
        names = ['Kick', 'Snare, top', 'Lectern', '', 'Wless 1', 'Vox <b>', 'Ünïcode']
        self.channels = []
        for n, name in enumerate(names, 1):
            self.channels.append(ConsoleInput.objects.create(
                console=self.console, input_ch=str(n), dante_number=str(n),
                source=name, source_b=f'{name} B' if n % 2 else None,
                source_hardware='Shure AD1', source_hardware_b='Shure AD2'))
        ConsoleInput.objects.create(console=self.console, input_ch='ST 7', source='Odd')
        for n in (1, 2, 6):
            ConsoleAuxOutput.objects.create(console=self.console, aux_number=str(n),
                                            name=f'Mix {n}')
        ConsoleMatrixOutput.objects.create(console=self.console, matrix_number='3',
                                           name='Delay, L')
        ConsoleStereoOutput.objects.create(console=self.console, stereo_type='L', name='Main L')
        ConsoleStereoOutput.objects.create(console=self.console, stereo_type='M', name='')
        self.box = Device.objects.create(project=self.project, name='Stage Box',
                                         input_count=8, output_count=0)
        self.ports = [DeviceInput.objects.create(device=self.box, input_number=n)
                      for n in range(1, 9)]

    def patch(self):
        """A on In 1-4, B on In 5-7 and on In 1 (the same port as ch 1's A)."""
        for port, ch in zip(self.ports[:4], self.channels[:4]):
            port.console_input = ch
            port.signal_name = ch.source
            port.save()
        if hasattr(DeviceInput, 'console_input_b'):
            for port, ch in zip(self.ports[4:7], self.channels[4:7]):
                port.console_input_b = ch
                port.save()
            self.ports[0].console_input_b = self.channels[0]
            self.ports[0].save()

    def exported(self):
        response = export_yamaha_csvs(self.console)
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            return [(info.filename, z.read(info.filename)) for info in z.infolist()]

    def test_export_is_byte_identical_with_a_and_b_patches_and_source_b(self):
        self.patch()
        files = self.exported()
        if os.environ.get('SS_REGENERATE_YAMAHA_GOLDEN'):
            GOLDEN.mkdir(parents=True, exist_ok=True)
            for name, data in files:
                (GOLDEN / name).write_bytes(data)
            ORDER.write_text(''.join(f'{name}\n' for name, _ in files))
        self.assertEqual([name for name, _ in files], ORDER.read_text().split())
        for name, data in files:
            with self.subTest(file=name):
                self.assertEqual(data, (GOLDEN / name).read_bytes())
        in_patch = dict(files)['InPatch.csv']
        self.assertIn(b'IN_PATCH,SOURCE,COMMENT\n', in_patch)
        self.assertNotIn(b'\r', in_patch)
        self.assertNotIn(b'Stage Box', b''.join(d for _, d in files))
