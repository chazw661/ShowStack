"""Move per-slot photos (PresenterSlot.photo_data) up to their presenters.

Before PresenterPhoto existed, a headshot lived on the slot -- one presenter
on one mic in one session -- so putting that presenter in another session
showed no photo there. This works out, for every presenter, which of their
slots' photos becomes their headshot.

The rule, agreed before this was written:

* One distinct photo across the presenter's slots: that one.
* Several different photos (a CONFLICT): the one on the most slots; on a tie,
  the one on the newest slot (highest id). The report lists every candidate
  so a different one can be chosen with ``--choose PRESENTER=SLOT``.
* A presenter that already has a headshot is left alone, unless chosen
  explicitly or ``--overwrite`` is given.
* Same-name duplicate presenters are NOT merged: each gets its own slots'
  photo. The report lists them so a later merge knows where photos are.

Never across projects: a slot whose presenter belongs to another project is
skipped and reported (none existed on prod when this was written, but a
headshot moved across that line would be a tenant leak).

Nothing here clears ``photo_data``. It stays as the rollback until the column
is dropped.
"""

import base64
import binascii
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction

from planner.utils.image_upload import ImageRejected, validate_photo_bytes

# Why a presenter did or did not get a headshot.
SINGLE = 'single'            # one distinct photo
RULE = 'conflict-rule'       # several; most-used / newest picked
CHOSEN = 'chosen'            # several or not; --choose picked
FROM_FILE = 'legacy-file'    # no slot photo, but Presenter.photo's file exists
SKIP_EXISTING = 'has-headshot'


@dataclass
class Candidate:
    digest: str
    slot_ids: list = field(default_factory=list)
    mime: str = ''
    size: int = 0
    labels: list = field(default_factory=list)   # "Day / Session RF n" per slot

    @property
    def newest_slot(self):
        return max(self.slot_ids)


@dataclass
class Decision:
    presenter_id: int
    presenter_name: str
    project_id: int
    project_name: str
    candidates: list
    action: str
    chosen: Candidate = None
    file_name: str = ''

    @property
    def is_conflict(self):
        return len(self.candidates) > 1


@dataclass
class Plan:
    decisions: list = field(default_factory=list)
    orphans: list = field(default_factory=list)          # (slot_id, project_id, label)
    cross_project: list = field(default_factory=list)    # (slot_id, presenter_id, slot_proj, presenter_proj)
    invalid: list = field(default_factory=list)          # (slot_id, presenter_id, reason)
    missing_files: list = field(default_factory=list)    # (presenter_id, file name)
    same_name: list = field(default_factory=list)        # (project_id, name, [(presenter_id, has_photo)])
    slots_with_photo: int = 0
    distinct_images: int = 0

    @property
    def to_write(self):
        return [d for d in self.decisions if d.action != SKIP_EXISTING]


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


def build_plan(project_id=None, choices=None, overwrite=False):
    """Work out what --apply would do. Reads only; writes nothing.

    ``choices`` maps presenter id -> slot id (from --choose). A choice that
    does not name one of that presenter's photo'd slots raises ChoiceError
    before anything else happens.
    """
    from django.core.files.storage import default_storage
    from planner.models import Presenter, PresenterPhoto, PresenterSlot

    choices = dict(choices or {})
    plan = Plan()

    slots = (PresenterSlot.objects
             .exclude(photo_data__isnull=True).exclude(photo_data='')
             .order_by('id'))
    if project_id is not None:
        slots = slots.filter(assignment__session__day__project_id=project_id)

    by_presenter = defaultdict(dict)    # presenter_id -> digest -> Candidate
    digests = set()
    # values_list + iterator: one photo in memory at a time, not 110 MB.
    rows = slots.values_list(
        'id', 'presenter_id', 'photo_data',
        'assignment__session__day__project_id', 'assignment__session__day__name',
        'assignment__session__day__date', 'assignment__session__name',
        'assignment__rf_number', 'presenter__project_id',
    ).iterator(chunk_size=20)
    for (slot_id, presenter_id, data_url, slot_project, day_name, day_date,
         session_name, rf, presenter_project) in rows:
        plan.slots_with_photo += 1
        label = f'{day_name or day_date} / {session_name} RF {rf}'
        if presenter_id is None:
            plan.orphans.append((slot_id, slot_project, label))
            continue
        if presenter_project != slot_project:
            plan.cross_project.append((slot_id, presenter_id, slot_project, presenter_project))
            continue
        try:
            raw, mime = decode_data_url(data_url)
        except ImageRejected as e:
            plan.invalid.append((slot_id, presenter_id, str(e)))
            continue
        digest = hashlib.sha256(raw).hexdigest()
        digests.add(digest)
        cand = by_presenter[presenter_id].setdefault(
            digest, Candidate(digest=digest, mime=mime, size=len(raw)))
        cand.slot_ids.append(slot_id)
        cand.labels.append(label)
    plan.distinct_images = len(digests)

    for pid, slot_id in choices.items():
        if not any(slot_id in c.slot_ids for c in by_presenter.get(pid, {}).values()):
            raise ChoiceError(
                f'--choose {pid}={slot_id}: slot {slot_id} is not a photo on presenter {pid}'
                + (' in this project' if project_id is not None else ''))

    presenters = Presenter.objects.select_related('project').order_by('project_id', 'name', 'id')
    if project_id is not None:
        presenters = presenters.filter(project_id=project_id)
    has_headshot = set(PresenterPhoto.objects.filter(
        presenter__in=presenters).values_list('presenter_id', flat=True))

    names = defaultdict(list)
    for p in presenters:
        names[(p.project_id, _norm(p.name))].append(p)
        cands = sorted(by_presenter.get(p.id, {}).values(),
                       key=lambda c: (len(c.slot_ids), c.newest_slot), reverse=True)
        decision = Decision(
            presenter_id=p.id, presenter_name=p.name, project_id=p.project_id,
            project_name=p.project.name, candidates=cands, action='',
        )
        if not cands:
            # No slot photo. The old Presenter.photo file, if it survived.
            if p.photo and p.photo.name:
                if default_storage.exists(p.photo.name):
                    decision.action = FROM_FILE
                    decision.file_name = p.photo.name
                else:
                    plan.missing_files.append((p.id, p.photo.name))
                    continue
            else:
                continue
        elif p.id in choices:
            decision.action = CHOSEN
            decision.chosen = next(c for c in cands if choices[p.id] in c.slot_ids)
        else:
            decision.action = RULE if len(cands) > 1 else SINGLE
            decision.chosen = cands[0]
        if p.id in has_headshot and p.id not in choices and not overwrite:
            decision.action = SKIP_EXISTING
        plan.decisions.append(decision)

    photo_pids = {d.presenter_id for d in plan.decisions}
    for (proj, _n), group in names.items():
        if len(group) > 1 and any(p.id in photo_pids or p.id in has_headshot for p in group):
            plan.same_name.append(
                (proj, group[0].name,
                 [(p.id, p.id in photo_pids or p.id in has_headshot) for p in group]))
    return plan


def apply_plan(plan, user=None):
    """Write every non-skipped decision. One transaction per presenter, so a
    bad image stops only its own presenter. Returns (written, failures)."""
    from django.core.files.storage import default_storage
    from planner.models import Presenter, PresenterPhoto, PresenterSlot

    written, failures = 0, []
    for d in plan.to_write:
        try:
            if d.action == FROM_FILE:
                with default_storage.open(d.file_name, 'rb') as f:
                    raw = f.read()
            else:
                data_url = PresenterSlot.objects.values_list(
                    'photo_data', flat=True).get(id=d.chosen.newest_slot)
                raw, _mime = decode_data_url(data_url)
            with transaction.atomic():
                presenter = Presenter.objects.select_for_update().get(id=d.presenter_id)
                PresenterPhoto.store(presenter, raw, user)
            written += 1
        except Exception as e:  # report and carry on; the rest still move
            failures.append((d.presenter_id, f'{type(e).__name__}: {e}'))
    return written, failures
