"""Report Presenter rows that are the same person twice, per project.

Read-only. Nothing is deleted, merged or renamed — the point is to show
Charlie what is already in each roster so the merges can be decided by hand.

Why duplicates exist: every assign/rename path used to call
Presenter.objects.get_or_create(name=..., project_id=...), which matches the
name EXACTLY, so "Jane Doe", "jane doe" and "Jane  Doe" each minted a new
Presenter. Presenter.resolve() now matches case-insensitively (and collapses
whitespace), so no new ones appear — but the existing ones stay until someone
looks at them, which is what this command is for.

Two rows are reported as duplicates when their names match after
casefolding and collapsing runs of whitespace. Project.duplicate() also used
to run its presenter-copy loop twice, so a duplicated project can hold two
EXACT copies of every presenter; those show up here as well.

Usage:
    python manage.py list_duplicate_presenters
    python manage.py list_duplicate_presenters --project 3
    python manage.py list_duplicate_presenters --exact-only   # same spelling
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count

from planner.models import Presenter, Project


def normalise(name):
    """The key two Presenter rows collide on: case- and spacing-insensitive."""
    return ' '.join((name or '').split()).casefold()


class Command(BaseCommand):
    help = "List duplicate Presenter rows per project. Read-only — deletes nothing."

    def add_arguments(self, parser):
        parser.add_argument(
            '--project', type=int, default=None,
            help='Restrict to a single Project id.',
        )
        parser.add_argument(
            '--exact-only', action='store_true',
            help='Only report rows whose names match exactly (ignore '
                 'case/spacing-only collisions).',
        )

    def handle(self, *args, **options):
        project_id = options['project']
        exact_only = options['exact_only']

        projects = Project.objects.all().order_by('id')
        if project_id is not None:
            projects = projects.filter(id=project_id)

        total_groups = 0
        total_extra_rows = 0
        projects_affected = 0

        for project in projects:
            presenters = Presenter.objects.filter(project=project).annotate(
                slot_count=Count('slots', distinct=True),
                shared_count=Count('shared_assignments', distinct=True),
            ).order_by('id')

            groups = defaultdict(list)
            for p in presenters:
                key = p.name if exact_only else normalise(p.name)
                groups[key].append(p)

            dupes = {k: v for k, v in groups.items() if len(v) > 1}
            if not dupes:
                continue

            projects_affected += 1
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'Project {project.id}: {project.name}'
            ))

            for key in sorted(dupes, key=lambda k: dupes[k][0].name.lower()):
                rows = dupes[key]
                total_groups += 1
                total_extra_rows += len(rows) - 1

                # The oldest row is the one Presenter.resolve() now hands back,
                # so it is the natural merge target — say so explicitly rather
                # than leaving it to be inferred from the id order.
                keeper = rows[0]
                self.stdout.write(self.style.WARNING(
                    f'  {len(rows)}x "{rows[0].name}"'
                ))
                for p in rows:
                    marks = []
                    if p.id == keeper.id:
                        marks.append('← resolve() returns this one')
                    if p.photo:
                        marks.append('has photo')
                    if (p.notes or '').strip():
                        marks.append('has notes')
                    suffix = ('   ' + ', '.join(marks)) if marks else ''
                    self.stdout.write(
                        f'    id={p.id:<6} name={p.name!r:<30} '
                        f'slots={p.slot_count:<3} shared={p.shared_count:<3} '
                        f'created={p.created_at:%Y-%m-%d %H:%M}{suffix}'
                    )

        self.stdout.write('')
        if not total_groups:
            self.stdout.write(self.style.SUCCESS(
                'No duplicate presenters found.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'{total_groups} duplicate name(s) across {projects_affected} '
            f'project(s); {total_extra_rows} redundant Presenter row(s).'
        ))
        self.stdout.write(
            'Nothing was changed. Rows with slots= or shared= above 0 are in '
            'use, so repoint those slots before retiring a row.'
        )
