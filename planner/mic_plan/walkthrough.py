"""The walkthrough: one panel per showflow row of a day, in show order, with
what the parse read from it (time, who comes on and off, their mic type,
the row's issues), never an RF. It replaces the Review tab.

What a panel shows comes from the parse and the user's overrides alone
(planning.build_day + solver.appearances, no solve), so the walkthrough
works before Generate and every on/off sits on the row that caused it: a
send, a line naming them, a re-entry, a catch, an exit line, a change the
user made. An off nothing wrote (the end of their segment) sits on the
segment's last row as an assumption. A host's times on stage stay separate.

A row that runs on past a page break (the first row of a page, with no line
label and no start time, under a row that has one) folds into the row above:
one panel.

Confirming: ``MicPlannerRowCheck`` keeps the row (rowkey.describe) and a
digest of its raw text plus what the panel showed. A check whose digest no
longer matches is reopened, and ``shown`` gives "was → now". Plan flags are
not in the digest: a Re-generate reopens nothing. A panel with no one coming
on or off, no issue and no lock is confirmed automatically.

Locks: a panel that is locked is never confirmed by Enter.
- person: the first row of a name the parse had little to go on for (a
  part planned by line estimates, or a name no send/catch cue is behind)
  until someone says Person / Not a person / Same as. Names a cue brought on
  get a first-row highlight instead.
- row: exit wording, a row split across pages, a mic type the parse
  inferred, text in the row no name accounts for. "Looks right" (or any
  edit of the row) confirms it.

Blockers (conflicts, a shortage while over the rig, held-back overrides)
stop Send to Mic Tracker whatever is confirmed.
"""

import hashlib
import json
import re

from django.db import transaction
from django.utils import timezone

from planner.models import MicPlan, MicPlannerDayOverride, MicPlannerRowCheck, ShowflowEvent, ShowflowImport

from . import importer, overrides, planning, rowkey, solver
from .display import FLAG_LABELS, PLAN_LABELS
from .parser import description_candidates, hm
from .planning import SHOWFLOW_CARD

# The cells a panel shows: the parser's column name -> ShowflowRow field.
COLUMNS = {'description': 'description', 'speaker': 'speaker_text', 'bsm': 'bsm_text',
           'audio': 'audio_text', 'notes': 'notes_text'}
LOCK_TEXT = {
    'exit': 'Exit wording: check who comes off here.',
    'split': 'This line runs on across a page break.',
    'mic': 'Mic type inferred from the showflow.',
    'leftover': 'Text here is not a person ShowStack recognised.',
}
# Plan flags shown on the walkthrough's day strip or rows; the override
# issues come from the build itself (build_day issues), not the plan.
_OVERRIDE_KINDS = ('override_changed', 'override_gone', 'override_person')
_EXIT_FLAGS = ('who_exits',)
_MIC_FLAGS = ('mic_name', 'mic_which')
_LEFTOVER_FLAGS = ('unmatched_speaker', 'description_names')


def _text(row):
    return any(getattr(row, f) for f in COLUMNS.values()) or bool(row.start_text)


def _labelled(row):
    return bool(row.line_no.strip() or row.start_text.strip())


def fold(rows):
    """[[head row, continuation rows...]] of one part's ``rows`` (in order),
    blank rows left out. A row continues the one above when it is the first
    with text on a later page, has no line label and no start time, and the
    row above has one of them: in files whose sub-rows carry neither (cues
    under a labelled line), an unlabelled row opening a page is the next
    sub-row, not a run-on (the corpus had three such, all false)."""
    panels, last_page = [], None
    for r in rows:
        if r.is_blank and not r.line_no:
            continue
        new_page = last_page is not None and r.page_no > last_page
        last_page = r.page_no
        if panels and new_page and not _labelled(r) and _labelled(panels[-1][0]) and _text(r):
            panels[-1].append(r)
        else:
            panels.append([r])
    return panels


def _digest(panel):
    out = {'text': [rowkey.raw_text(r) for r in panel['_rows']], 'time': panel['time'],
           'on': sorted([o['key'], o['mic'], o['how'], o['host']] for o in panel['on']),
           'off': sorted([o['key'], o['how']] for o in panel['off']),
           'issues': sorted(i['kind'] for i in panel['issues']),
           'locks': sorted(l['kind'] for l in panel['locks']) + sorted(p['key'] for p in panel['person_locks'])}
    return hashlib.sha1(json.dumps(out, sort_keys=True).encode()).hexdigest()


def _who(o):
    bits = [o['name']]
    if o.get('mic') == solver.HH:
        bits.append('HH')
    if o.get('host'):
        bits.append('host')
    if o.get('how') == 'end':
        bits.append('assumed')
    return ' · '.join(bits)


def _shown(panel):
    """What the panel showed, in words: kept with a check for "was → now"."""
    return {'text': ' / '.join(rowkey.raw_text(r) for r in panel['_rows']), 'time': panel['time'],
            'on': [_who(o) for o in panel['on']], 'off': [_who(o) for o in panel['off']],
            'issues': [i['label'] for i in panel['issues']]}


WAS_WORDS = {'text': 'Showflow text', 'time': 'Time', 'on': 'On', 'off': 'Off', 'issues': 'Issues'}


def was_now(before, now):
    out = []
    for k, word in WAS_WORDS.items():
        a, b = before.get(k), now.get(k)
        if a != b:
            fmt = (lambda v: ', '.join(v) or 'nobody') if k in ('on', 'off') else \
                  (lambda v: ', '.join(v) or 'none') if k == 'issues' else (lambda v: v or '—')
            out.append({'what': word, 'was': fmt(a or ([] if k in ('on', 'off', 'issues') else '')),
                        'now': fmt(b or ([] if k in ('on', 'off', 'issues') else ''))})
    return out


def _locate(text, piece, start=0):
    """(start, end) of ``piece`` in ``text`` ignoring case and runs of spaces, or None."""
    words = piece.split()
    if not words:
        return None
    m = re.compile(r'\s+'.join(re.escape(w) for w in words), re.I).search(text or '', start)
    return (m.start(), m.end()) if m else None


def _segment_at(ix, app):
    """The segment of the appearance's part that its (assumed) off falls in:
    the one it ends, else the one its last row is in."""
    segs = ix.part_segs.get(app.part, [])
    seg = next((s for s in segs if s.t0 < app.off <= s.t1), None)
    if seg is None:
        row = ix.row.get(app.off_row)
        seg = ix.seg_of(row) if row is not None else None
    return seg


def build(day, plan=None, values=None):
    """Everything the walkthrough shows for ``day`` (JSON-safe but for the
    '_rows' of each panel, which ``public`` drops)."""
    parts = importer.active_parts(day)
    plan = plan if plan is not None else MicPlan.objects.filter(day=day).first()
    if values is None:
        values = planning.plan_values(plan) if plan is not None else planning.settings_dict(
            planning.project_settings(day.project))
    edits = list(plan.edits.all()) if plan is not None else []
    data, rows_by_part, mode = planning.build_day(day, follow=planning._showflow_hosts(values, edits))
    apps, hosts = solver.appearances(data, fold_hosts=False)
    ix = solver._Index(data)
    people = {p.pk: p for p in day.showflow_people.all()}
    numbers = {p.pk: k + 1 for k, p in enumerate(parts)}

    # Panels, in show order; every row maps to its panel.
    panels, panel_of = [], {}
    for part in parts:
        for group in fold(rows_by_part[part.pk]):
            head = group[0]
            p = {'id': head.pk, 'part': part.pk, 'part_no': numbers[part.pk],
                 'line': head.line_no or '#{}'.format(head.order + 1), 'page': head.page_no,
                 'time': '' if head.est_time is None else (hm(head.est_time) if head.time_exact
                                                           else '≈' + hm(head.est_time)),
                 'segment': head.is_segment, 'continued': len(group) > 1,
                 'rows': [{'order': r.order, 'page': r.page_no, 'line': r.line_no, 'start': r.start_text,
                           'cells': {c: getattr(r, f) for c, f in COLUMNS.items() if getattr(r, f)}, 'marks': []}
                          for r in group],
                 'on': [], 'off': [], 'issues': [], 'badges': [], 'locks': [], 'person_locks': [],
                 'leftovers': [], '_rows': group}
            panels.append(p)
            for r in group:
                panel_of[r.pk] = p
    by_order = {(part.pk, r.order): r for part in parts for r in rows_by_part[part.pk]}
    show_index = {p['id']: k for k, p in enumerate(panels)}

    def mark(part_pk, order, col, start, end, kind, person=None):
        r = by_order.get((part_pk, order))
        if r is None or r.pk not in panel_of:
            return
        p = panel_of[r.pk]
        cell = next(x for x in p['rows'] if x['order'] == order)
        if col in cell['cells'] and 0 <= start < end <= len(cell['cells'][col]):
            cell['marks'].append({'col': col, 'start': start, 'end': end, 'kind': kind, 'person': person})

    # Who comes on and off, on the row that did it.
    sends = {(c.person, c.row) for c in data.cues if c.kind == 'send'}
    enters = {(person, k) for person, keys in data.enters.items() for k in keys}
    added = {(a.person, a.on_row) for a in data.added}
    applied, issues = overrides.plan_input(parts, rows_by_part)
    user_on = set()
    user_mic = set()
    for part, row, e in applied:
        for key in e.get('on', ()):
            user_on.add((key, row.pk))
        for key in (e.get('mic') or {}):
            user_mic.add((key, row.pk))
    first_on = {}
    for a in sorted(apps, key=lambda a: (show_index[panel_of[a.on_row]['id']] if a.on_row in panel_of else -1,
                                         a.on, a.person)):
        person = people.get(a.person)
        if person is None or a.on_row not in panel_of:
            continue
        key = person.name_key
        if (a.person, a.on_row) in sends:
            how = 'send'
        elif (key, a.on_row) in user_on:
            how = 'user'
        elif (a.person, a.on_row) in added:
            how = 'added'
        elif person.flags.get('role') == 'vog':
            how = 'fixed'
        elif (a.person, a.on_row) in enters:
            how = 'enter'
        else:
            how = 'named'
        if (key, a.on_row) in user_mic or person.mic_hint_locked:
            mic_how = 'user'
        elif a.mic_type == solver.HH and person.mic_hint == 'HH':
            mic_how = 'hint'
        else:
            mic_how = 'default'
        on = {'person': a.person, 'key': key, 'name': person.display_name, 'mic': a.mic_type, 'mic_how': mic_how,
              'how': how, 'host': a.person in hosts, 'backup': person.mic_hint == 'backup',
              'at': hm(a.on), 'assumed': ''}
        panel_of[a.on_row]['on'].append(on)
        first_on.setdefault(a.person, panel_of[a.on_row])
        # The off: on the row that wrote it, else (assumed) the last row of
        # the segment they were on in.
        off_panel = panel_of.get(a.off_row)
        if a.off_how == 'end':
            seg = _segment_at(ix, a)
            if seg is not None:
                last = next((r for r in reversed(rows_by_part[seg.part])
                             if seg.start <= r.order < seg.end and r.pk in panel_of), None)
                off_panel = panel_of.get(last.pk) if last is not None else off_panel
        if off_panel is not None:
            off_panel['off'].append({'person': a.person, 'key': key, 'name': person.display_name,
                                     'how': a.off_how, 'host': a.person in hosts, 'at': hm(a.off),
                                     'assumed': 'end of segment' if a.off_how == 'end' else ''})

    # What the user said about each row (overrides), for its edit form.
    for part in parts:
        for e, row, _ in overrides.resolve(part, rows_by_part[part.pk]):
            if row is not None and row.pk in panel_of:
                panel_of[row.pk]['override'] = dict({k: list(e.get(k, ())) for k in overrides.LISTS},
                                                    mic=dict(e.get('mic') or {}), id=e['id'])

    # Highlights: the words each name came from, and leftover text.
    for person in people.values():
        for part_pk, spans in (person.flags.get('spans') or {}).items():
            for order, col, start, end in spans:
                mark(int(part_pk), order, col, start, end, 'name', person.pk)

    # Row issues from the parse; file-level ones go to the day strip.
    strip = []
    for part in parts:
        for w in part.warnings:
            label = FLAG_LABELS.get(w['kind'], w['kind'])
            r = by_order.get((part.pk, w.get('row_order'))) if w.get('row_order') is not None else None
            if r is None or r.pk not in panel_of:
                strip.append({'kind': w['kind'], 'label': label, 'text': w['text'], 'part_no': numbers[part.pk]})
                continue
            p = panel_of[r.pk]
            p['issues'].append({'kind': w['kind'], 'label': label, 'text': w['text']})
            if w['kind'] == 'unmatched_speaker':
                spans = w.get('spans') or [
                    s for s in (_locate(r.speaker_text, q) for q in re.findall(r'"([^"]+)"', w['text'])) if s]
                for start, end in spans:
                    mark(part.pk, r.order, 'speaker', start, end, 'leftover')
            elif w['kind'] == 'description_names':
                at = 0
                for name in description_candidates(r.description):
                    found = _locate(r.description, name, at)
                    if found:
                        mark(part.pk, r.order, 'description', found[0], found[1], 'leftover')
                        at = found[1]
                p['leftovers'] = description_candidates(r.description)
    for i in issues:
        label = PLAN_LABELS.get(i['kind'], i['kind'])
        item = {'kind': i['kind'], 'label': label, 'text': i['text'], 'entry': i.get('entry'), 'part': i.get('part')}
        if i['kind'] == 'override_changed':
            item.update(was=i['was'], now=i['now'])
        strip.append(item)
        if i.get('row') in panel_of:
            panel_of[i['row']]['issues'].append({'kind': i['kind'], 'label': label, 'text': i['text']})

    # Plan flags: badges on their row (label only), the rest on the strip.
    if plan is not None:
        for f in plan.flags:
            if f['kind'] in _OVERRIDE_KINDS:
                continue
            label = PLAN_LABELS.get(f['kind'], f['kind'])
            if f.get('row') in panel_of:
                p = panel_of[f['row']]
                if not any(b['kind'] == f['kind'] for b in p['badges']):
                    p['badges'].append({'kind': f['kind'], 'label': label})
            elif f['kind'] == SHOWFLOW_CARD:
                strip.append({'kind': f['kind'], 'label': label, 'text': f['text'], 'plan': True,
                              'mics': [i['text'] for i in f['items'] if not i['repeat']],
                              'can_use': any(i['fits'] for i in f['items'])})
            else:
                strip.append({'kind': f['kind'], 'label': label, 'text': f['text'], 'plan': True})
    for o in MicPlannerDayOverride.objects.filter(day=day, kind='not_a_person'):
        strip.append({'kind': 'rejected', 'label': 'Not a person', 'key': o.key,
                      'text': '"{}" is not a person on this day.'.format(o.value.get('phrase') or o.key)})
    for person in people.values():
        for line in person.flags.get('added_missing', []):
            strip.append({'kind': 'added_missing', 'label': FLAG_LABELS['added_missing'], 'person': person.pk,
                          'text': 'Line {} is no longer in this showflow: {} was added on at it by hand.'
                                  .format(line, person.display_name)})
        if person.flags.get('gone'):
            strip.append({'kind': 'gone', 'label': FLAG_LABELS['gone'], 'person': person.pk,
                          'text': '{} is no longer in this showflow but has a merge, Presenter link or mic hint '
                                  'you set.'.format(person.display_name)})

    # Locks.
    cued_people = set(ShowflowEvent.objects.filter(row__showflow_import__in=parts).values_list('person_id', flat=True))
    loose = {pk for pk in rows_by_part} - set(data.cued_parts)
    first_seen = {}
    for p in panels:
        for cell in p['rows']:
            for m in cell['marks']:
                if m['person'] is not None:
                    first_seen.setdefault(m['person'], p)
    for pk, person in people.items():
        if person.flags.get('gone') or person.flags.get('role') or person.flags.get('added'):
            continue
        where = first_on.get(pk) or first_seen.get(pk)
        if where is None:
            continue
        in_loose = any(person.flags.get('rows', {}).get(str(part)) for part in loose)
        weak = in_loose or pk not in cued_people
        if weak and not person.flags.get('confirmed'):
            where['person_locks'].append({'person': pk, 'key': person.name_key, 'name': person.display_name})
        elif not weak:
            for o in where['on']:
                if o['person'] == pk:
                    o['first'] = True
    for p in panels:
        kinds = {i['kind'] for i in p['issues']}
        reasons = []
        if kinds & set(_EXIT_FLAGS) or any(o['how'] == 'exit' for o in p['off']) or any(
                g.row in {r.pk for r in p['_rows']} for g in data.group_exits):
            reasons.append('exit')
        if p['continued']:
            reasons.append('split')
        if kinds & set(_MIC_FLAGS) or any(o['mic_how'] == 'hint' for o in p['on']):
            reasons.append('mic')
        if kinds & set(_LEFTOVER_FLAGS):
            reasons.append('leftover')
        p['locks'] = [{'kind': k, 'text': LOCK_TEXT[k]} for k in reasons]

    # Confirmed, reopened, open or automatic.
    checks = {}
    for part in parts:
        rows = rows_by_part[part.pk]
        for c in part.row_checks.all():
            r, _ = rowkey.find(c.row, rows)
            if r is not None and r.pk in panel_of:
                checks[panel_of[r.pk]['id']] = c          # the latest wins (ordered by id)
    for p in panels:
        p['digest'] = _digest(p)
        shown = _shown(p)
        c = checks.get(p['id'])
        quiet = not (p['on'] or p['off'] or p['issues'] or p['locks'] or p['person_locks'])
        if c is not None and c.digest == p['digest']:
            p['state'] = 'confirmed'
        elif c is not None:
            p['state'] = 'reopened'
            p['was'] = was_now(c.shown, shown)
        else:
            p['state'] = 'auto' if quiet else 'open'
        if c is not None:
            p['by'], p['at'] = c.checked_by_name, c.checked_at.isoformat()
        p['sig'] = hashlib.sha1(json.dumps([p['digest'], p['state'], p.get('by'), p['badges']],
                                           sort_keys=True).encode()).hexdigest()[:12]
        p['_shown'] = shown

    short = ''
    if plan is not None and not plan.stale:
        from .push import short_of_rig
        short = short_of_rig(plan)
    blockers = []
    if plan is not None and not plan.stale:
        for f in plan.flags:
            if f['kind'] == 'conflict' or (short and f['kind'] == 'shortage'):
                p = panel_of.get(f.get('row'))
                blockers.append({'kind': f['kind'], 'label': PLAN_LABELS[f['kind']], 'text': f['text'],
                                 'panel': p['id'] if p else None, 'line': p['line'] if p else ''})
    for i in issues:
        if i['kind'] == 'override_changed':
            p = panel_of.get(i.get('row'))
            blockers.append({'kind': i['kind'], 'label': PLAN_LABELS[i['kind']], 'text': i['text'],
                             'panel': p['id'] if p else None, 'line': p['line'] if p else ''})
    return {
        'parts': [{'pk': part.pk, 'no': numbers[part.pk], 'name': part.source_filename} for part in parts],
        'people': sorted(({'pk': p.pk, 'key': p.name_key, 'name': p.display_name} for p in people.values()
                          if not p.flags.get('gone')), key=lambda x: x['name'].lower()),
        'panels': panels,
        'strip': strip,
        'blockers': blockers,
        'mode': mode,
        'stale': bool(plan and plan.stale),
        'has_plan': plan is not None,
    }


def progress(walk):
    panels = walk['panels']
    done = sum(1 for p in panels if p['state'] in ('confirmed', 'auto'))
    reopened = sum(1 for p in panels if p['state'] == 'reopened')
    first = next((p['id'] for p in panels if p['state'] in ('open', 'reopened')), None)
    plan_rows = [p['id'] for p in panels if p['badges']]
    return {'confirmed': done, 'total': len(panels), 'reopened': reopened,
            'open': len(panels) - done - reopened, 'auto': sum(1 for p in panels if p['state'] == 'auto'),
            'first_open': first, 'done': first is None, 'plan_rows': plan_rows,
            'plan_issues': sum(len(p['badges']) for p in panels)}


def public(panel):
    return {k: v for k, v in panel.items() if not k.startswith('_')}


def page_data(walk):
    """The JSON the page renders (json_script)."""
    return {'parts': walk['parts'], 'people': walk['people'], 'panels': [public(p) for p in walk['panels']],
            'strip': walk['strip'],
            'blockers': walk['blockers'], 'progress': progress(walk), 'mode': walk['mode'],
            'stale': walk['stale'], 'has_plan': walk['has_plan']}


def find_panel(walk, row_pk):
    for p in walk['panels']:
        if p['id'] == row_pk or any(r.pk == row_pk for r in p['_rows']):
            return p
    return None


class Refused(Exception):
    """The row is not what the user saw (``panel``: as it is now)."""
    def __init__(self, panel, why):
        super().__init__(why)
        self.panel = panel


@transaction.atomic
def confirm(day, row_pk, digest, user=None, ack=False, walk=None):
    """Confirm the panel of ``row_pk`` as the user saw it (``digest``).
    A row lock needs ``ack`` (Looks right); a person lock a decision.
    Returns the walk, rebuilt."""
    walk = walk or build(day)
    p = find_panel(walk, row_pk)
    if p is None:
        raise Refused(None, 'That line is no longer in this showflow.')
    ShowflowImport.objects.select_for_update().get(pk=p['part'])
    if digest is not None and p['digest'] != digest:
        raise Refused(p, 'This line changed.')
    if p['person_locks']:
        raise Refused(p, 'Decide who {} is first.'.format(p['person_locks'][0]['name']))
    if p['locks'] and not ack:
        raise Refused(p, 'Check this line first.')
    _save_check(p, user)
    return build(day)


def _save_check(p, user):
    rows = p['_rows'][0].showflow_import.rows.order_by('order')
    rows = list(rows)
    head = p['_rows'][0]
    for c in MicPlannerRowCheck.objects.filter(part_id=p['part']):
        r, _ = rowkey.find(c.row, rows)
        if r is not None and r.pk in {x.pk for x in p['_rows']}:
            c.delete()
    MicPlannerRowCheck.objects.create(
        part_id=p['part'], row=rowkey.describe(head, rows), digest=p['digest'], shown=p['_shown'],
        checked_by=user, checked_by_name=user.get_username() if user else '', checked_at=timezone.now())


@transaction.atomic
def unconfirm(day, row_pk):
    walk = build(day)
    p = find_panel(walk, row_pk)
    if p is None:
        return walk
    rows = list(p['_rows'][0].showflow_import.rows.order_by('order'))
    mine = {x.pk for x in p['_rows']}
    for c in MicPlannerRowCheck.objects.filter(part_id=p['part']):
        r, _ = rowkey.find(c.row, rows)
        if r is not None and r.pk in mine:
            c.delete()
    return build(day)


def confirm_after_edit(day, row_pk, user):
    """An edit of a row confirms it, as it now is (locks or not: the edit
    is the decision), unless a person on it is still undecided."""
    walk = build(day)
    p = find_panel(walk, row_pk)
    if p is not None and not p['person_locks']:
        with transaction.atomic():
            _save_check(p, user)
        walk = build(day)
    return walk


def open_rows(day):
    """Rows not confirmed, and rows reopened: the dashboard card's count."""
    pr = progress(build(day))
    return pr['open'] + pr['reopened']
