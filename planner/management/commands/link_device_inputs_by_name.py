"""Link I/O device inputs to console channels by name -- the backfill for #95.

**Dry-run unless given --apply, and it is not wired into any deploy step.**

From #95 until the link fix, picking "FOH PM7 · Ch 3 · Kick" on the I/O device
page saved only the text "Kick": ``DeviceInput.console_input`` stayed empty, so
the device PDF and the System Report printed a blank Console Source for every
port patched in that window. This command finds those ports and, where the name
identifies exactly one channel, links them.

For every input with a name and no link, it looks for console channels in the
**same project** whose Source or Source (B) is that name (trimmed,
case-insensitive; template consoles are ignored). It never guesses: a link is
written only when the name identifies exactly one channel, as its A input.

  MATCHED    exactly one channel, by its Source. --apply links it.
  AMBIGUOUS  more than one channel -- on more than one console (FOH and a
             monitor desk with the same channel list, whether or not the stage
             box is actually split to both), or twice on one console (a
             duplicate "Spare"). Left alone and listed per device, for a human
             to pick on the I/O device page.
  B INPUT    exactly one channel, but by its Source (B). A stored link always
             means the A input, so this is left alone and listed.
  UNMATCHED  none -- a free-typed name ("Talkback Mic"), or a channel renamed
             since. Left alone.

It also reports ports that ARE linked but whose name has drifted from the
channel's current name (renamed before the rename-follows-the-link fix):

  STALE      --apply copies the channel's current name onto the port.

Each project is applied in its own transaction, and each write re-checks that
the port is still unlinked, so a port someone patched by hand in the meantime is
never overwritten.

Usage::

    # dry-run, everything:
    python manage.py link_device_inputs_by_name
    # one project, every port listed:
    python manage.py link_device_inputs_by_name --project 3 -v 2
    # write:
    python manage.py link_device_inputs_by_name --project 3 --apply

    # against prod: inside the app container, no database proxy (CLAUDE.md).
    # Take a Railway Postgres backup first, and read the dry-run before --apply:
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py link_device_inputs_by_name
"""

from collections import defaultdict
from itertools import groupby

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planner.models import ConsoleInput, DeviceInput, Project
from planner.utils.device_patch import norm

MATCHED, AMBIGUOUS, B_INPUT, UNMATCHED, STALE = (
    'matched', 'ambiguous', 'b input', 'unmatched', 'stale')


def _where(channel, slot='A'):
    where = f'{channel.console.name} ch {channel.input_ch}'
    return where if slot == 'A' else f'{where} (B)'


def classify(project):
    """{kind: [(DeviceInput, [(ConsoleInput, slot), ...]), ...]} for one
    project. ``slot`` is 'A' or 'B': which of the channel's names matched."""
    # name -> {channel: slot}. One entry per channel, so a channel whose A and
    # B are both the name counts once, as A.
    by_name = defaultdict(dict)
    channels = (ConsoleInput.objects
                .filter(console__project=project, console__is_template=False)
                .select_related('console')
                .order_by('console__name', 'pk'))
    for ch in channels:
        for value, slot in ((ch.source_b, 'B'), (ch.source, 'A')):
            if norm(value):
                by_name[norm(value)][ch] = slot

    result = {MATCHED: [], AMBIGUOUS: [], B_INPUT: [], UNMATCHED: [], STALE: []}
    ports = (DeviceInput.objects
             .filter(device__project=project)
             .select_related('device', 'console_input__console')
             .order_by('device__name', 'device_id', 'input_number'))
    for port in ports:
        if port.console_input_id:
            current = (port.console_input.source or '').strip()
            if current and current != (port.signal_name or '').strip():
                result[STALE].append((port, [(port.console_input, 'A')]))
            continue
        if not norm(port.signal_name):
            continue
        found = list(by_name.get(norm(port.signal_name), {}).items())
        if not found:
            kind = UNMATCHED
        elif len(found) > 1:
            kind = AMBIGUOUS
        else:
            kind = MATCHED if found[0][1] == 'A' else B_INPUT
        result[kind].append((port, found))
    return result


class Command(BaseCommand):
    help = ("Link named-but-unlinked I/O device inputs to the one console "
            "channel of that name. Dry-run unless given --apply.")

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the links (default: report only).')
        parser.add_argument('--project', type=int,
                            help='Only this project id.')

    def handle(self, *args, **opts):
        projects = Project.objects.order_by('pk')
        if opts['project']:
            projects = projects.filter(pk=opts['project'])
            if not projects.exists():
                raise CommandError(f"No project with id {opts['project']}.")
        apply, verbose = opts['apply'], opts['verbosity'] >= 2

        self.stdout.write('APPLYING' if apply else
                          'DRY RUN -- nothing is written. Add --apply to write.')
        totals = defaultdict(int)
        for project in projects:
            result = classify(project)
            if not any(result.values()):
                continue
            for kind, rows in result.items():
                totals[kind] += len(rows)
            self.stdout.write(
                f'\nProject {project.pk} "{project.name}": '
                f'{len(result[MATCHED])} matched, '
                f'{len(result[AMBIGUOUS])} ambiguous, '
                f'{len(result[B_INPUT])} B input only, '
                f'{len(result[UNMATCHED])} unmatched, '
                f'{len(result[STALE])} linked with a stale name')
            self._list(result, verbose)
            if apply:
                linked, renamed = self._apply(result)
                self.stdout.write(self.style.SUCCESS(
                    f'  wrote {linked} links, refreshed {renamed} names'))

        self.stdout.write(
            f'\nTotal: {totals[MATCHED]} matched, {totals[AMBIGUOUS]} ambiguous, '
            f'{totals[B_INPUT]} B input only, '
            f'{totals[UNMATCHED]} unmatched, {totals[STALE]} stale.')

    def _list(self, result, verbose):
        # Ambiguous and B-input rows are always listed, per device -- they are
        # the ones a human has to resolve, on that device's page. The rest
        # only with -v 2.
        for kind, heading in ((AMBIGUOUS, 'Ambiguous -- pick the channel by hand'),
                              (B_INPUT, 'Source (B) only -- not linked')):
            if not result[kind]:
                continue
            self.stdout.write(f'  {heading}:')
            for device, rows in groupby(result[kind], key=lambda r: r[0].device):
                self.stdout.write(f'    {device.name}')
                for port, found in rows:
                    self.stdout.write(
                        f'      In {port.input_number} "{port.signal_name}" -> '
                        + ', '.join(_where(ch, slot) for ch, slot in found))
        if verbose:
            for kind in (MATCHED, UNMATCHED, STALE):
                for port, found in result[kind]:
                    where = ', '.join(_where(ch, slot) for ch, slot in found) or '-'
                    self.stdout.write(
                        f'  {kind.upper():9} {port.device.name} In {port.input_number} '
                        f'"{port.signal_name}" -> {where}')

    @staticmethod
    def _apply(result):
        linked = renamed = 0
        with transaction.atomic():
            for port, ((channel, _slot),) in result[MATCHED]:
                linked += DeviceInput.objects.filter(
                    pk=port.pk, console_input__isnull=True,
                ).update(console_input=channel,
                         signal_name=(channel.source or '').strip())
            for port, ((channel, _slot),) in result[STALE]:
                renamed += DeviceInput.objects.filter(
                    pk=port.pk, console_input=channel,
                ).update(signal_name=(channel.source or '').strip())
        return linked, renamed
