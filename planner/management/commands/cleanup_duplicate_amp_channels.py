"""Proposed cleanup for the AmpChannel rows issue #100's duplication left behind.

**Dry-run unless given --apply, and it is not wired into any deploy step.**
Merging this changes nothing: ``railway.json``'s ``startCommand`` does not call
it, so it only ever runs when someone types it. Run
``report_duplicate_amp_channels`` first and read what it says.

What it does
------------
For each amp holding two rows with the same ``channel_number``, keep one and
delete the rest:

  IDENTICAL    the rows hold the same patch (the all-blank case included).
               Keep the **lowest id** — they are interchangeable, so prefer the
               row anything else is likelier to already point at.
  ONE-SIDED    exactly one row holds patch data. Keep **that row**, whatever
               its id. This is the expected shape of the bug: the blank
               scaffold row was written first and so has the *lower* id, which
               is why "keep the oldest" would delete the engineer's patch.
  CONFLICTING  two or more rows hold patch data and disagree. **Skipped**, and
               listed at the end. Both answers are somebody's work; merging
               them is a judgement call, not a migration.

Why a command and not a data migration
--------------------------------------
A migration runs itself, once, inside the deploy — exactly when nobody is
watching, against the one database with real shows in it, with the CONFLICTING
cases decided by whatever the code happened to do. This data needs the opposite:
look at the report, run the dry-run, then apply deliberately, per project if you
like, with the option of stopping after the first project and checking a rack
in the admin. ``renumber_mic_assignments`` is here for the same reason.

Why not add a unique constraint on (amp, channel_number)
--------------------------------------------------------
That is the structural fix and it is the right follow-up — it is the *absence*
of that constraint that let the double-create write duplicates at all, where
the same bug against P1Processor could not (its channels are
``unique_together`` and created via ``get_or_create``). But the migration that
adds it fails while a single duplicate pair is still in the table, so it has to
come after this cleanup has run everywhere and
``report_duplicate_amp_channels`` is clean, including the CONFLICTING amps that
only a human can clear. Separate PR, once that is true.

Usage:
    # Dry-run — prints exactly what --apply would delete, writes nothing:
    python manage.py cleanup_duplicate_amp_channels

    # One project at a time is the recommended way in:
    python manage.py cleanup_duplicate_amp_channels --project 3
    python manage.py cleanup_duplicate_amp_channels --project 3 --apply

    # Everything the rules can decide:
    python manage.py cleanup_duplicate_amp_channels --apply

    # against prod — runs inside the app container, so it needs no database
    # proxy (see CLAUDE.md). Take a Railway Postgres backup first, and read the
    # dry-run before adding --apply:
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py cleanup_duplicate_amp_channels
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py cleanup_duplicate_amp_channels --apply
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import Amp, Project
from planner.utils.amp_channel_dupes import (
    CONFLICTING, IDENTICAL, ONE_SIDED,
    is_blank, judge, keeper_of, patch_of,
)


class Command(BaseCommand):
    help = ("Delete redundant duplicate AmpChannel rows, keeping the one "
            "carrying the patch. Dry-run unless given --apply.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually delete. Without this flag the command is a '
                 'dry-run and writes nothing.',
        )
        parser.add_argument(
            '--project', type=int, default=None,
            help='Restrict to a single Project id.',
        )
        parser.add_argument(
            '--amp', type=int, default=None,
            help='Restrict to a single Amp id — for clearing one rack by '
                 'hand after resolving a CONFLICTING group.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        amps = (Amp.objects
                .select_related('amp_model', 'location', 'project')
                .order_by('project_id', 'location__sort_order',
                          'sort_order', 'id'))
        if options['project'] is not None:
            amps = amps.filter(project_id=options['project'])
            if not Project.objects.filter(id=options['project']).exists():
                self.stdout.write(self.style.ERROR(
                    'No project with id %d.' % options['project']))
                return
        if options['amp'] is not None:
            amps = amps.filter(id=options['amp'])

        self.stdout.write(self.style.MIGRATE_HEADING(
            'cleanup_duplicate_amp_channels — %s'
            % ('APPLYING (rows will be deleted)' if apply_changes
               else 'DRY RUN (nothing will be written)')))

        amps_touched = 0
        rows_to_delete = []          # (amp, number, verdict, keeper, victims)
        skipped = []                 # (amp, number, rows)

        for amp in amps:
            groups, verdicts = judge(amp)
            if not groups:
                continue

            lines = []
            for number in sorted(groups):
                rows = groups[number]
                verdict = verdicts[number]
                keeper = keeper_of(rows, verdict)

                if keeper is None:
                    skipped.append((amp, number, rows))
                    lines.append((
                        '      ch %-3d x%d  %s  SKIPPED — %d row(s) hold '
                        'differing patches'
                        % (number, len(rows), self.style.ERROR(verdict),
                           sum(1 for r in rows if not is_blank(patch_of(r)))),
                        None))
                    continue

                victims = [r for r in rows if r.id != keeper.id]
                rows_to_delete.append((amp, number, verdict, keeper, victims))
                lines.append((
                    '      ch %-3d x%d  %s  keep id=%d, delete %s'
                    % (number, len(rows), self.style.SUCCESS(verdict),
                       keeper.id,
                       ','.join('id=%d' % r.id for r in victims)),
                    (keeper, victims)))

            if not lines:
                continue

            amps_touched += 1
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                '  project %d  amp id=%d  %r  (%s)'
                % (amp.project_id, amp.id, amp.name,
                   amp.project.name)))
            for text, _ in lines:
                self.stdout.write(text)

        total_victims = sum(len(v) for _, _, _, _, v in rows_to_delete)

        self.stdout.write('')
        if not amps_touched:
            self.stdout.write(self.style.SUCCESS(
                'Nothing to do — no amp holds a duplicated channel number.'))
            return

        verdict_totals = {IDENTICAL: 0, ONE_SIDED: 0}
        for _, _, verdict, _, victims in rows_to_delete:
            verdict_totals[verdict] += len(victims)

        self.stdout.write(
            '%d amp(s) affected. %d row(s) resolvable '
            '(IDENTICAL=%d, ONE-SIDED=%d); %d group(s) skipped as CONFLICTING.'
            % (amps_touched, total_victims, verdict_totals[IDENTICAL],
               verdict_totals[ONE_SIDED], len(skipped)))

        if skipped:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                'Skipped (resolve by hand in the admin, then re-run with '
                '--amp <id> --apply):'))
            for amp, number, rows in skipped:
                self.stdout.write(
                    '    project %d  amp id=%d %r  ch %d  ids=%s'
                    % (amp.project_id, amp.id, amp.name, number,
                       ','.join(str(r.id) for r in rows)))

        if not apply_changes:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                'DRY RUN — nothing was written. Re-run with --apply to delete '
                'the %d row(s) above.' % total_victims))
            return

        if not total_victims:
            self.stdout.write('')
            self.stdout.write(
                'Nothing deletable; every group needs a human.')
            return

        # One transaction for the lot: a half-cleaned amp is harder to reason
        # about than an uncleaned one, and the report command is the thing that
        # tells you where you stand.
        # Counted from the ids asked for rather than from delete()'s return,
        # which totals cascaded rows too and would overstate the figure the
        # moment anything is hung off AmpChannel.
        deleted = 0
        with transaction.atomic():
            for amp, number, verdict, keeper, victims in rows_to_delete:
                ids = [r.id for r in victims]
                amp.channels.filter(id__in=ids).delete()
                deleted += len(ids)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            'Deleted %d redundant AmpChannel row(s) across %d amp(s).'
            % (deleted, amps_touched)))
        self.stdout.write(
            'Re-run report_duplicate_amp_channels to confirm what is left.')
