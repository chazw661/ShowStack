"""Merge AmpModel rows that are the same model under different spellings.

**Dry-run unless given --apply, and it is not wired into any deploy step.**

The AmpModel catalogue is shared by every account, and before the add form
started offering the existing row it collected duplicates such as
"L-Acoustics LA12X" ×2 plus "LA LA12X", and "Lacoustics LA8-2" ×2. Rows are
the same model when ``planner.utils.amp_models.model_key`` says so: case,
spaces and punctuation ignored, manufacturer abbreviations read in full.

For each group of duplicates:

  SURVIVOR  the row linked to a power profile (so the amps keep their mains
            figures); failing that the one with the most amps, then the
            oldest.
  EXTRAS    every amp on them is moved to the survivor, then they are
            deleted.
  ALIAS     when the model has a power profile, the survivor takes the
            profile's name and is linked to it. "Lacoustics LA8-2" (the
            "-2" is a copy number, see model_key) becomes "L-Acoustics LA8"
            with the LA8 figures. This applies to a lone misspelt row too.
  SKIPPED   groups where moving would take something away: an extra with
            amps on it has a different channel count, or an input or
            connector the survivor lacks, or the rows point at different
            power profiles. Fix the rows by hand and re-run. Where the
            survivor has MORE (half-filled duplicates keep the defaults),
            the group merges and the dry-run says what the moved amps gain.

Every group is applied in its own transaction.

Usage:
    # Dry-run: lists every group, the survivor and how many amps move.
    python manage.py merge_amp_models

    # Do it:
    python manage.py merge_amp_models --apply

    # against prod, inside the app container (see CLAUDE.md). Take a Railway
    # Postgres backup first, and read the dry-run before adding --apply:
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py merge_amp_models
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py merge_amp_models --apply
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import Amp
from planner.utils.amp_models import duplicate_groups


def _describe(amp_model, counts):
    profile = amp_model.power_profile
    linked = f'profile: {profile}' if profile else 'no power profile'
    return (f'#{amp_model.pk} "{amp_model.manufacturer} {amp_model.model_name}" '
            f'({counts.get(amp_model.pk, 0)} amps, {linked})')


class Command(BaseCommand):
    help = ("Merge duplicate AmpModel rows into one, moving their amps. "
            "Dry-run unless given --apply.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Move the amps and delete the extra rows. Without it nothing is written.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        groups = duplicate_groups()
        if not groups:
            self.stdout.write(self.style.SUCCESS('No duplicate amp models.'))
            return

        self.stdout.write('APPLYING' if apply else 'DRY RUN: nothing will be written. Add --apply to merge.')
        merged = moved = deleted = renamed = linked = 0
        skipped = []
        for group in groups:
            self.stdout.write('')
            self.stdout.write(f'Group: {" / ".join(group.key)}')
            self.stdout.write(f'  keep    {_describe(group.survivor, group.amp_counts)}')
            for extra in group.extras:
                self.stdout.write(f'  merge   {_describe(extra, group.amp_counts)}')
            if group.rename_to:
                self.stdout.write(f'  rename  #{group.survivor.pk} to "{" ".join(group.rename_to)}"')
            if group.link_profile:
                self.stdout.write(f'  link    #{group.survivor.pk} to profile {group.profile}')
            if not group.can_merge:
                self.stdout.write(self.style.WARNING(
                    f'  SKIPPED: {"; ".join(group.problems)}'))
                skipped.append(group)
                continue
            for note in group.notes:
                self.stdout.write(f'  note    {note}')
            self.stdout.write(f'  {group.amps_to_move} amps move, {len(group.extras)} rows deleted')
            if not apply:
                continue
            with transaction.atomic():
                extra_ids = [m.pk for m in group.extras]
                moved += Amp.objects.filter(amp_model_id__in=extra_ids).update(
                    amp_model=group.survivor)
                for extra in group.extras:
                    extra.delete()
                    deleted += 1
                survivor = group.survivor
                if group.rename_to:
                    survivor.manufacturer, survivor.model_name = group.rename_to
                    renamed += 1
                if group.link_profile:
                    survivor.power_profile = group.profile
                    linked += 1
                if group.rename_to or group.link_profile:
                    survivor.save(update_fields=['manufacturer', 'model_name', 'power_profile'])
            merged += 1

        self.stdout.write('')
        if apply:
            self.stdout.write(self.style.SUCCESS(
                f'Merged {merged} groups: {moved} amps moved, {deleted} rows deleted, '
                f'{renamed} renamed, {linked} linked to a profile.'))
        else:
            total = sum(g.amps_to_move for g in groups if g.can_merge)
            rows = sum(len(g.extras) for g in groups if g.can_merge)
            ok = [g for g in groups if g.can_merge]
            self.stdout.write(
                f'Would merge {len(ok)} groups: '
                f'{total} amps moved, {rows} rows deleted, '
                f'{sum(1 for g in ok if g.rename_to)} renamed, '
                f'{sum(1 for g in ok if g.link_profile)} linked to a profile.')
        if skipped:
            self.stdout.write(self.style.WARNING(
                f'{len(skipped)} groups skipped; fix them by hand and re-run.'))
