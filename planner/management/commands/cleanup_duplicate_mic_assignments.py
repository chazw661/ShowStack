"""Proposed cleanup for the MicAssignment rows the MicSession bug left behind.

**Dry-run unless given --apply, and it is not wired into any deploy step.**
Merging this changes nothing: ``railway.json``'s ``startCommand`` does not call
it, so it only ever runs when someone types it. Run
``report_duplicate_mic_assignments`` first and read what it says.

What it does
------------
For each session holding two rows with the same ``rf_number``, keep one and
delete the rest:

  IDENTICAL    the rows hold the same payload (the all-empty case included).
               Keep the **lowest id**.
  ONE-SIDED    exactly one row holds a payload. Keep **that row**, whatever its
               id. This is the expected shape of the bug: the blank scaffold
               row is written first and so has the *lower* id, which is why
               "keep the oldest" would delete the engineer's work.
  CONFLICTING  two or more rows hold payloads and disagree. **Skipped** and
               listed.

On top of the verdict, three things are protected outright — **a presenter, a
note, and the mic'd state.** A row holding the group's only presenter, only
note or only mic'd flag is never deleted, even where the verdict would
otherwise pick a different winner. Such a group is vetoed, reported, and left
exactly as it is. An assignment's presenters and notes live partly in its
``PresenterSlot`` children, and deleting the parent cascades to them, so this
is the difference between a tidy table and a presenter's mic going missing from
a show.

The payload decides whether a rule *can* pick a winner; the veto decides
whether acting on that winner would *destroy* something. See
``planner/utils/mic_assignment_dupes.py``.

Why a command and not a data migration
--------------------------------------
A migration runs itself, once, unattended, inside the deploy, against the one
database with real shows in it, with the undecidable cases resolved by whatever
the code happened to do. This data wants the opposite: read the report, run the
dry-run, then apply deliberately — one session at a time if you like, checking
the Mic Tracker in between. ``renumber_mic_assignments`` is a command for the
same reason.

Not the same tool as renumber_mic_assignments
---------------------------------------------
That one collapses rf_numbers to a consecutive 1..N. Run against a session that
still holds duplicates it would renumber the *pairs* apart — turning eight
doubled mics into sixteen distinctly-numbered ones and hiding the problem for
good. Clear duplicates with this command first; renumber afterwards if needed.

Why not add a unique constraint on (session, rf_number)
------------------------------------------------------
That is the structural fix and the right follow-up — the absence of such a
constraint is what let the double-create write duplicates at all, here and on
``AmpChannel``. But the migration adding it fails while a single duplicate pair
remains, so it has to come after this cleanup has run everywhere and the report
is clean, including the groups only a human can clear. Separate PR, once that
is true. Note that ``renumber_mic_assignments`` exists partly because
rf_numbers have been allowed to collide historically (issue #36), so that
constraint needs its own think.

Usage:
    # Dry-run — prints exactly what --apply would delete, writes nothing:
    python manage.py cleanup_duplicate_mic_assignments

    # One session, or one project, at a time is the recommended way in:
    python manage.py cleanup_duplicate_mic_assignments --session 24
    python manage.py cleanup_duplicate_mic_assignments --session 24 --apply
    python manage.py cleanup_duplicate_mic_assignments --project 3 --apply

    # Everything the rules can decide:
    python manage.py cleanup_duplicate_mic_assignments --apply

To run against production, see the "Running the reports against production"
section of CLAUDE.md — ``railway ssh`` into the app service needs no database
proxy. Take a Railway Postgres backup before using --apply.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import MicSession, Project
from planner.utils.mic_assignment_dupes import (
    CONFLICTING, IDENTICAL, ONE_SIDED,
    describe, judge, numbering_held,
)


class Command(BaseCommand):
    help = ("Delete redundant duplicate MicAssignment rows, keeping the one "
            "carrying the work. Dry-run unless given --apply.")

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
            '--session', type=int, default=None,
            help='Restrict to a single MicSession id — for clearing one '
                 'session by hand after resolving a skipped group.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        sessions = (MicSession.objects
                    .select_related('day', 'day__project')
                    .order_by('day__project_id', 'day__order', 'order', 'id'))
        if options['project'] is not None:
            if not Project.objects.filter(id=options['project']).exists():
                self.stdout.write(self.style.ERROR(
                    'No project with id %d.' % options['project']))
                return
            sessions = sessions.filter(day__project_id=options['project'])
        if options['session'] is not None:
            sessions = sessions.filter(id=options['session'])

        self.stdout.write(self.style.MIGRATE_HEADING(
            'cleanup_duplicate_mic_assignments — %s'
            % ('APPLYING (rows will be deleted)' if apply_changes
               else 'DRY RUN (nothing will be written)')))

        sessions_touched = 0
        rows_to_delete = []      # (session, number, verdict, keeper, victims)
        skipped = []             # (session, number, rows, verdict, lost)

        for session in sessions:
            groups, decisions = judge(session)
            if not groups:
                continue

            lines = []
            for number in sorted(groups):
                rows = groups[number]
                verdict, keeper, lost = decisions[number]

                if keeper is None:
                    skipped.append((session, number, rows, verdict, lost))
                    reason = ('VETOED — would lose %s' % ', '.join(lost)
                              if lost
                              else 'rows hold differing payloads')
                    lines.append(
                        '      rf %-3d x%d  %s  SKIPPED — %s'
                        % (number, len(rows), self.style.ERROR(verdict),
                           reason))
                    continue

                victims = [r for r in rows if r.id != keeper.id]
                rows_to_delete.append(
                    (session, number, verdict, keeper, victims))
                lines.append(
                    '      rf %-3d x%d  %s  keep id=%d (%s), delete %s'
                    % (number, len(rows), self.style.SUCCESS(verdict),
                       keeper.id, describe(keeper),
                       ','.join('id=%d' % r.id for r in victims)))

            if not lines:
                continue

            sessions_touched += 1
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                '  project %d  session id=%d  %r  (%s)'
                % (session.day.project_id, session.id, session.name,
                   session.day.project.name)))
            for text in lines:
                self.stdout.write(text)

        total_victims = sum(len(v) for _, _, _, _, v in rows_to_delete)

        self.stdout.write('')
        if not sessions_touched:
            self.stdout.write(self.style.SUCCESS(
                'Nothing to do — no session holds a duplicated rf_number.'))
            return

        verdict_totals = {IDENTICAL: 0, ONE_SIDED: 0}
        for _, _, verdict, _, victims in rows_to_delete:
            verdict_totals[verdict] += len(victims)

        self.stdout.write(
            '%d session(s) affected. %d row(s) resolvable '
            '(IDENTICAL=%d, ONE-SIDED=%d); %d group(s) skipped.'
            % (sessions_touched, total_victims, verdict_totals[IDENTICAL],
               verdict_totals[ONE_SIDED], len(skipped)))

        if skipped:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                'Skipped (resolve by hand in the Mic Tracker, then re-run '
                'with --session <id> --apply):'))
            for session, number, rows, verdict, lost in skipped:
                self.stdout.write(
                    '    project %d  session id=%d %r  rf %d  %s  ids=%s%s'
                    % (session.day.project_id, session.id, session.name,
                       number, verdict,
                       ','.join(str(r.id) for r in rows),
                       '  (protects %s)' % ', '.join(lost) if lost else ''))

        if not apply_changes:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                'DRY RUN — nothing was written. Re-run with --apply to delete '
                'the %d row(s) above.' % total_victims))
            return

        if not total_victims:
            self.stdout.write('')
            self.stdout.write('Nothing deletable; every group needs a human.')
            return

        # Deleting a MicAssignment cascades to its PresenterSlots -- wanted, the
        # victim's slots go with it -- and fires the issue #36 post_delete
        # receiver, which renumbers the session's surviving rf_numbers. That
        # second part must NOT happen here: it would pull a skipped
        # CONFLICTING pair apart and leave the session looking clean while two
        # rows still mean the same mic. numbering_held() suspends it; its
        # docstring has the full reasoning.
        #
        # One transaction for the lot, so nothing is left half-cleaned, and the
        # receiver is restored even if a delete raises.
        deleted = 0
        with numbering_held(), transaction.atomic():
            for session, number, verdict, keeper, victims in rows_to_delete:
                ids = [r.id for r in victims]
                session.mic_assignments.filter(id__in=ids).delete()
                deleted += len(ids)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            'Deleted %d redundant MicAssignment row(s) across %d session(s).'
            % (deleted, sessions_touched)))
        self.stdout.write(
            'The surviving rows keep the rf_numbers they came from the source '
            'session with; nothing was renumbered and num_mics is untouched.')
        self.stdout.write(
            'Re-run report_duplicate_mic_assignments to confirm what is left. '
            'Only once it reports clean is renumber_mic_assignments safe to '
            'run -- on a session that still holds a duplicate pair it would '
            'renumber the pair apart and hide it.')
