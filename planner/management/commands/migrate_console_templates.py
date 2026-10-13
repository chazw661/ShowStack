"""Copy every legacy template console (is_template=True) into a ShowTemplate.

DRY-RUN BY DEFAULT. Without ``--apply`` this reads and prints the plan and
writes nothing -- no rows, no rollback-after-write. Read the dry run, take a
Railway Postgres backup, then run again with ``--apply``.

For each Console with is_template=True:

* create a ShowTemplate(kind='console') owned by the console's project owner,
  with source_project set to that project;
* name it after the console, or "<console> (<project>)" if the owner already
  has a console template by that name, then numbered if THAT is taken too;
* copy the full console -- every input/aux/matrix/stereo field, IPs and the
  location by name -- through planner.show_templates;
* set the console's is_template to False.

What it NEVER does: remove, move or edit the console beyond that one flag.
Most consoles ticked as templates on prod are live show consoles (20 of 25
when this was written), so the console stays exactly where it is; the
template is a copy. The is_template column itself is dropped in a later PR.

A console with no project has no owner to give the template to; it is
reported and skipped. Each console is converted in its own transaction, and
a converted console no longer has is_template set, so re-running after a
partial failure picks up where it stopped and never makes a second copy.

Usage:
    python manage.py migrate_console_templates            # dry run
    python manage.py migrate_console_templates --apply

    # against prod (see CLAUDE.md "Running management commands against prod"):
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py migrate_console_templates
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import Console, ShowTemplate
from planner.show_templates import save_console_template, unique_template_name


class Command(BaseCommand):
    help = ("Copy is_template consoles into owner-scoped ShowTemplates. "
            "Dry-run unless --apply is given.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the templates and clear is_template. Without it, '
                 'nothing is written.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        consoles = (
            Console.objects.filter(is_template=True)
            .select_related('project', 'project__owner', 'location')
            .order_by('project__owner_id', 'project_id', 'id')
        )

        self.stdout.write(
            ('APPLYING' if apply else 'DRY RUN -- nothing will be written')
            + f": {consoles.count()} template console(s)\n"
        )

        # Names planned this run but not written yet, per owner, so a dry run
        # reports the same suffixes --apply will choose.
        planned = defaultdict(set)
        converted = skipped = 0

        for console in consoles:
            project = console.project
            label = f"console #{console.id} '{console.name}'"
            if project is None:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP {label}: no project, so no owner to give it to"))
                skipped += 1
                continue

            owner = project.owner
            name = unique_template_name(
                owner, ShowTemplate.KIND_CONSOLE, console.name,
                alternate=f"{console.name} ({project.name})",
                taken=planned[owner.id],
            )
            planned[owner.id].add(name)
            counts = (
                f"{console.consoleinput_set.count()} in, "
                f"{console.consoleauxoutput_set.count()} aux, "
                f"{console.consolematrixoutput_set.count()} mtx, "
                f"{console.consolestereooutput_set.count()} st"
            )
            renamed = '' if name == console.name else '  [renamed]'
            self.stdout.write(
                f"  {label} in project #{project.id} '{project.name}' "
                f"-> template '{name}' for {owner.username} ({counts}){renamed}"
            )

            if apply:
                with transaction.atomic():
                    save_console_template(console, owner, name)
                    # update(), not save(): the flag is the only thing that
                    # changes, and the console row is otherwise left alone.
                    Console.objects.filter(pk=console.pk).update(is_template=False)
            converted += 1

        verb = 'Converted' if apply else 'Would convert'
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb} {converted} console(s); skipped {skipped}. "
            "No console was removed from its project."
        ))
        if not apply and converted:
            self.stdout.write("Re-run with --apply to write.")
