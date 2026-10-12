"""Move per-slot photos up to their presenters, so a photo follows the person.

A DRY RUN unless --apply. The dry run reads every slot photo, decides which
becomes each presenter's headshot, and prints the decisions -- conflicts in
full, with the --choose override to pick a different one. Nothing is written.

The rule (agreed in the presenter-photo proposal), and why each case exists,
is in ``planner/utils/slot_photo_migration.py``. In short: one distinct photo
moves up; several different photos -> the one on the most slots, ties to the
newest slot; a presenter that already has a headshot is skipped unless chosen
or --overwrite; same-name presenters are not merged; nothing crosses projects;
``photo_data`` is left in place as the rollback.

Usage:
    python manage.py migrate_slot_photos_to_presenters                 # dry run
    python manage.py migrate_slot_photos_to_presenters --project 3
    python manage.py migrate_slot_photos_to_presenters --verbose       # every presenter
    python manage.py migrate_slot_photos_to_presenters --apply
    # after reviewing the conflicts, pick a different photo for some:
    python manage.py migrate_slot_photos_to_presenters --choose 41=990 --choose 57=1203 --apply

Against production: ``railway ssh`` into the app service (see CLAUDE.md).
Take a Railway Postgres backup and read the dry run before adding --apply.
"""

from django.core.management.base import BaseCommand, CommandError

from planner.utils.slot_photo_migration import (
    CHOSEN, FROM_FILE, RULE, SINGLE, SKIP_EXISTING, ChoiceError,
    apply_plan, build_plan,
)


def _choice(value):
    try:
        pid, sid = value.split('=', 1)
        return int(pid), int(sid)
    except ValueError:
        raise CommandError(f'--choose expects PRESENTER_ID=SLOT_ID, got {value!r}')


def _kb(n):
    return f'{n / 1024:.0f} KB'


class Command(BaseCommand):
    help = ("Make each presenter's slot photo their headshot, so it shows in "
            "every session they are in. Dry run unless --apply.")

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the headshots. Without it, nothing is written.')
        parser.add_argument('--project', type=int, default=None,
                            help='Restrict to a single Project id.')
        parser.add_argument('--choose', action='append', default=[], metavar='PRESENTER=SLOT',
                            help='Use the photo on SLOT for PRESENTER instead of the rule\'s '
                                 'pick (replaces an existing headshot). Repeatable.')
        parser.add_argument('--overwrite', action='store_true',
                            help='Replace headshots presenters already have. Without it '
                                 'they are left alone.')
        parser.add_argument('--verbose', action='store_true',
                            help='List every presenter\'s decision, not only conflicts.')

    def handle(self, *args, **options):
        choices = dict(_choice(c) for c in options['choose'])
        try:
            plan = build_plan(options['project'], choices, options['overwrite'])
        except ChoiceError as e:
            raise CommandError(str(e))

        w = self.stdout.write
        mode = 'APPLY' if options['apply'] else 'DRY RUN -- nothing written; add --apply'
        w(f'Slot photos -> presenter headshots ({mode})')
        if options['project'] is not None:
            w(f'Project {options["project"]} only')
        w('')

        counts = {}
        for d in plan.decisions:
            counts[d.action] = counts.get(d.action, 0) + 1
        projects = {d.project_id for d in plan.decisions}
        w(f'Slots holding a photo:            {plan.slots_with_photo} '
          f'({plan.distinct_images} distinct images)')
        w(f'Presenters to get a headshot:     {len(plan.to_write)} across {len(projects)} project(s)')
        w(f'  one photo:                      {counts.get(SINGLE, 0)}')
        w(f'  conflict, picked by rule:       {counts.get(RULE, 0)}')
        w(f'  picked with --choose:           {counts.get(CHOSEN, 0)}')
        w(f'  from a surviving photo file:    {counts.get(FROM_FILE, 0)}')
        w(f'Already have a headshot (skip):   {counts.get(SKIP_EXISTING, 0)}')
        w(f'Photo on a slot with no presenter: {len(plan.orphans)}')
        w(f'Skipped, presenter in another project: {len(plan.cross_project)}')
        w(f'Unreadable slot photos:           {len(plan.invalid)}')
        w(f'Presenter.photo files missing:    {len(plan.missing_files)}')
        w(f'Same-name presenter groups (not merged): {len(plan.same_name)}')

        conflicts = [d for d in plan.decisions if d.is_conflict]
        if conflicts:
            w('')
            w(f'CONFLICTS -- presenter has more than one different photo ({len(conflicts)})')
            for d in conflicts:
                self._decision(d)

        if options['verbose']:
            rest = [d for d in plan.decisions if not d.is_conflict]
            if rest:
                w('')
                w('ALL OTHER PRESENTERS')
                for d in rest:
                    self._decision(d)

        if plan.orphans:
            w('')
            w('PHOTO ON A SLOT WITH NO PRESENTER -- left on the slot, still shown there')
            for slot_id, proj, label in plan.orphans:
                w(f'  project {proj} · slot {slot_id} · {label}')
        if plan.cross_project:
            w('')
            w('SKIPPED -- slot and presenter in different projects')
            for slot_id, pid, sp, pp in plan.cross_project:
                w(f'  slot {slot_id} (project {sp}) -> presenter {pid} (project {pp})')
        if plan.invalid:
            w('')
            w('UNREADABLE -- not a JPEG/PNG/WebP this could decode')
            for slot_id, pid, reason in plan.invalid:
                w(f'  slot {slot_id} · presenter {pid} · {reason}')
        if plan.same_name:
            w('')
            w('SAME-NAME PRESENTERS -- not merged; each keeps its own photo')
            for proj, name, members in plan.same_name:
                desc = ', '.join(f'{pid}{" (photo)" if has else ""}' for pid, has in members)
                w(f'  project {proj} · "{name}" · presenters {desc}')

        if not options['apply']:
            w('')
            w('Dry run: nothing written. Re-run with --apply to write the headshots above.')
            return

        written, failures = apply_plan(plan)
        w('')
        w(f'Wrote {written} headshot(s).')
        for pid, err in failures:
            self.stderr.write(f'  FAILED presenter {pid}: {err}')
        if failures:
            raise CommandError(f'{len(failures)} presenter(s) failed; the rest were written.')

    def _decision(self, d):
        w = self.stdout.write
        w(f'  project {d.project_id} "{d.project_name}" · presenter {d.presenter_id} '
          f'"{d.presenter_name}" -> {d.action}')
        if d.action == FROM_FILE:
            w(f'      file {d.file_name}')
            return
        for c in d.candidates:
            mark = '*' if (d.chosen is c and d.action != SKIP_EXISTING) else ' '
            uses = len(c.slot_ids)
            w(f'    {mark} slot {c.newest_slot:<6} {c.mime:<10} {_kb(c.size):>7}  '
              f'on {uses} slot{"s" if uses != 1 else ""}: '
              + '; '.join(f'{sid} ({lbl})' for sid, lbl in zip(c.slot_ids, c.labels)))
        if d.is_conflict:
            others = [c for c in d.candidates if c is not d.chosen]
            w(f'      to use another: ' + ' or '.join(
                f'--choose {d.presenter_id}={c.newest_slot}' for c in others))
