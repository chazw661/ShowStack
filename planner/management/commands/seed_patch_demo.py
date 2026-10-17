"""Seed a local demo show for the console <-> I/O device patch work.

**Local SQLite only.** The command refuses to run against any other database
engine: ``.env`` in this repo has carried a production proxy URL before, and a
seed that deletes and recreates a project is not something to aim at a real
show by accident.

What it builds (replacing any previous copy of the same demo project):

  FOH Rivage PM7   96 inputs, 12 aux, 4 matrix, St L/R/M
  MON CL5          48 inputs -- 1-16 split from Stage Box A, 17-20 from the
                   wireless rack
  MON PM5          24 inputs, the same band names as FOH 1-24, but its own
                   I/O: MON Stage Box, no split
  Stage Box A      32 in / 16 out -- ports picked from the suggestion list,
                   so they carry the console_input link
  Stage Box B      32 in / 16 out -- named but NOT linked, which is exactly
                   how the I/O device page saved every pick from #95 until
                   the link fix (the regression the backfill repairs)
  Wireless Rack    16 in / 2 out -- linked to FOH 49-64
  MON Stage Box    16 in / 8 out -- in 1-8 linked to MON PM5 1-8; in 9-10
                   named only

Deliberate edge cases, so every display state has something to show:

  renamed channel    FOH ch 22 "Vox 3" is renamed to "Vox 3 (Guest)" after
                     Stage Box A in 22 was linked to it
  duplicate "Spare"  FOH ch 90 and 91 are both "Spare"; Stage Box B in 20 is
                     named "Spare" -- ambiguous by name
  free-typed name    Stage Box B in 22 "Talkback Mic" and Stage Box A in 30
                     "Playback L (QLab)" match no channel
  split              Stage Box A in 1-16 feed FOH 1-16 (linked) and MON CL5
                     1-16 (same names). Nothing records a split yet, and a
                     linked port counts only for the console it is linked to,
                     so MON CL5 shows these unpatched
  own I/O, no split  MON PM5 has FOH's channel names but its own stage box.
                     Its linked ports show on MON PM5 only, never on FOH;
                     MON Stage Box in 9-10 ("OH L", "OH R", no link) fit FOH,
                     MON CL5 and MON PM5, so they are ambiguous on all three
                     and the backfill leaves them for a human
  A/B pair           FOH ch 25 "Lectern" / B "Lectern B": Stage Box A in 25 is
                     the A feed (linked), Stage Box B in 25 the B (by name)
  conflict           Stage Box A in 27 and Stage Box B in 27 are both linked
                     to FOH ch 70 "Host Mic"
  unpatched          FOH 72-89 are named with no port; 92-96 are blank
  outputs            Aux 1-8 -> Stage Box A out 1-8 (linked), Aux 1 also ->
                     Stage Box A out 9; St L/R -> Stage Box B out 1-2 (stereo
                     has no link, so by name); Mtx 1 linked, Mtx 2 by name;
                     Stage Box B out 5 "Comms Feed" free-typed

Usage::

    python manage.py seed_patch_demo                 # first superuser owns it
    python manage.py seed_patch_demo --user charlie
"""

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput,
    ConsoleStereoOutput, Device, DeviceInput, DeviceOutput, Project,
)

PROJECT_NAME = 'Patch Demo (seed)'

BAND = [
    'Kick In', 'Kick Out', 'Snare Top', 'Snare Btm', 'Hat', 'Tom 1', 'Tom 2',
    'Floor Tom', 'OH L', 'OH R', 'Bass DI', 'Bass Mic', 'Gtr 1', 'Gtr 2',
    'Keys L', 'Keys R', 'Track L', 'Track R', 'Click', 'Vox 1', 'Vox 2',
    'Vox 3', 'Vox 4', 'Perc',
]
UNPATCHED = [
    'Video PB L', 'Video PB R', 'Laptop L', 'Laptop R', 'Zoom L', 'Zoom R',
    'Phone Patch', 'Audience L', 'Audience R', 'Ambient 1', 'Ambient 2',
    'Walk-in L', 'Walk-in R', 'Announce', 'Stage Mgr', 'Backup Host',
    'Backup Lectern', 'Line 89',
]
AUX = ['Drum Wedge', 'Bass Wedge', 'Gtr Wedge', 'Keys Wedge', 'Vox 1 Wedge',
       'Vox 2 Wedge', 'Side Fill L', 'Side Fill R']
MATRIX = ['Lobby', 'Front Fill', 'Delay Ring', 'Record L']


class Command(BaseCommand):
    help = ("Create a local demo show for the console/I-O patch display. "
            "SQLite only; replaces any previous copy of the demo project.")

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Username to own the demo project '
                            '(default: the first superuser).')

    def handle(self, *args, **opts):
        if connection.vendor != 'sqlite':
            raise CommandError(
                'seed_patch_demo only runs against local SQLite; this '
                f'database is {connection.vendor!r}. Unset DATABASE_URL.')

        if opts['user']:
            user = User.objects.filter(username=opts['user']).first()
            if user is None:
                raise CommandError(f"No user named {opts['user']!r}.")
        else:
            user = User.objects.filter(is_superuser=True).order_by('pk').first()
            if user is None:
                raise CommandError('No superuser yet: run createsuperuser, '
                                   'or pass --user.')

        with transaction.atomic():
            replaced = Project.objects.filter(owner=user, name=PROJECT_NAME).delete()[0]
            project = self._build(user)

        self.stdout.write(self.style.SUCCESS(
            f'{"Replaced" if replaced else "Created"} "{PROJECT_NAME}" '
            f'(project id {project.pk}) owned by {user.username}.'))
        self.stdout.write('Select it in the project switcher, then open '
                          'Consoles -> FOH Rivage PM7.')

    # ------------------------------------------------------------------

    def _build(self, user):
        project = Project.objects.create(name=PROJECT_NAME, owner=user,
                                         venue='Local demo')

        foh = Console.objects.create(project=project, name='FOH Rivage PM7')
        mon = Console.objects.create(project=project, name='MON CL5')
        pm5 = Console.objects.create(project=project, name='MON PM5')

        foh_names = {}
        for i, name in enumerate(BAND, 1):
            foh_names[i] = name
        foh_names[25] = 'Lectern'
        for i in range(33, 45):
            foh_names[i] = f'Choir {i - 32}'
        for i in range(49, 65):
            foh_names[i] = f'Wless {i - 48}'
        foh_names[70] = 'Host Mic'
        for i, name in zip(range(72, 90), UNPATCHED):
            foh_names[i] = name
        foh_names[90] = foh_names[91] = 'Spare'

        foh_ch = {}
        for ch in range(1, 97):
            foh_ch[ch] = ConsoleInput.objects.create(
                console=foh, input_ch=str(ch), dante_number=str(ch),
                source=foh_names.get(ch, ''),
                source_b='Lectern B' if ch == 25 else None,
            )
        for ch in range(1, 49):
            if ch <= 16:
                name = BAND[ch - 1]
            elif ch <= 20:
                name = f'Wless {ch - 16}'
            else:
                name = ''
            ConsoleInput.objects.create(console=mon, input_ch=str(ch),
                                        dante_number=str(ch), source=name)
        pm5_ch = {}
        for ch in range(1, 25):
            pm5_ch[ch] = ConsoleInput.objects.create(
                console=pm5, input_ch=str(ch), dante_number=str(ch),
                source=BAND[ch - 1])

        aux = {}
        for n in range(1, 13):
            aux[n] = ConsoleAuxOutput.objects.create(
                console=foh, aux_number=str(n),
                name=AUX[n - 1] if n <= 8 else '', mono_stereo='Mono')
        mtx = {}
        for n, name in enumerate(MATRIX, 1):
            mtx[n] = ConsoleMatrixOutput.objects.create(
                console=foh, matrix_number=str(n), name=name, mono_stereo='Mono')
        for st, name in (('L', 'PA Left'), ('R', 'PA Right'), ('M', 'Sub')):
            ConsoleStereoOutput.objects.create(console=foh, stereo_type=st, name=name)

        box_a = self._device(project, 'Stage Box A', 32, 16)
        box_b = self._device(project, 'Stage Box B', 32, 16)
        rack = self._device(project, 'Wireless Rack', 16, 2)
        mon_box = self._device(project, 'MON Stage Box', 16, 8)

        def link(device, port, channel):
            """A pick from the suggestion list: name AND link."""
            DeviceInput.objects.filter(device=device, input_number=port).update(
                signal_name=channel.source, console_input=channel)

        def name_only(device, port, name):
            """Typed, or picked before the link fix: name, no link."""
            DeviceInput.objects.filter(device=device, input_number=port).update(
                signal_name=name, console_input=None)

        # Stage Box A: band 1-24 linked (FOH 1-16 also split to MON by name).
        for ch in range(1, 25):
            link(box_a, ch, foh_ch[ch])
        link(box_a, 25, foh_ch[25])                       # A feed of an A/B pair
        link(box_a, 27, foh_ch[70])                       # conflict, side 1
        name_only(box_a, 30, 'Playback L (QLab)')         # free-typed

        # Stage Box B: patched after #95 -- names, no links.
        for port in range(1, 13):
            name_only(box_b, port, f'Choir {port}')
        name_only(box_b, 20, 'Spare')                     # ambiguous
        name_only(box_b, 22, 'Talkback Mic')              # free-typed
        name_only(box_b, 25, 'Lectern B')                 # B feed of the pair
        link(box_b, 27, foh_ch[70])                       # conflict, side 2

        # Wireless rack: linked straight to FOH 49-64.
        for port in range(1, 17):
            link(rack, port, foh_ch[48 + port])

        # MON PM5's own stage box: picked after the fix (linked to MON PM5,
        # though FOH has the same names), and two ports from before it.
        for ch in range(1, 9):
            link(mon_box, ch, pm5_ch[ch])
        name_only(mon_box, 9, 'OH L')                     # ambiguous: 3 consoles
        name_only(mon_box, 10, 'OH R')

        # Renamed after linking. .save() rather than .update() so anything
        # listening for a ConsoleInput save sees the rename, as it would from
        # the Console page.
        renamed = foh_ch[22]
        renamed.source = 'Vox 3 (Guest)'
        renamed.save()

        aux_ct = ContentType.objects.get_for_model(ConsoleAuxOutput)
        mtx_ct = ContentType.objects.get_for_model(ConsoleMatrixOutput)

        def out(device, port, name, ct=None, obj=None):
            DeviceOutput.objects.filter(device=device, output_number=port).update(
                signal_name=name, content_type=ct,
                object_id=obj.pk if obj else None)

        for n in range(1, 9):
            out(box_a, n, AUX[n - 1], aux_ct, aux[n])
        out(box_a, 9, AUX[0], aux_ct, aux[1])            # one aux, two outputs
        out(box_b, 1, 'PA Left')                          # stereo: name only
        out(box_b, 2, 'PA Right')
        out(box_b, 3, 'Lobby', mtx_ct, mtx[1])
        out(box_b, 4, 'Front Fill')                       # matrix, by name
        out(box_b, 5, 'Comms Feed')                       # free-typed
        return project

    @staticmethod
    def _device(project, name, ins, outs):
        device = Device.objects.create(project=project, name=name,
                                       input_count=ins, output_count=outs)
        DeviceInput.objects.bulk_create(
            DeviceInput(device=device, input_number=n, signal_name='')
            for n in range(1, ins + 1))
        DeviceOutput.objects.bulk_create(
            DeviceOutput(device=device, output_number=n, signal_name='')
            for n in range(1, outs + 1))
        return device
