"""One-shot cleanup for issue #36's aborted insert-above/below feature.

Walks every MicSession and renumbers its MicAssignment rows to a clean
consecutive 1..N (preserving current rf_number / id ordering so the
visual sequence stays the same). Also syncs MicSession.num_mics to the
actual row count so create_mic_assignments doesn't later resurrect or
prune rows.

Usage:
    # Dry-run — show which sessions would change, no writes:
    railway run python manage.py renumber_mic_assignments

    # Apply changes:
    railway run python manage.py renumber_mic_assignments --apply

    # Limit to one session:
    railway run python manage.py renumber_mic_assignments --session 24 --apply
"""

from django.core.management.base import BaseCommand

from planner.models import MicSession


class Command(BaseCommand):
    help = "Renumber MicAssignment.rf_number per session to consecutive 1..N."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually save changes. Without this flag the command is a dry-run.',
        )
        parser.add_argument(
            '--session', type=int, default=None,
            help='Restrict to a single MicSession id.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        session_id = options['session']

        qs = MicSession.objects.all()
        if session_id is not None:
            qs = qs.filter(id=session_id)

        total_sessions = 0
        changed_sessions = 0
        total_rows_changed = 0

        for session in qs.order_by('id'):
            total_sessions += 1
            assignments = list(
                session.mic_assignments.order_by('rf_number', 'id')
            )
            if not assignments:
                continue

            current = [a.rf_number for a in assignments]
            desired = list(range(1, len(assignments) + 1))
            if current == desired and session.num_mics == len(assignments):
                continue

            changed_sessions += 1
            self.stdout.write(self.style.WARNING(
                f"Session {session.id} ({session.name!r}): "
                f"rf_numbers {current} -> {desired}; "
                f"num_mics {session.num_mics} -> {len(assignments)}"
            ))

            if apply_changes and session.renumber_assignments():
                total_rows_changed += len(assignments)

        verb = "renumbered" if apply_changes else "would renumber"
        self.stdout.write(self.style.SUCCESS(
            f"Scanned {total_sessions} session(s); {verb} {changed_sessions}."
        ))
        if apply_changes:
            self.stdout.write(self.style.SUCCESS(
                f"Touched {total_rows_changed} MicAssignment row(s)."
            ))
        else:
            self.stdout.write("Re-run with --apply to persist the changes above.")
