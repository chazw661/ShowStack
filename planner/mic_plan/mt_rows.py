"""Mic Tracker rows as plain JSON, for a push's revert data (push.apply
writes it, revert reads it).

``full`` is every column of one row, plus its many-to-many ids, exact enough
to re-create it with its pk. ``state`` is every session, row, slot and group
in some sessions, with photos as a hash (they are large, and only "changed or
not" matters there): what a push left, so a revert can tell what Mic Tracker
changed since.
"""

import hashlib

from planner.models import MicAssignment, MicGroup, MicSession, PresenterSlot

MODELS = {'micsession': MicSession, 'micassignment': MicAssignment, 'presenterslot': PresenterSlot,
          'micgroup': MicGroup}
IN_SESSIONS = {'micsession': 'pk__in', 'micassignment': 'session_id__in',
               'presenterslot': 'assignment__session_id__in', 'micgroup': 'session_id__in'}
# Set by Django on every save; a change elsewhere in the row is what counts.
NOT_COMPARED = {'last_modified'}


def _json(v):
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    if hasattr(v, 'name') and hasattr(v, 'storage'):          # a FieldFile
        return v.name or ''
    return v


def full(obj):
    out = {f.attname: _json(getattr(obj, f.attname)) for f in obj._meta.concrete_fields if not f.primary_key}
    for f in obj._meta.many_to_many:
        out[f.name] = sorted(getattr(obj, f.name).values_list('pk', flat=True))
    return out


def fingerprint(obj):
    out = {k: v for k, v in full(obj).items() if k not in NOT_COMPARED}
    if out.get('photo_data'):
        out['photo_data'] = hashlib.sha1(out['photo_data'].encode()).hexdigest()
    return out


def state(session_pks):
    """{model name: {str(pk): fingerprint}} for everything in these sessions."""
    session_pks = sorted(set(session_pks))
    return {name: {str(o.pk): fingerprint(o) for o in MODELS[name].objects.filter(**{IN_SESSIONS[name]: session_pks})}
            for name in MODELS}


def restore_value(model, attname, value):
    """``value`` as ``full`` wrote it, back as the column's Python value."""
    field = model._meta.get_field(attname)
    return value if value is None else field.to_python(value)
