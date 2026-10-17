"""Link I/O device inputs to console channels by name -- the backfill for #95.

**Dry-run unless given --apply, and it is not wired into any deploy step.**

From #95 until the link fix, picking "FOH PM7 · Ch 3 · Kick" on the I/O device
page saved only the text "Kick": ``DeviceInput.console_input`` stayed empty, so
the device PDF and the System Report printed a blank Console Source for every
port patched in that window. This command finds those ports and, where the name
identifies exactly one channel, links them.

For every input with a name and no link, it looks for console channels in the
**same project** whose source is that name (trimmed, case-insensitive; template
consoles are ignored):

  MATCHED    exactly one channel. --apply links it.
  AMBIGUOUS  several -- a duplicate "Spare", or the same name on FOH and MON
             (a split). Left alone and listed: the name alone cannot say which
             one the port feeds. The console page still shows these "by name".
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

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planner.models import ConsoleInput, DeviceInput, Project
from planner.utils.device_patch import norm

MATCHED, AMBIGUOUS, UNMATCHED, STALE = 'matched', 'ambiguous', 'unmatched', 'stale'


def _where(channel):
    return f'{channel.console.name} ch {channel.input_ch}'


def classify(project):
    """{kind: [(DeviceInput, [ConsoleInput, ...]), ...]} for one project."""
    by_name = defaultdict(list)
    channels = (ConsoleInput.objects
                .filter(console__project=project, console__is_template=False)
                .select_related('console')
                .order_by('console__name', 'pk'))
    for ch in channels:
        if norm(ch.source):
            by_name[norm(ch.source)].append(ch)

    result = {MATCHED: [], AMBIGUOUS: [], UNMATCHED: [], STALE: []}
    ports = (DeviceInput.objects
             .filter(device__project=project)
             .select_related('device', 'console_input__console')
             .order_by('device__name', 'input_number'))
    for port in ports:
        if port.console_input_id:
            current = (port.console_input.source or '').strip()
            if current and current != (port.signal_name or '').strip():
                result[STALE].append((port, [port.console_input]))
            continue
        if not norm(port.signal_name):
            continue
        found = by_name.get(norm(port.signal_name), [])
        kind = MATCHED if len(found) == 1 else AMBIGUOUS if found else UNMATCHED
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
                f'{len(result[UNMATCHED])} unmatched, '
                f'{len(result[STALE])} linked with a stale name')
            self._list(result, verbose)
            if apply:
                linked, renamed = self._apply(result)
                self.stdout.write(self.style.SUCCESS(
                    f'  wrote {linked} links, refreshed {renamed} names'))

        self.stdout.write(
            f'\nTotal: {totals[MATCHED]} matched, {totals[AMBIGUOUS]} ambiguous, '
            f'{totals[UNMATCHED]} unmatched, {totals[STALE]} stale.')

    def _list(self, result, verbose):
        # Ambiguous rows are always listed -- they are the ones a human has to
        # look at. The rest only with -v 2.
        shown = (MATCHED, AMBIGUOUS, UNMATCHED, STALE) if verbose else (AMBIGUOUS,)
        for kind in shown:
            for port, found in result[kind]:
                where = ', '.join(_where(ch) for ch in found) or '-'
                self.stdout.write(
                    f'  {kind.upper():9} {port.device.name} In {port.input_number} '
                    f'"{port.signal_name}" -> {where}')

    @staticmethod
    def _apply(result):
        linked = renamed = 0
        with transaction.atomic():
            for port, (channel,) in result[MATCHED]:
                linked += DeviceInput.objects.filter(
                    pk=port.pk, console_input__isnull=True,
                ).update(console_input=channel,
                         signal_name=(channel.source or '').strip())
            for port, (channel,) in result[STALE]:
                renamed += DeviceInput.objects.filter(
                    pk=port.pk, console_input=channel,
                ).update(signal_name=(channel.source or '').strip())
        return linked, renamed
