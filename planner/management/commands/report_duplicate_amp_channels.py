"""Report AmpChannel rows that share a channel_number, per project.

Read-only. Nothing is deleted, renumbered or merged — the point is to show
which racks are affected and whether the duplicated pairs actually disagree,
so the cleanup can be decided with the numbers in front of you. The cleanup
itself is ``cleanup_duplicate_amp_channels`` (dry-run unless given --apply).

Why duplicates exist: ``Amp.save()`` calls ``setup_channels()``, which builds
one blank ``AmpChannel`` per channel the amp model declares.
``Project.duplicate()`` then copied the source amp's channels on top of that
scaffold instead of replacing it, so a duplicated 4-channel LA12X ended up with
8 rows numbered 1,1,2,2,3,3,4,4 — half blank, half the real patch (issue #100).
``duplicate()`` now drops the scaffold before copying, so no new duplicates
appear; the rows written by earlier duplications stay until someone looks at
them, which is what this command is for.

The verdicts (IDENTICAL / ONE-SIDED / CONFLICTING), and which row each one
would keep, are defined in ``planner/utils/amp_channel_dupes.py`` — read that
module's docstring for the reasoning, including why "keep the oldest row" is
the wrong rule here.

Usage:
    python manage.py report_duplicate_amp_channels
    python manage.py report_duplicate_amp_channels --project 3
    python manage.py report_duplicate_amp_channels --conflicting-only
    python manage.py report_duplicate_amp_channels --show-values

    # against prod — runs inside the app container, so it needs no database
    # proxy and no credentials on your laptop (see the "Running management
    # commands against prod" section of CLAUDE.md for the gotchas):
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py report_duplicate_amp_channels
"""

from django.core.management.base import BaseCommand

from planner.models import Amp, Project
from planner.utils.amp_channel_dupes import (
    CONFLICTING, IDENTICAL, ONE_SIDED, PATCH_FIELDS,
    is_blank, judge, keeper_of, patch_of,
)


class Command(BaseCommand):
    help = ("List amps whose AmpChannel rows share a channel_number. "
            "Read-only — changes nothing.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--project', type=int, default=None,
            help='Restrict to a single Project id.',
        )
        parser.add_argument(
            '--conflicting-only', action='store_true',
            help='Only report amps holding at least one CONFLICTING group — '
                 'the ones the cleanup cannot decide on its own.',
        )
        parser.add_argument(
            '--show-values', action='store_true',
            help="Print every duplicated row's patch values. CONFLICTING "
                 'groups print theirs either way.',
        )

    def handle(self, *args, **options):
        projects = Project.objects.all().order_by('id')
        if options['project'] is not None:
            projects = projects.filter(id=options['project'])

        conflicting_only = options['conflicting_only']
        show_values = options['show_values']

        projects_affected = 0
        amps_affected = 0
        redundant_rows = 0
        resolvable_rows = 0
        verdict_counts = {IDENTICAL: 0, ONE_SIDED: 0, CONFLICTING: 0}
        needs_review = []

        for project in projects:
            amps = (Amp.objects
                    .filter(project=project)
                    .select_related('amp_model', 'location')
                    .order_by('location__sort_order', 'sort_order', 'id'))

            reports = []
            for amp in amps:
                groups, verdicts = judge(amp)
                if not groups:
                    continue
                if conflicting_only and CONFLICTING not in verdicts.values():
                    continue
                reports.append((amp, groups, verdicts))

            if not reports:
                continue

            projects_affected += 1
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING(
                'Project %d: %s' % (project.id, project.name)))
            self.stdout.write('  owner=%s  archived=%s'
                              % (project.owner.username, project.is_archived))

            for amp, groups, verdicts in reports:
                amps_affected += 1
                total = amp.channels.count()
                extra = sum(len(rows) - 1 for rows in groups.values())
                redundant_rows += extra
                for number, verdict in verdicts.items():
                    verdict_counts[verdict] += 1
                    if verdict != CONFLICTING:
                        resolvable_rows += len(groups[number]) - 1

                declared = (amp.amp_model.channel_count
                            if amp.amp_model_id else None)
                expected = ('%d' % declared if declared is not None
                            else 'n/a (no model)')

                self.stdout.write(self.style.WARNING(
                    '  amp id=%d  %r' % (amp.id, amp.name)))
                self.stdout.write(
                    '    location=%s  model=%s'
                    % (amp.location.name if amp.location_id else '-',
                       amp.amp_model if amp.amp_model_id else '(none)'))
                self.stdout.write(
                    '    channels=%d (model declares %s)  '
                    'duplicated numbers=[%s]  redundant rows=%d'
                    % (total, expected,
                       ','.join(str(n) for n in sorted(groups)), extra))

                for number in sorted(groups):
                    rows = groups[number]
                    verdict = verdicts[number]
                    keeper = keeper_of(rows, verdict)
                    style = (self.style.ERROR if verdict == CONFLICTING
                             else self.style.SUCCESS)
                    self.stdout.write(
                        '      ch %-3d x%d  %s%s'
                        % (number, len(rows), style(verdict),
                           '' if keeper is None
                           else '  -> would keep id=%d' % keeper.id))

                    if show_values or verdict == CONFLICTING:
                        for row in rows:
                            patch = patch_of(row)
                            if is_blank(patch):
                                rendered = 'blank'
                            else:
                                rendered = '  '.join(
                                    '%s=%r' % (f, v)
                                    for f, v in zip(PATCH_FIELDS, patch) if v)
                            mark = ('  <- keep' if keeper is not None
                                    and row.id == keeper.id else '')
                            self.stdout.write('          id=%-7d %s%s'
                                              % (row.id, rendered, mark))

                if CONFLICTING in verdicts.values():
                    needs_review.append((project, amp))

        self.stdout.write('')
        if not amps_affected:
            self.stdout.write(self.style.SUCCESS(
                'No amps with duplicated channel numbers found.'))
            return

        self.stdout.write(self.style.SUCCESS(
            '%d amp(s) across %d project(s) hold duplicated channel numbers; '
            '%d redundant AmpChannel row(s).'
            % (amps_affected, projects_affected, redundant_rows)))
        self.stdout.write(
            '  duplicated numbers by verdict: IDENTICAL=%d  ONE-SIDED=%d  '
            'CONFLICTING=%d'
            % (verdict_counts[IDENTICAL], verdict_counts[ONE_SIDED],
               verdict_counts[CONFLICTING]))
        self.stdout.write(
            '  %d of the %d redundant row(s) are mechanically resolvable; '
            '%d sit in CONFLICTING groups and need a human.'
            % (resolvable_rows, redundant_rows,
               redundant_rows - resolvable_rows))

        if needs_review:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                '%d amp(s) hold a CONFLICTING group — both rows were edited '
                'after the duplication, so no rule picks a winner:'
                % len(needs_review)))
            for project, amp in needs_review:
                self.stdout.write('    project %d  amp id=%d  %r'
                                  % (project.id, amp.id, amp.name))
            self.stdout.write(
                '  Their values are printed above; fix those by hand in the '
                'admin. The cleanup command skips them.')

        self.stdout.write('')
        self.stdout.write(
            'Nothing was changed. cleanup_duplicate_amp_channels replays the '
            'same verdicts from the same module and is a dry-run unless given '
            '--apply.')
