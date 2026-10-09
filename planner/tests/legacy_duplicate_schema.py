"""Run a test module against the schema as it was *before* migration 0198.

``cleanup_duplicate_amp_channels`` and ``cleanup_duplicate_mic_assignments``
are pre-migration tools. Their entire job is to clear the duplicate rows that
issue #100 wrote and that migration 0198's pre-flight check refuses to add the
uniqueness constraints over. A database still holding those duplicates is, by
definition, a database where ``unique_amp_channel_number`` and
``unique_session_rf_number`` do not exist yet -- so their fixtures cannot be
built while the constraints are in place.

Hence::

    from planner.tests.legacy_duplicate_schema import (
        setUpModule, tearDownModule)          # noqa: F401

``setUpModule`` / ``tearDownModule`` are used rather than a mixin because
unittest runs them outside every test transaction. ``TestCase`` opens a
class-level atomic block in ``setUpClass``, and on SQLite dropping a table
constraint means rebuilding the table -- not something to do inside an open
transaction. Both functions are idempotent, so it does not matter if the
runner's test reordering makes them fire more than once.

Nothing else should import this. A test that needs duplicate numbers is
either testing the cleanup tools or testing something that should not be
possible any more.
"""
from contextlib import contextmanager

from django.db import connection

from planner.models import AmpChannel, MicAssignment

# (model, constraint name) for the two constraints migration 0198 adds.
LEGACY_DROPPED = (
    (AmpChannel, 'unique_amp_channel_number'),
    (MicAssignment, 'unique_session_rf_number'),
)


def _named(model, name):
    """The UniqueConstraint object called ``name`` on ``model``, or None."""
    for constraint in model._meta.constraints:
        if constraint.name == name:
            return constraint
    return None


def _set_constraints(model, constraints):
    """Replace ``model._meta.constraints`` and drop what Django cached off it.

    SQLite has no ``ALTER TABLE ... DROP CONSTRAINT``: Django's schema editor
    rebuilds the table from ``model._meta``, so the constraint has to be gone
    from the model state *before* ``remove_constraint`` runs or the rebuild
    puts it straight back. ``total_unique_constraints`` is a cached_property
    feeding ``Model.validate_unique()``, so it has to go with it.
    """
    model._meta.constraints = constraints
    model._meta.__dict__.pop('total_unique_constraints', None)


def drop_number_constraints():
    """Drop both constraints. No-op for either one already gone."""
    for model, name in LEGACY_DROPPED:
        constraint = _named(model, name)
        if constraint is None:
            continue
        remaining = [c for c in model._meta.constraints if c.name != name]
        _set_constraints(model, remaining)
        with connection.schema_editor(atomic=False) as editor:
            editor.remove_constraint(model, constraint)


def restore_number_constraints():
    """Put both constraints back. No-op for either one already present."""
    for model, name in LEGACY_DROPPED:
        if _named(model, name) is not None:
            continue
        constraint = _ORIGINALS[(model, name)]
        _set_constraints(model, list(model._meta.constraints) + [constraint])
        with connection.schema_editor(atomic=False) as editor:
            editor.add_constraint(model, constraint)


# Captured at import, while the model state is still pristine, so
# restore_number_constraints() has something to put back.
_ORIGINALS = {
    (model, name): _named(model, name) for model, name in LEGACY_DROPPED
}
for _key, _value in _ORIGINALS.items():
    assert _value is not None, (
        '%s has no constraint named %r -- legacy_duplicate_schema is out of '
        'step with the model. If the constraint was renamed, rename it here '
        'too; if it was removed, this module and the cleanup commands it '
        'supports are probably obsolete.' % (_key[0].__name__, _key[1])
    )


@contextmanager
def legacy_duplicate_schema():
    """Context-manager form, for a single test that needs duplicate numbers."""
    drop_number_constraints()
    try:
        yield
    finally:
        restore_number_constraints()


def setUpModule():
    drop_number_constraints()


def tearDownModule():
    restore_number_constraints()
