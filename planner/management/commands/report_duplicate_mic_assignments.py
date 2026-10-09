"""Report MicAssignment rows that share an rf_number, per project and session.

Read-only. Nothing is deleted, renumbered or merged — the point is to show
which sessions are affected, which row of each pair actually holds the
presenter, the notes and the mic'd state, and whether the pair disagrees. The
cleanup is ``cleanup_duplicate_mic_assignments`` (dry-run unless --apply).

Why duplicates exist: ``MicSession.save()`` calls
``create_mic_assignments()``, which writes ``num_mics`` blank ``MicAssignment``
rows. ``Project.duplicate()`` then copied the source session's assignments on
top of that scaffold instead of replacing it, so an 8-mic session duplicated to
16 rows with every rf_number twice — and only half of them holding a
``PresenterSlot``, which is why half the mics in a duplicated show had no A2
card. Same bug as the amp channels in issue #100, one model over.
``duplicate()`` now drops the scaffold before copying, so no new duplicates
appear.

The verdicts (IDENTICAL / ONE-SIDED / CONFLICTING), which row each one would
keep, and the presenter/notes/mic'd protections that can veto a keeper are
defined in ``planner/utils/mic_assignment_dupes.py`` and
``planner/utils/dupe_verdicts.py``. Read those docstrings for the reasoning,
including why "keep the oldest row" is the wrong rule here.

``renumber_mic_assignments`` is a different tool for a different job: it
collapses rf_numbers to a consecutive 1..N, which on a doubled session would
paper over the duplication by renumbering the pairs apart. Clear the duplicates
first, then renumber if you still need to.

Usage:
    python manage.py report_duplicate_mic_assignments
    python manage.py report_duplicate_mic_assignments --project 3
    python manage.py report_duplicate_mic_assignments --session 24
    python manage.py report_duplicate_mic_assignments --conflicting-only
    python manage.py report_duplicate_mic_assignments --show-values

To run it against production, see the "Running the reports against
production" section of CLAUDE.md. Use ``railway ssh`` into the app service —
the report needs no database proxy and no credentials on your laptop.
"""

from django.core.management.base import BaseCommand

from planner.models import MicSession, Project
from planner.utils.mic_assignment_dupes import (
    CONFLICTING, IDENTICAL, ONE_SIDED,
    describe, has_micd_state, has_notes, has_presenter, judge,
)


class Command(BaseCommand):
    help = ("List mic sessions whose MicAssignment rows share an rf_number. "
            "Read-only — changes nothing.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--project', type=int, default=None,
            help='Restrict to a single Project id.',
        )
        parser.add_argument(
            '--session', type=int, default=None,
            help='Restrict to a single MicSession id.',
        )
        parser.add_argument(
            '--conflicting-only', action='store_true',
            help='Only report sessions holding at least one group the cleanup '
                 'cannot decide — CONFLICTING, or vetoed to protect a '
                 'presenter, a note or the mic\'d state.',
        )
        parser.add_argument(
            '--show-values', action='store_true',
            help='Print what every duplicated row holds. Undecidable groups '
                 'print theirs either way.',
        )

    def handle(self, *args, **options):
        projects = Project.objects.all().order_by('id')
        if options['project'] is not None:
            projects = projects.filter(id=options['project'])

        conflicting_only = options['conflicting_only']
        show_values = options['show_values']

        projects_affected = 0
        sessions_affected = 0
        redundant_rows = 0
        resolvable_rows = 0
        verdict_counts = {IDENTICAL: 0, ONE_SIDED: 0, CONFLICTING: 0}
        vetoed = []
        needs_review = []

        for project in projects:
            sessions = (MicSession.objects
                        .filter(day__project=project)
                        .select_related('day')
                        .order_by('day__order', 'day__date', 'order', 'id'))
            if options['session'] is not None:
                sessions = sessions.filter(id=options['session'])

            reports = []
            for session in sessions:
                groups, decisions = judge(session)
                if not groups:
                    continue
                undecidable = any(keeper is None
                                  for _, keeper, _ in decisions.values())
                if conflicting_only and not undecidable:
                    continue
                reports.append((session, groups, decisions))

            if not reports:
                continue

            projects_affected += 1
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING(
                'Project %d: %s' % (project.id, project.name)))
            self.stdout.write('  owner=%s  archived=%s'
                              % (project.owner.username, project.is_archived))

            for session, groups, decisions in reports:
                sessions_affected += 1
                total = session.mic_assignments.count()
                extra = sum(len(rows) - 1 for rows in groups.values())
                redundant_rows += extra

                self.stdout.write(self.style.WARNING(
                    '  session id=%d  %r  (%s)'
                    % (session.id, session.name,
                       session.day.name or session.day.date)))
                self.stdout.write(
                    '    assignments=%d (num_mics=%d)  '
                    'duplicated rf_numbers=[%s]  redundant rows=%d'
                    % (total, session.num_mics,
                       ','.join(str(n) for n in sorted(groups)), extra))

                for number in sorted(groups):
                    rows = groups[number]
                    verdict, keeper, lost = decisions[number]
                    verdict_counts[verdict] += 1
                    if keeper is not None:
                        resolvable_rows += len(rows) - 1

                    if lost:
                        label = '%s  VETOED (would lose %s)' % (
                            verdict, ', '.join(lost))
                        style = self.style.ERROR
                    elif keeper is None:
                        label = verdict
                        style = self.style.ERROR
                    else:
                        label = verdict
                        style = self.style.SUCCESS

                    self.stdout.write(
                        '      rf %-3d x%d  %s%s'
                        % (number, len(rows), style(label),
                           '' if keeper is None
                           else '  -> would keep id=%d' % keeper.id))

                    if show_values or keeper is None:
                        for row in rows:
                            holds = [name for name, test in (
                                ('presenter', has_presenter),
                                ('notes', has_notes),
                                ("mic'd", has_micd_state)) if test(row)]
                            mark = ('  <- keep' if keeper is not None
                                    and row.id == keeper.id else '')
                            self.stdout.write(
                                '          id=%-7d %s%s%s'
                                % (row.id, describe(row),
                                   ('   [holds %s]' % ', '.join(holds))
                                   if holds else '', mark))

                if any(keeper is None for _, keeper, _ in decisions.values()):
                    needs_review.append((project, session))
                for number, (_, keeper, lost) in decisions.items():
                    if lost:
                        vetoed.append((project, session, number, lost))

        self.stdout.write('')
        if not sessions_affected:
            self.stdout.write(self.style.SUCCESS(
                'No sessions with duplicated rf_numbers found.'))
            return

        self.stdout.write(self.style.SUCCESS(
            '%d session(s) across %d project(s) hold duplicated rf_numbers; '
            '%d redundant MicAssignment row(s).'
            % (sessions_affected, projects_affected, redundant_rows)))
        self.stdout.write(
            '  duplicated rf_numbers by verdict: IDENTICAL=%d  ONE-SIDED=%d  '
            'CONFLICTING=%d'
            % (verdict_counts[IDENTICAL], verdict_counts[ONE_SIDED],
               verdict_counts[CONFLICTING]))
        self.stdout.write(
            '  %d of the %d redundant row(s) are mechanically resolvable; '
            '%d need a human.'
            % (resolvable_rows, redundant_rows,
               redundant_rows - resolvable_rows))

        if vetoed:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                '%d group(s) were vetoed to protect something the keeper does '
                'not hold:' % len(vetoed)))
            for project, session, number, lost in vetoed:
                self.stdout.write(
                    '    project %d  session id=%d %r  rf %d  would lose: %s'
                    % (project.id, session.id, session.name, number,
                       ', '.join(lost)))

        if needs_review:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                '%d session(s) hold a group the cleanup will skip:'
                % len(needs_review)))
            for project, session in needs_review:
                self.stdout.write('    project %d  session id=%d  %r'
                                  % (project.id, session.id, session.name))
            self.stdout.write(
                '  Their rows are printed above; fix those by hand in the '
                'Mic Tracker, then re-run the cleanup for that session.')

        self.stdout.write('')
        self.stdout.write(
            'Nothing was changed. cleanup_duplicate_mic_assignments replays '
            'the same verdicts from the same module and is a dry-run unless '
            'given --apply.')
