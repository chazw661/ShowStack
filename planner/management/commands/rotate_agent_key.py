"""Give one project a new network monitor agent key.

**Dry-run unless given --apply, and it is not wired into any deploy step.**

Why: until #147 the Network Monitor page showed the project's agent key to
every member, viewers included, and the key is a Bearer token for the agent
endpoints, which write (device lists, scan results). The page now shows it to
owners and editors only, but a key a viewer has already seen keeps working
until it is replaced. This replaces it.

After --apply the old key stops working at once, so the project's running
agent loses access until it is restarted with the new key. The owner reads the
new key (and the full agent command) on the Network Monitor page. The key is
not printed here, so it doesn't end up in a terminal or a log.

Usage:
    # Dry-run: names the project and what would happen, changes nothing:
    python manage.py rotate_agent_key --project 3

    python manage.py rotate_agent_key --project 3 --apply

    # against prod (see "Running management commands against prod" in
    # CLAUDE.md for the gotchas):
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py rotate_agent_key --project 3 --apply
"""

import uuid

from django.core.management.base import BaseCommand, CommandError

from planner.models import Project


class Command(BaseCommand):
    help = ("Replace a project's network monitor agent key. "
            "Dry-run unless given --apply.")

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, required=True,
                            help='The Project id whose key is replaced.')
        parser.add_argument('--apply', action='store_true',
                            help='Write the new key. Without it nothing changes.')

    def handle(self, *args, project, apply, **options):
        try:
            target = Project.objects.select_related('owner').get(pk=project)
        except Project.DoesNotExist:
            raise CommandError(f'No project with id {project}.')

        label = f'project {target.pk} "{target.name}" (owner {target.owner})'
        if not apply:
            self.stdout.write(
                f'Dry-run: would replace the agent key of {label}. Its running '
                f'agent would need restarting with the new key. Add --apply to do it.')
            return

        target.agent_api_key = uuid.uuid4()
        target.save(update_fields=['agent_api_key'])
        self.stdout.write(self.style.SUCCESS(
            f'Replaced the agent key of {label}. The old key no longer works; '
            f'the new one is on the Network Monitor page for the owner and editors.'))
