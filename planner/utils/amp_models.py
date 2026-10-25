"""Telling AmpModel rows apart from spelling variants of each other.

The AmpModel catalogue is shared by every account and anyone who edits a show
can add to it, so it has collected rows like "L-Acoustics LA12X", "LA LA12X"
and two "Lacoustics LA8-2"s. Two rows are the same model when their names
match after dropping case, spaces and punctuation, and after reading the
manufacturer abbreviations below as the full name.

Used by the AmpModel add form (offer the existing row instead of a new one)
and by the merge_amp_models command.
"""
import re
from dataclasses import dataclass, field

# Normalised manufacturer spellings seen in real rows, mapped to one form.
# Extend this rather than special-casing a brand anywhere else.
MANUFACTURER_ALIASES = {
    'la': 'lacoustics',
    'lacoustic': 'lacoustics',
    'lacoustics': 'lacoustics',
    'db': 'dbaudiotechnik',
    'dbaudio': 'dbaudiotechnik',
    'meyer': 'meyersound',
}

# What an amp's channel rows and rack-card outputs come from. Amps only move
# to a row with the same channel count and at least the same inputs and
# connectors, so nothing already filled in on them drops out of view.
SPEC_FIELDS = (
    'channel_count', 'has_analog_inputs', 'has_aes_inputs', 'has_avb_inputs',
    'nl4_connector_count', 'nl8_connector_count', 'cacom_output_count',
    'sc32_connector_count',
)


def _squash(text):
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())


def model_key(manufacturer, model_name):
    """("L-Acoustics", "LA 12X") and ("la", "la12x") give the same key."""
    maker = _squash(manufacturer)
    return MANUFACTURER_ALIASES.get(maker, maker), _squash(model_name)


def find_existing(manufacturer, model_name, exclude_pk=None):
    """The AmpModel rows that are this model under another spelling, the
    one to use first."""
    from planner.models import AmpModel
    key = model_key(manufacturer, model_name)
    rows = AmpModel.objects.exclude(pk=exclude_pk) if exclude_pk else AmpModel.objects.all()
    matches = [m for m in rows.select_related('power_profile')
               if model_key(m.manufacturer, m.model_name) == key]
    return sorted(matches, key=_survivor_rank)


def _survivor_rank(amp_model, amp_counts=None):
    """Linked to a power profile first, then the most amps, then the fullest
    spec (rows added in a hurry keep the defaults), then the oldest."""
    amps = (amp_counts or {}).get(amp_model.pk, 0)
    spec = sum(int(getattr(amp_model, name)) for name in SPEC_FIELDS[1:])
    return (amp_model.power_profile_id is None, -amps, -spec, amp_model.pk)


@dataclass
class DuplicateGroup:
    key: tuple
    survivor: object
    extras: list
    amp_counts: dict
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def amps_to_move(self):
        return sum(self.amp_counts.get(m.pk, 0) for m in self.extras)

    @property
    def can_merge(self):
        return not self.problems


def duplicate_groups():
    """Every set of two or more AmpModel rows that are one model."""
    from django.db.models import Count
    from planner.models import AmpModel
    rows = list(AmpModel.objects.select_related('power_profile')
                .annotate(n_amps=Count('amp')).order_by('pk'))
    by_key = {}
    for m in rows:
        by_key.setdefault(model_key(m.manufacturer, m.model_name), []).append(m)

    groups = []
    for key, members in by_key.items():
        if len(members) < 2:
            continue
        counts = {m.pk: m.n_amps for m in members}
        members.sort(key=lambda m: _survivor_rank(m, counts))
        survivor, extras = members[0], members[1:]
        problems, notes = [], []
        profiles = {m.power_profile_id for m in members} - {None}
        if len(profiles) > 1:
            problems.append('linked to different power profiles')
        for extra in extras:
            if not counts[extra.pk]:
                continue  # no amps move, so nothing can change for anyone
            for name in SPEC_FIELDS:
                mine, theirs = getattr(extra, name), getattr(survivor, name)
                if mine == theirs:
                    continue
                label = name.replace('_', ' ')
                if name == 'channel_count' or theirs < mine:
                    # The moved amps would lose channel rows or outputs.
                    problems.append(f'#{extra.pk} has {label} {mine}, #{survivor.pk} has {theirs}')
                else:
                    notes.append(f'amps from #{extra.pk} gain {label} ({mine} -> {theirs})')
        groups.append(DuplicateGroup(key, survivor, extras, counts, problems, notes))
    return groups
