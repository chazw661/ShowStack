"""Export every Signal Flow Diagram's canvas to JSON. Never writes the database.

The Signal Flow Diagrammer is retired: its editor, routes and admin are gone,
and a later PR drops the model. This is the backup of what users drew.

Modes:
    (default)              dry run -- per project: owner, diagram count, latest
                           edit. Writes nothing anywhere.
    --apply --stdout       one JSON bundle of every diagram on stdout (the
                           summary goes to stderr). Writes no file.
    --apply [--out-dir D]  one file per diagram, D/<project id>/<diagram id>-
                           <name>.json. Refuses to overwrite unless --force.

Each diagram carries: project_id, project_name, owner, diagram_id, name,
created_at, updated_at, version, canvas_state, viewport.

Usage:
    python manage.py export_signal_flow_diagrams
    python manage.py export_signal_flow_diagrams --project 3
    python manage.py export_signal_flow_diagrams --apply --out-dir sfd-export

    # against prod: the container's disk is wiped on every redeploy, so take
    # the bundle off it on stdout rather than writing files there
    # (see CLAUDE.md, "Running management commands against prod"):
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py export_signal_flow_diagrams --apply --stdout \\
      > sfd-export.json
"""
import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from planner.models import SignalFlowDiagram


def as_dict(diagram):
    project = diagram.project
    return {
        'project_id': project.pk,
        'project_name': project.name,
        'owner': project.owner.username if project.owner_id else None,
        'diagram_id': diagram.pk,
        'name': diagram.name,
        'created_at': diagram.created_at.isoformat() if diagram.created_at else None,
        'updated_at': diagram.updated_at.isoformat() if diagram.updated_at else None,
        'version': diagram.version,
        'canvas_state': diagram.canvas_state,
        'viewport': diagram.viewport,
    }


def file_name(diagram):
    """``<diagram id>-<name>.json``. The id keeps names that slugify alike
    (or to nothing, e.g. non-Latin text) from colliding."""
    slug = slugify(diagram.name)[:60] or 'diagram'
    return f'{diagram.pk}-{slug}.json'


class Command(BaseCommand):
    help = ("Export Signal Flow Diagrams to JSON. Dry run unless --apply; "
            "never writes the database.")

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the export (files, or stdout with --stdout).')
        parser.add_argument('--stdout', action='store_true', dest='to_stdout',
                            help='With --apply: print one JSON bundle instead of writing files.')
        parser.add_argument('--out-dir', default='signal_flow_export',
                            help='With --apply: directory for the files '
                                 '(default: signal_flow_export).')
        parser.add_argument('--force', action='store_true',
                            help='With --apply: overwrite files that already exist.')
        parser.add_argument('--project', type=int, default=None,
                            help='Restrict to a single Project id.')

    def handle(self, *args, **options):
        if options['to_stdout'] and not options['apply']:
            raise CommandError('--stdout writes the export; add --apply.')

        diagrams = (SignalFlowDiagram.objects
                    .select_related('project__owner')
                    .order_by('project_id', 'id'))
        if options['project'] is not None:
            diagrams = diagrams.filter(project_id=options['project'])
        diagrams = list(diagrams)

        # With --stdout, stdout carries only the JSON bundle.
        report = self.stderr if options['to_stdout'] else self.stdout
        self._summary(report, diagrams)

        if not options['apply']:
            report.write('Dry run: nothing written. Add --apply (with --stdout '
                         'or --out-dir) to export.')
            return

        if options['to_stdout']:
            bundle = {'exported_at': timezone.now().isoformat(),
                      'count': len(diagrams),
                      'diagrams': [as_dict(d) for d in diagrams]}
            self.stdout.write(json.dumps(bundle, indent=2, ensure_ascii=False))
            report.write('Wrote %d diagram(s) to stdout.' % len(diagrams))
            return

        out = Path(options['out_dir'])
        targets = [(d, out / str(d.project_id) / file_name(d)) for d in diagrams]
        existing = [str(path) for _, path in targets if path.exists()]
        if existing and not options['force']:
            raise CommandError('Refusing to overwrite (add --force): ' + ', '.join(existing))
        for diagram, path in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(as_dict(diagram), indent=2, ensure_ascii=False) + '\n',
                            encoding='utf-8')
        report.write('Wrote %d file(s) under %s' % (len(targets), out))

    def _summary(self, report, diagrams):
        by_project = defaultdict(list)
        for d in diagrams:
            by_project[d.project_id].append(d)
        for rows in by_project.values():
            project = rows[0].project
            owner = project.owner.username if project.owner_id else '-'
            latest = max(d.updated_at for d in rows)
            report.write('project %-5d %-30r owner=%-20s diagrams=%-3d latest edit %s'
                         % (project.pk, project.name, owner, len(rows),
                            latest.isoformat() if latest else '-'))
        owners = {rows[0].project.owner_id for rows in by_project.values()}
        report.write('%d diagram(s) in %d project(s), %d owner(s).'
                     % (len(diagrams), len(by_project), len(owners)))
