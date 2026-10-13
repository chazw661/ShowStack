"""Sort every presenter into a person or a mic position, and place the photos.

Before PresenterPhoto, every photo lived on a slot (``PresenterSlot.photo_data``)
-- one presenter on one mic in one session. Some "presenters" are people, and
their photo should follow them into every session. Many are mic positions
(HH13, Q&A 2, A2 OS) with a different speaker's photo in each session, and
those photos must stay exactly where they are.

The rule, agreed before this was written:

* A presenter whose NAME looks like a mic position (planner.utils.mic_labels),
  or whose slots hold DIFFERENT photos, is a mic label: ``is_mic_label`` is
  set and every slot photo stays as that session's photo. No headshot.
* A person with one distinct photo: it becomes their headshot.
* A person whose photos are re-uploads of one picture (fingerprints within
  NEAR_IDENTICAL_BITS): one headshot -- the photo on the most slots, ties to
  the newest slot.
* A presenter already flagged a mic label stays one.
* Overrides, per presenter id: ``--skip`` (touch nothing), ``--label``,
  ``--person`` (headshot by the rule above), ``--choose P=S`` (person, with
  the photo on slot S).

Under the display rule (planner.utils.presenter_photos) a slot's own photo
wins on its card, so a person's slot photos keep showing on their cards after
this runs -- the headshot is what NEW sessions get. Nothing here clears
``photo_data`` or deletes a headshot: a wrong classification is undone by
re-running with an override, and no photo is lost either way.

Never across projects: a slot whose presenter belongs to another project is
skipped and reported (none on prod when this was written; a headshot moved
across that line would be a tenant leak). Same-name presenters are not merged.

``collect`` reads the database and decodes the images; ``classify`` is pure,
so the plan for any data set can be worked out and tested without one.
"""

import base64
import binascii
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction

from planner.utils.image_upload import (
    NEAR_IDENTICAL_BITS, ImageRejected, fingerprint_distance, photo_fingerprint,
    validate_photo_bytes,
)
from planner.utils.mic_labels import looks_like_mic_label

# What a presenter is, and why. LABEL_* set is_mic_label and write no
# headshot; PERSON_* that carry a photo write one.
SKIP = 'skip'
LABEL_ALREADY = 'label: already flagged'
LABEL_FORCED = 'label: --label'
LABEL_NAME = 'label: name'
LABEL_PHOTOS = 'label: different photos'
PERSON_FORCED = 'person: --person'
PERSON_CHOSEN = 'person: --choose'
PERSON_SINGLE = 'person: one photo'
PERSON_NEAR = 'person: re-uploads of one photo'
PERSON_FILE = 'person: photo file'
PERSON_KEEPS_HEADSHOT = 'person: has a headshot'
PERSON_NO_PHOTO = 'person: no photo'

LABELS = (LABEL_ALREADY, LABEL_FORCED, LABEL_NAME, LABEL_PHOTOS)
ORDER = (LABEL_NAME, LABEL_PHOTOS, LABEL_FORCED, LABEL_ALREADY,
         PERSON_SINGLE, PERSON_NEAR, PERSON_CHOSEN, PERSON_FORCED, PERSON_FILE,
         PERSON_KEEPS_HEADSHOT, PERSON_NO_PHOTO, SKIP)


@dataclass
class PresenterInfo:
    id: int
    name: str
    project_id: int
    project_name: str
    is_mic_label: bool = False
    has_headshot: bool = False
    photo_file: str = ''           # Presenter.photo's name, if set
    photo_file_exists: bool = False


@dataclass
class PhotoRow:
    """One slot holding a photo. ``error`` set means it could not be read."""
    slot_id: int
    presenter_id: int              # None: a slot with no presenter
    slot_project_id: int
    presenter_project_id: int
    label: str                     # "Day / Session RF n"
    digest: str = ''
    mime: str = ''
    size: int = 0
    fingerprint: int = 0
    error: str = ''


@dataclass
class Candidate:
    """One distinct image (by content hash) on one presenter's slots."""
    digest: str
    fingerprint: int
    mime: str
    size: int
    slot_ids: list = field(default_factory=list)
    labels: list = field(default_factory=list)

    @property
    def newest_slot(self):
        return max(self.slot_ids)


@dataclass
class Decision:
    presenter: PresenterInfo
    kind: str
    candidates: list = field(default_factory=list)   # most slots first
    chosen: Candidate = None        # the photo that becomes the headshot
    spread: int = 0                 # largest fingerprint distance between candidates

    @property
    def is_label(self):
        return self.kind in LABELS

    @property
    def sets_label(self):
        """True/False to write is_mic_label, None to leave it."""
        if self.kind == SKIP:
            return None
        want = self.is_label
        return want if want != self.presenter.is_mic_label else None

    @property
    def writes_headshot(self):
        return self.kind in (PERSON_SINGLE, PERSON_NEAR, PERSON_CHOSEN,
                             PERSON_FORCED, PERSON_FILE) and (
            self.chosen is not None or self.kind == PERSON_FILE)

    @property
    def has_photos(self):
        return bool(self.candidates) or self.kind == PERSON_FILE


@dataclass
class Overrides:
    skip: set = field(default_factory=set)
    label: set = field(default_factory=set)
    person: set = field(default_factory=set)
    choose: dict = field(default_factory=dict)   # presenter id -> slot id
    overwrite: bool = False


@dataclass
class Plan:
    decisions: list = field(default_factory=list)
    orphans: list = field(default_factory=list)          # PhotoRow
    cross_project: list = field(default_factory=list)    # PhotoRow
    invalid: list = field(default_factory=list)          # PhotoRow
    missing_files: list = field(default_factory=list)    # PresenterInfo
    same_name: list = field(default_factory=list)        # (project_id, name, [Decision])
    slots_with_photo: int = 0
    distinct_images: int = 0

    def of_kind(self, kind):
        return [d for d in self.decisions if d.kind == kind]

    @property
    def headshots_to_write(self):
        return [d for d in self.decisions if d.writes_headshot]

    @property
    def flags_to_set(self):
        return [d for d in self.decisions if d.sets_label is not None]


class ChoiceError(ValueError):
    pass


def decode_data_url(data_url):
    """(bytes, mime) for a stored data URL, or raise ImageRejected."""
    if not data_url or not data_url.startswith('data:') or ',' not in data_url:
        raise ImageRejected('not a data URL')
    try:
        raw = base64.b64decode(data_url.split(',', 1)[1], validate=False)
    except (binascii.Error, ValueError):
        raise ImageRejected('bad base64')
    return raw, validate_photo_bytes(raw)


def _norm(name):
    return ' '.join((name or '').split()).casefold()


def _clusters(cands):
    """Group candidates whose fingerprints chain within NEAR_IDENTICAL_BITS."""
    parent = list(range(len(cands)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if fingerprint_distance(cands[i].fingerprint, cands[j].fingerprint) <= NEAR_IDENTICAL_BITS:
                parent[root(i)] = root(j)
    return len({root(i) for i in range(len(cands))})


def collect(project_id=None):
    """Read what classify() needs: every presenter, and every slot photo
    decoded, hashed and fingerprinted (one photo in memory at a time)."""
    from django.core.files.storage import default_storage
    from planner.models import Presenter, PresenterPhoto, PresenterSlot

    presenters_qs = Presenter.objects.select_related('project').order_by('project_id', 'name', 'id')
    if project_id is not None:
        presenters_qs = presenters_qs.filter(project_id=project_id)
    has_headshot = set(PresenterPhoto.objects.filter(
        presenter__in=presenters_qs).values_list('presenter_id', flat=True))
    presenters = []
    for p in presenters_qs:
        name = p.photo.name if p.photo else ''
        presenters.append(PresenterInfo(
            id=p.id, name=p.name, project_id=p.project_id, project_name=p.project.name,
            is_mic_label=p.is_mic_label, has_headshot=p.id in has_headshot,
            photo_file=name or '',
            photo_file_exists=bool(name) and default_storage.exists(name),
        ))

    slots = (PresenterSlot.objects
             .exclude(photo_data__isnull=True).exclude(photo_data='')
             .order_by('id'))
    if project_id is not None:
        slots = slots.filter(assignment__session__day__project_id=project_id)
    photos = []
    for (slot_id, presenter_id, data_url, slot_project, day_name, day_date,
         session_name, rf, presenter_project) in slots.values_list(
            'id', 'presenter_id', 'photo_data',
            'assignment__session__day__project_id', 'assignment__session__day__name',
            'assignment__session__day__date', 'assignment__session__name',
            'assignment__rf_number', 'presenter__project_id',
    ).iterator(chunk_size=20):
        row = PhotoRow(slot_id=slot_id, presenter_id=presenter_id,
                       slot_project_id=slot_project, presenter_project_id=presenter_project,
                       label=f'{day_name or day_date} / {session_name} RF {rf}')
        try:
            raw, row.mime = decode_data_url(data_url)
            row.digest = hashlib.sha256(raw).hexdigest()
            row.size = len(raw)
            row.fingerprint = photo_fingerprint(raw)
        except ImageRejected as e:
            row.error = str(e)
        photos.append(row)
    return presenters, photos


def classify(presenters, photos, overrides=None):
    """Work out what --apply would do. Pure: no database, no images.

    Raises ChoiceError for an override that names a presenter not in this run,
    names one presenter twice, or --choose's a slot that is not that
    presenter's photo -- before anything is decided.
    """
    o = overrides or Overrides()
    plan = Plan()
    by_id = {p.id: p for p in presenters}

    # Overrides first: a typo must stop the run, not be ignored.
    choose_ids = set(o.choose)
    named = [('--skip', o.skip), ('--label', o.label),
             ('--person', o.person - choose_ids), ('--choose', choose_ids)]
    seen = {}
    for flag, ids in named:
        for pid in ids:
            if pid not in by_id:
                raise ChoiceError(f'{flag} {pid}: no presenter {pid} in this run')
            if pid in seen:
                raise ChoiceError(f'presenter {pid} is given both {seen[pid]} and {flag}')
            seen[pid] = flag

    by_presenter = defaultdict(dict)    # presenter id -> digest -> Candidate
    digests = set()
    for row in photos:
        plan.slots_with_photo += 1
        if row.presenter_id is None:
            plan.orphans.append(row)
            continue
        if row.presenter_project_id != row.slot_project_id:
            plan.cross_project.append(row)
            continue
        if row.error:
            plan.invalid.append(row)
            continue
        if row.presenter_id not in by_id:   # outside --project
            continue
        digests.add(row.digest)
        cand = by_presenter[row.presenter_id].setdefault(row.digest, Candidate(
            digest=row.digest, fingerprint=row.fingerprint, mime=row.mime, size=row.size))
        cand.slot_ids.append(row.slot_id)
        cand.labels.append(row.label)
    plan.distinct_images = len(digests)

    for pid, slot_id in o.choose.items():
        if not any(slot_id in c.slot_ids for c in by_presenter.get(pid, {}).values()):
            raise ChoiceError(f'--choose {pid}={slot_id}: slot {slot_id} is not a photo on presenter {pid}')

    names = defaultdict(list)
    for p in presenters:
        cands = sorted(by_presenter.get(p.id, {}).values(),
                       key=lambda c: (len(c.slot_ids), c.newest_slot), reverse=True)
        d = Decision(presenter=p, kind='', candidates=cands)
        d.spread = max((fingerprint_distance(a.fingerprint, b.fingerprint)
                        for i, a in enumerate(cands) for b in cands[i + 1:]), default=0)
        distinct = _clusters(cands) if cands else 0
        rule_pick = cands[0] if cands else None

        if p.id in o.skip:
            d.kind = SKIP
        elif p.id in o.label:
            d.kind = LABEL_FORCED
        elif p.id in o.choose:
            d.kind = PERSON_CHOSEN
            d.chosen = next(c for c in cands if o.choose[p.id] in c.slot_ids)
        elif p.id in o.person:
            d.kind = PERSON_FORCED
            d.chosen = rule_pick
        elif p.is_mic_label:
            d.kind = LABEL_ALREADY
        elif looks_like_mic_label(p.name):
            d.kind = LABEL_NAME
        elif distinct > 1:
            d.kind = LABEL_PHOTOS
        elif cands:
            d.kind = PERSON_SINGLE if len(cands) == 1 else PERSON_NEAR
            d.chosen = rule_pick
        elif p.photo_file and p.photo_file_exists:
            d.kind = PERSON_FILE
        else:
            d.kind = PERSON_NO_PHOTO
            if p.photo_file:
                plan.missing_files.append(p)

        # An existing headshot is kept unless this run is told otherwise.
        if (d.writes_headshot and p.has_headshot and d.kind != PERSON_CHOSEN
                and not o.overwrite):
            d.kind = PERSON_KEEPS_HEADSHOT
            d.chosen = None
        if d.kind == PERSON_FORCED and d.chosen is None and p.photo_file_exists:
            d.kind = PERSON_FILE

        plan.decisions.append(d)
        names[(p.project_id, _norm(p.name))].append(d)

    for (proj, _n), group in names.items():
        if len(group) > 1 and any(d.has_photos or d.presenter.has_headshot for d in group):
            plan.same_name.append((proj, group[0].presenter.name, group))
    return plan


def build_plan(project_id=None, overrides=None):
    """Read the database and classify. Writes nothing."""
    presenters, photos = collect(project_id)
    return classify(presenters, photos, overrides)


def apply_plan(plan, user=None):
    """Write the plan: is_mic_label for every presenter whose classification
    changes it, and a headshot for every person who gets one. One transaction
    per presenter, so a bad image stops only its own presenter. Slot photos
    are never touched. Returns (flags_written, headshots_written, failures).
    """
    from django.core.files.storage import default_storage
    from planner.models import Presenter, PresenterPhoto, PresenterSlot

    flags = headshots = 0
    failures = []
    for d in plan.decisions:
        want_flag = d.sets_label
        if want_flag is None and not d.writes_headshot:
            continue
        try:
            raw = None
            if d.writes_headshot:
                if d.kind == PERSON_FILE:
                    with default_storage.open(d.presenter.photo_file, 'rb') as f:
                        raw = f.read()
                else:
                    data_url = PresenterSlot.objects.values_list(
                        'photo_data', flat=True).get(id=d.chosen.newest_slot)
                    raw, _mime = decode_data_url(data_url)
            with transaction.atomic():
                presenter = Presenter.objects.select_for_update().get(id=d.presenter.id)
                if want_flag is not None:
                    presenter.is_mic_label = want_flag
                    presenter.save(update_fields=['is_mic_label'])
                if raw is not None:
                    PresenterPhoto.store(presenter, raw, user)
            flags += want_flag is not None
            headshots += raw is not None
        except Exception as e:  # report and carry on; the rest still move
            failures.append((d.presenter.id, f'{type(e).__name__}: {e}'))
    return flags, headshots, failures
