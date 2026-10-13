"""Sort presenters into people and mic positions, and place their photos.

A DRY RUN unless --apply. The dry run reads every slot photo, classifies every
presenter, and prints the result project by project -- with the override that
would change each decision. Nothing is written.

The rule, and why each case exists, is in
``planner/utils/slot_photo_migration.py``. In short: a mic-position name
(HH13, Q&A 2, A2 OS) or different photos in different sessions -> mic label,
every slot photo stays per session; one photo, or re-uploads of one -> that
person's headshot for every session. Slot photos are never cleared.

Usage:
    python manage.py migrate_slot_photos_to_presenters                 # dry run
    python manage.py migrate_slot_photos_to_presenters --project 3
    python manage.py migrate_slot_photos_to_presenters --verbose       # + people with no photo
    # correct what the dry run got wrong, check it again, then apply:
    python manage.py migrate_slot_photos_to_presenters --person 172 --label 41 --skip 57
    python manage.py migrate_slot_photos_to_presenters --choose 168=103 --apply

Overrides take presenter ids and are repeatable or comma-separated.

Against production: ``railway ssh`` into the app service (see CLAUDE.md).
Take a Railway Postgres backup and read the dry run before adding --apply.
Re-running applies the classification again, so carry the overrides along.
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from planner.utils import slot_photo_migration as spm


def _ids(values):
    out = set()
    for v in values:
        for part in str(v).split(','):
            part = part.strip()
            if not part:
                continue
            try:
                out.add(int(part))
            except ValueError:
                raise CommandError(f'expected a presenter id, got {part!r}')
    return out


def _choice(value):
    try:
        pid, sid = value.split('=', 1)
        return int(pid), int(sid)
    except ValueError:
        raise CommandError(f'--choose expects PRESENTER_ID=SLOT_ID, got {value!r}')


def _kb(n):
    return f'{n / 1024:.0f} KB'


# The one-word tag in the listing, and the override that flips the decision.
def _tag(d):
    return 'SKIP  ' if d.kind == spm.SKIP else ('LABEL ' if d.is_label else 'PERSON')


def _flip_hint(d):
    pid = d.presenter.id
    if d.kind == spm.SKIP:
        return ''
    if d.is_label:
        return f'--person {pid}'
    return f'--label {pid}'


def write_report(plan, write, verbose=False, applying=False, project=None):
    w = write
    mode = 'APPLY' if applying else 'DRY RUN -- nothing written; add --apply'
    w(f'Presenters: people and mic positions, and their photos ({mode})')
    if project is not None:
        w(f'Project {project} only')
    w('')

    counts = Counter(d.kind for d in plan.decisions)
    labels = [d for d in plan.decisions if d.is_label]
    w(f'Slots holding a photo:               {plan.slots_with_photo} '
      f'({plan.distinct_images} distinct images)')
    w(f'Presenters:                          {len(plan.decisions)}')
    w(f'MIC LABELS -- photos stay per session: {len(labels)} '
      f'({sum(1 for d in labels if d.candidates)} with photos, '
      f'{sum(len(c.slot_ids) for d in labels for c in d.candidates)} slot photos kept as session photos)')
    w(f'  name looks like a mic position:    {counts[spm.LABEL_NAME]}')
    w(f'  different photos in different sessions: {counts[spm.LABEL_PHOTOS]}')
    w(f'  --label:                           {counts[spm.LABEL_FORCED]}')
    w(f'  already flagged:                   {counts[spm.LABEL_ALREADY]}')
    w(f'PEOPLE -- headshot for every session: {len(plan.headshots_to_write)}')
    w(f'  one photo:                         {counts[spm.PERSON_SINGLE]}')
    w(f'  re-uploads of one photo:           {counts[spm.PERSON_NEAR]}')
    w(f'  --choose:                          {counts[spm.PERSON_CHOSEN]}')
    w(f'  --person:                          {counts[spm.PERSON_FORCED]}')
    w(f'  from a surviving photo file:       {counts[spm.PERSON_FILE]}')
    w(f'People keeping the headshot they have: {counts[spm.PERSON_KEEPS_HEADSHOT]}')
    w(f'People with no photo (nothing to do): {counts[spm.PERSON_NO_PHOTO]}'
      + ('' if verbose else '  (listed with --verbose)'))
    w(f'Skipped with --skip:                 {counts[spm.SKIP]}')
    w(f'is_mic_label changes:                {len(plan.flags_to_set)}')
    w(f'Photo on a slot with no presenter:   {len(plan.orphans)}')
    w(f'Presenter in another project:        {len(plan.cross_project)}')
    w(f'Unreadable slot photos:              {len(plan.invalid)}')
    w(f'Presenter.photo files missing:       {len(plan.missing_files)}')
    w(f'Same-name presenter groups (not merged): {len(plan.same_name)}')

    w('')
    w('EVERY PRESENTER, BY PROJECT  (* = the photo that becomes the headshot)')
    project_id = None
    for d in plan.decisions:
        if d.kind == spm.PERSON_NO_PHOTO and not verbose:
            continue
        p = d.presenter
        if p.project_id != project_id:
            project_id = p.project_id
            w('')
            w(f'Project {p.project_id} "{p.project_name}"')
        hint = _flip_hint(d)
        n_slots = sum(len(c.slot_ids) for c in d.candidates)
        if d.candidates:
            photos = (f'{len(d.candidates)} photo{"s" if len(d.candidates) != 1 else ""} '
                      f'on {n_slots} slot{"s" if n_slots != 1 else ""}')
            if len(d.candidates) > 1:
                photos += f', fingerprints up to {d.spread} bits apart'
        elif d.kind == spm.PERSON_FILE:
            photos = f'file {p.photo_file}'
        else:
            photos = 'no photo'
        w(f'  {_tag(d)} {p.id:>5}  {p.name[:40]:<40}  {d.kind:<32} {photos}'
          + (f'   [{hint}]' if hint else ''))
        # Every photo is listed when there is more than one, or when the
        # presenter is a label: that is what someone checking needs to see.
        if len(d.candidates) > 1 or (d.is_label and d.candidates):
            for c in d.candidates:
                mark = '*' if c is d.chosen else ' '
                w(f'        {mark} slot {c.newest_slot:<6} {c.mime:<10} {_kb(c.size):>7}  '
                  f'on {len(c.slot_ids)}: '
                  + '; '.join(f'{sid} ({lbl})' for sid, lbl in zip(c.slot_ids, c.labels)))
            if not d.is_label and len(d.candidates) > 1:
                others = [c for c in d.candidates if c is not d.chosen]
                w('          other photo: ' + ' or '.join(
                    f'--choose {p.id}={c.newest_slot}' for c in others))
        elif d.candidates:
            c = d.candidates[0]
            w(f'        * slot {c.newest_slot:<6} {c.mime:<10} {_kb(c.size):>7}  on {len(c.slot_ids)}: '
              + '; '.join(f'{sid} ({lbl})' for sid, lbl in zip(c.slot_ids, c.labels)))

    if plan.orphans:
        w('')
        w('PHOTO ON A SLOT WITH NO PRESENTER -- stays on the slot as its session photo')
        for r in plan.orphans:
            w(f'  project {r.slot_project_id} · slot {r.slot_id} · {r.label}')
    if plan.cross_project:
        w('')
        w('SKIPPED -- slot and presenter in different projects')
        for r in plan.cross_project:
            w(f'  slot {r.slot_id} (project {r.slot_project_id}) -> presenter '
              f'{r.presenter_id} (project {r.presenter_project_id})')
    if plan.invalid:
        w('')
        w('UNREADABLE -- not a JPEG/PNG/WebP this could decode; left on the slot')
        for r in plan.invalid:
            w(f'  slot {r.slot_id} · presenter {r.presenter_id} · {r.error}')
    if plan.missing_files:
        w('')
        w('PRESENTER.PHOTO FILE MISSING -- lost in an old redeploy; needs re-uploading')
        for p in plan.missing_files:
            w(f'  project {p.project_id} · presenter {p.id} "{p.name}" · {p.photo_file}')
    if plan.same_name:
        w('')
        w('SAME-NAME PRESENTERS -- not merged; each keeps its own photos')
        for proj, name, group in plan.same_name:
            desc = ', '.join(f'{d.presenter.id} ({"label" if d.is_label else "person"}'
                             f'{", photo" if d.has_photos else ""})' for d in group)
            w(f'  project {proj} · "{name}" · {desc}')


class Command(BaseCommand):
    help = ("Classify presenters as people or mic positions; give people a "
            "headshot for every session and keep mic positions' photos per "
            "session. Dry run unless --apply.")

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write it. Without it, nothing is written.')
        parser.add_argument('--project', type=int, default=None,
                            help='Restrict to a single Project id.')
        parser.add_argument('--skip', action='append', default=[], metavar='ID',
                            help='Leave this presenter exactly as it is.')
        parser.add_argument('--label', action='append', default=[], metavar='ID',
                            help='Treat as a mic position: photos stay per session.')
        parser.add_argument('--person', action='append', default=[], metavar='ID',
                            help='Treat as a person: headshot from the photo on the most slots.')
        parser.add_argument('--choose', action='append', default=[], metavar='PRESENTER=SLOT',
                            help='A person, with the photo on SLOT as the headshot '
                                 '(replaces an existing one).')
        parser.add_argument('--overwrite', action='store_true',
                            help='Replace headshots people already have.')
        parser.add_argument('--verbose', action='store_true',
                            help='Also list people with no photo.')

    def handle(self, *args, **options):
        overrides = spm.Overrides(
            skip=_ids(options['skip']), label=_ids(options['label']),
            person=_ids(options['person']),
            choose=dict(_choice(c) for c in options['choose']),
            overwrite=options['overwrite'],
        )
        try:
            plan = spm.build_plan(options['project'], overrides)
        except spm.ChoiceError as e:
            raise CommandError(str(e))

        write_report(plan, self.stdout.write, verbose=options['verbose'],
                     applying=options['apply'], project=options['project'])

        if not options['apply']:
            self.stdout.write('')
            self.stdout.write('Dry run: nothing written. Re-run with --apply (and the same '
                              'overrides) to write the above.')
            return

        flags, headshots, failures = spm.apply_plan(plan)
        self.stdout.write('')
        self.stdout.write(f'Set is_mic_label on {flags} presenter(s); wrote {headshots} headshot(s).')
        for pid, err in failures:
            self.stderr.write(f'  FAILED presenter {pid}: {err}')
        if failures:
            raise CommandError(f'{len(failures)} presenter(s) failed; the rest were written.')
