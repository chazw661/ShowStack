"""Revert the last Send to Mic Tracker: put Mic Tracker back exactly as it was
before that push, from MicPlanPush.before.

``preview`` lists what the revert would do and writes nothing; ``apply``
works it out again in one transaction, checks it is still what the editor
saw and does it:

1. re-create the sessions, rows and slots the push deleted, with their pks;
2. put back the values it changed on rows, slots and People links (a slot it
   moved goes back to its old row, its A2 data with it);
3. delete the slots, rows and sessions it created (still marked
   rf_from_plan, so deleting a row renumbers nothing);
4. put back the values it changed on sessions, rf_from_plan included;
5. delete the presenters it created that nothing uses any more.

Every write is a queryset update or bulk_create, so no save() hook runs
(a session's scaffold rows, renumbering). The push is then marked reverted
(``summary['reverted']``), and ``push.last_push`` skips it, so the next push
matches through the one before it.

A push stores what it left (``before['after']``). Anything different now was
changed in Mic Tracker since; the revert is refused while there is any,
unless the editor ticks "revert anyway". A slot or row with a photo, A2
notes or MIC'D that the revert would delete is always listed.
"""

import hashlib
import json
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from planner.models import MicAssignment, MicPlanPush, MicSession, Presenter, PresenterSlot, ShowflowPerson

from . import mt_rows
from .push import PushRefused, last_push

LEGACY = ('This push was sent before Revert existed, so changes made in Mic Tracker since it '
          'cannot be checked. Look at Mic Tracker first.')
ORDER = ('micsession', 'micassignment', 'presenterslot')
FIELD_WORDS = {'presenter_id': 'presenter', 'assignment_id': 'RF', 'session_id': 'session', 'rf_number': 'RF',
               'num_mics': 'mic count', 'rf_from_plan': 'fixed RF numbers', 'start_time': 'start',
               'end_time': 'end', 'is_micd': "MIC'D", 'is_active': 'active', 'photo_data': 'photo',
               'a2_group_id': 'A2 group', 'group_id': 'group', 'a2_groups': 'A2 groups'}


@dataclass
class RevertPreview:
    push: MicPlanPush
    actions: list = field(default_factory=list)      # what it will do, in words
    changed: list = field(default_factory=list)      # changed in Mic Tracker since the push
    a2: list = field(default_factory=list)           # A2 data the revert would delete
    presenters: list = field(default_factory=list)   # created by the push: removed if unused
    digest: str = ''


class _Names:
    """Words for sessions, rows and slots, from the database and the push's
    revert data (for things that no longer exist)."""

    def __init__(self, push):
        self.sessions = {s.pk: s.name for s in MicSession.objects.filter(day_id=push.day_id)}
        self.rows = {r.pk: (r.session_id, r.rf_number) for r in MicAssignment.objects.filter(session__day_id=push.day_id)}
        self.presenters = dict(Presenter.objects.filter(project_id=push.day.project_id).values_list('pk', 'name'))
        b = push.before or {}
        for kind in ('after',):
            for pk, v in (b.get(kind) or {}).get('micsession', {}).items():
                self.sessions.setdefault(int(pk), v.get('name', ''))
            for pk, v in (b.get(kind) or {}).get('micassignment', {}).items():
                self.rows.setdefault(int(pk), (v.get('session_id'), v.get('rf_number')))
        for model, pk, v in b.get('deleted', []):
            if model == 'micsession':
                self.sessions.setdefault(pk, v.get('name', ''))
            elif model == 'micassignment':
                self.rows.setdefault(pk, (v.get('session_id'), v.get('rf_number')))

    def session(self, pk):
        return self.sessions.get(pk) or 'a session'

    def row(self, pk):
        spk, rf = self.rows.get(pk, (None, None))
        return 'RF {} · {}'.format(rf if rf is not None else '?', self.session(spk))

    def slot(self, values):
        who = self.presenters.get(values.get('presenter_id')) or 'no presenter'
        return '{} · {}'.format(self.row(values.get('assignment_id')), who)

    def thing(self, model, pk, values):
        if model == 'micsession':
            return 'Session {}'.format(values.get('name') or self.session(pk))
        if model == 'micassignment':
            return self.row(pk)
        if model == 'presenterslot':
            return self.slot(values)
        return 'Group {} in {}'.format(values.get('name', ''), self.session(values.get('session_id')))


def _a2_reason(values, pushed):
    """Why deleting this slot or row loses A2 data ('' if it does not).
    ``pushed``: its values as the push left them (None: added since)."""
    if values.get('photo_data') or values.get('photo'):
        return 'photo'
    if values.get('is_micd'):
        return "MIC'D"
    if values.get('notes') and values.get('notes') != (pushed or {}).get('notes'):
        return 'notes'
    return ''


def _created(b):
    out = {m: [] for m in ('micsession', 'micassignment', 'presenterslot', 'presenter')}
    for model, pk in b.get('created', []):
        out[model].append(pk)
    return out


def _originals(b, model):
    """{pk: {field: value before the push}} for the values it changed. A
    field changed twice keeps its first (earliest) value."""
    out = {}
    for m, pk, values in b.get('updated', []):
        if m == model:
            row = out.setdefault(pk, {})
            for f, v in values.items():
                row.setdefault(f, v)
    return out


def preview(day):
    """What reverting ``day``'s last push would do. Raises PushRefused."""
    push = last_push(day)
    if push is None:
        raise PushRefused('There is no push to revert.', 404)
    b = push.before or {}
    names = _Names(push)
    out = RevertPreview(push=push)
    created = _created(b)

    # Changed in Mic Tracker since the push.
    after = b.get('after')
    if after is None:
        out.changed.append(LEGACY)
        now = mt_rows.state(_scope_of(b))
    else:
        now = mt_rows.state(b.get('scope', []))
        for model in mt_rows.MODELS:
            was, cur = after.get(model, {}), now.get(model, {})
            for pk in sorted(set(was) | set(cur), key=int):
                if pk not in cur:
                    out.changed.append('{}: deleted in Mic Tracker'.format(names.thing(model, int(pk), was[pk])))
                elif pk not in was:
                    out.changed.append('{}: added in Mic Tracker'.format(names.thing(model, int(pk), cur[pk])))
                elif was[pk] != cur[pk]:
                    fields = [f for f in cur[pk] if cur[pk][f] != was[pk].get(f)]
                    out.changed.append('{}: {} changed'.format(
                        names.thing(model, int(pk), cur[pk]), ', '.join(FIELD_WORDS.get(f, f.replace('_', ' '))
                                                                         for f in fields)))
    pushed = (after or {})

    # What it deletes, A2 data first.
    gone_sessions = set(created['micsession'])
    gone_rows = set(created['micassignment'])
    for pk, v in now.get('micassignment', {}).items():
        if v['session_id'] in gone_sessions:
            gone_rows.add(int(pk))
    gone_slots = set(created['presenterslot'])
    for pk, v in now.get('presenterslot', {}).items():
        if v['assignment_id'] in gone_rows:
            gone_slots.add(int(pk))
    moved_back = {pk for pk, old in _originals(b, 'presenterslot').items() if 'assignment_id' in old}
    for pk in sorted(gone_slots - moved_back):
        v = now.get('presenterslot', {}).get(str(pk))
        if v is None:
            continue
        why = _a2_reason(v, pushed.get('presenterslot', {}).get(str(pk), None if after is not None else {}))
        if why:
            out.a2.append('{}: {} will be deleted'.format(names.slot(v), why))
    for pk in sorted(gone_rows):
        v = now.get('micassignment', {}).get(str(pk))
        if v is None:
            continue
        why = _a2_reason(v, pushed.get('micassignment', {}).get(str(pk), None if after is not None else {}))
        if why:
            out.a2.append('{}: row {} will be deleted'.format(names.row(pk), why))

    live = {m: set(map(int, now.get(m, {}))) for m in ORDER}
    for pk in sorted(created['micsession']):
        if pk in live['micsession']:
            rows = sum(1 for v in now['micassignment'].values() if v['session_id'] == pk)
            out.actions.append('Delete session {} ({} RF{}), created by this push'.format(
                names.session(pk), rows, '' if rows == 1 else 's'))
    for pk in sorted(created['micassignment']):
        v = now['micassignment'].get(str(pk))
        if v is not None and v['session_id'] not in gone_sessions:
            out.actions.append('Delete {}, created by this push'.format(names.row(pk)))
    for pk in sorted(created['presenterslot']):
        v = now['presenterslot'].get(str(pk))
        if v is not None and v['assignment_id'] not in gone_rows:
            out.actions.append('Delete slot {}, created by this push'.format(names.slot(v)))

    for model in ORDER:
        for pk, old in sorted(_originals(b, model).items()):
            cur = now.get(model, {}).get(str(pk))
            if cur is None:
                continue
            diff = {f: v for f, v in old.items() if cur.get(f) != v}
            if diff:
                out.actions.append('Put back {}: {}'.format(names.thing(model, pk, cur), ', '.join(
                    '{} {}'.format(FIELD_WORDS.get(f, f.replace('_', ' ')), _word(f, v, names)) for f, v in diff.items())))
    for model, pk, values in b.get('deleted', []):
        if model in ORDER:
            out.actions.append('Re-create {}, deleted by this push'.format(names.thing(model, pk, values)))
    links = sum(1 for m, *_ in b.get('updated', []) if m == 'showflowperson')
    if links:
        out.actions.append('Unlink {} {} in People from the presenter this push linked'.format(
            links, 'person' if links == 1 else 'people'))
    out.presenters = sorted(Presenter.objects.filter(pk__in=created['presenter']).values_list('name', flat=True))

    out.digest = hashlib.sha256(json.dumps(
        [push.pk, out.actions, out.changed, out.a2, out.presenters, now], sort_keys=True, default=str)
        .encode()).hexdigest()
    return out


def _word(f, v, names):
    if v in (None, ''):
        return '(blank)'
    if f == 'presenter_id':
        return names.presenters.get(v, 'a presenter')
    if f == 'assignment_id':
        return names.row(v)
    if isinstance(v, bool):
        return 'on' if v else 'off'
    return str(v)


def _scope_of(b):
    """The sessions an older push (no ``scope``) touched, from its revert data."""
    rows = dict(MicAssignment.objects.values_list('pk', 'session_id').filter(
        pk__in=[pk for m, pk, *_ in b.get('created', []) + b.get('updated', []) if m == 'micassignment']))
    out = set(rows.values())
    for model, pk, *rest in b.get('created', []) + b.get('updated', []) + b.get('deleted', []):
        if model == 'micsession':
            out.add(pk)
        elif model == 'presenterslot':
            a = PresenterSlot.objects.filter(pk=pk).values_list('assignment__session_id', flat=True).first()
            if a:
                out.add(a)
    for model, pk, *rest in b.get('deleted', []):
        if model == 'micassignment':
            out.add(rest[0]['session_id'])
    return out


@transaction.atomic
def apply(day, push_pk, digest, anyway=False, user=None):
    """Do the revert the editor confirmed. Returns the (now reverted) push."""
    list(MicSession.objects.select_for_update().filter(day=day).values_list('pk', flat=True))
    p = preview(day)
    push = MicPlanPush.objects.select_for_update().get(pk=p.push.pk)
    if push.pk != push_pk or digest != p.digest:
        raise PushRefused('Mic Tracker or the push changed since the preview. Review it again.', 409)
    if p.changed and not anyway:
        raise PushRefused('Mic Tracker changed since this push. Tick "Revert anyway" to revert regardless.', 409)
    b = push.before or {}
    created = _created(b)

    # 1. Re-create what the push deleted, parents first, with their pks.
    deleted = {m: [(pk, v) for mm, pk, v in b.get('deleted', []) if mm == m] for m in ORDER}
    for model in ORDER:
        cls = mt_rows.MODELS[model]
        for pk, values in deleted[model]:
            if cls.objects.filter(pk=pk).exists() or not _parent_exists(model, values):
                continue
            if model == 'micassignment' and MicAssignment.objects.filter(
                    session_id=values['session_id'], rf_number=values['rf_number']).exists():
                continue                    # an RF added in Mic Tracker since ("revert anyway")
            m2m = {f.name: values.get(f.name) for f in cls._meta.many_to_many if f.name in values}
            cols = {k: mt_rows.restore_value(cls, k, v) for k, v in values.items() if k not in m2m}
            if cols.get('presenter_id') and not Presenter.objects.filter(pk=cols['presenter_id']).exists():
                cols['presenter_id'] = None
            obj, = cls.objects.bulk_create([cls(pk=pk, **cols)])
            stamped = {f.attname: cols[f.attname] for f in cls._meta.concrete_fields
                       if getattr(f, 'auto_now', False) and cols.get(f.attname)}
            if stamped:                     # bulk_create stamped them "now"
                cls.objects.filter(pk=pk).update(**stamped)
            for name, ids in m2m.items():
                getattr(obj, name).set(ids or [])

    # 2. Values on rows, slots and People links, latest change undone first.
    for model, pk, values in reversed(b.get('updated', [])):
        if model == 'micsession':
            continue
        cls = ShowflowPerson if model == 'showflowperson' else mt_rows.MODELS[model]
        cls.objects.filter(pk=pk).update(**{k: mt_rows.restore_value(cls, k, v) for k, v in values.items()})

    # 3. Delete what it created, children first (rf_from_plan still set).
    PresenterSlot.objects.filter(pk__in=created['presenterslot']).delete()
    MicAssignment.objects.filter(pk__in=created['micassignment']).delete()
    MicSession.objects.filter(pk__in=created['micsession']).delete()

    # 4. Session values, rf_from_plan and num_mics included.
    for model, pk, values in reversed(b.get('updated', [])):
        if model == 'micsession':
            MicSession.objects.filter(pk=pk).update(
                **{k: mt_rows.restore_value(MicSession, k, v) for k, v in values.items()})

    # 5. Presenters it created, if nothing uses them now.
    for pres in Presenter.objects.filter(pk__in=created['presenter']):
        if not any(r.related_model._default_manager.filter(**{r.field.name: pres}).exists()
                   for r in Presenter._meta.related_objects):
            pres.delete()

    push.summary = dict(push.summary or {}, reverted={
        'at': timezone.now().isoformat(), 'by': user.get_username() if user else '', 'anyway': bool(anyway and p.changed),
        'changed': p.changed, 'a2': p.a2})
    push.save(update_fields=['summary'])
    return push


def _parent_exists(model, values):
    if model == 'micsession':
        return True
    if model == 'micassignment':
        return MicSession.objects.filter(pk=values['session_id']).exists()
    return MicAssignment.objects.filter(pk=values['assignment_id']).exists()


def last_reverted(day):
    """The day's most recently reverted push, for the header, or None."""
    return MicPlanPush.objects.filter(day=day, summary__has_key='reverted').first()
