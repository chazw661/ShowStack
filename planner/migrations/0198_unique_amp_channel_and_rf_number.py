"""Make (amp, channel_number) and (session, rf_number) unique at the database.

Issue #100 let ``Project.duplicate()`` double every auto-scaffolded child row,
so 4-channel amps came out of duplication with 8 ``AmpChannel`` rows numbered
1,1,2,2,3,3,4,4 and mic sessions came out with every ``rf_number`` twice. The
duplication is fixed and the production data has been cleaned, but nothing in
the schema stopped the next bug writing the same shape again -- and every
reader of these tables (the rack view, the Rivage PM export, the PA cable
schedule, the Mic Tracker, the A2 view, the Listen companion) is written as
though a number identifies one row.

Why the constraints are NOT ``DEFERRABLE INITIALLY DEFERRED``
-------------------------------------------------------------
A deferrable constraint is the right tool when some write path must pass
through an intermediate state that collides -- the classic "swap two numbers"
update. Every path that renumbers these fields was audited, and none of them
does:

* ``MicSession.renumber_assignments()`` collapses rf_numbers to 1..N and is
  the one true in-place renumberer (it runs from the issue #36 ``post_delete``
  receiver, from ``MicSessionAdmin.save_formset``, and from the
  ``renumber_mic_assignments`` command). It is collision-free for any
  numbering this constraint permits, and not by luck: it takes the rows in
  ``rf_number`` order and always collapses to ``1..N``, so each row's target
  is at or below the value it already holds, earlier rows have already
  dropped below it, and later rows are still above it. Nothing is written
  onto occupied ground, with or without the two passes over negative
  scratch values that it additionally uses (those earn their keep repairing
  legacy *duplicate*-holding data, which breaks that argument -- but that
  repair necessarily happens before this migration, never after it).
  ``test_unique_numbering`` pins the property over every gapped subset.
* ``Amp.setup_channels()`` and ``MicSession.create_mic_assignments()`` only
  ever *add* the numbers missing from ``1..target``. They used to derive that
  range from a row count, which duplicated an existing number whenever the
  surviving numbers had a gap; both now compute the gap from the numbers
  themselves.
* ``Project.duplicate()`` and ``MicSession.duplicate_to_session()`` delete the
  scaffold rows the parent's ``save()`` created before copying the source rows
  in, so the copy inserts into an empty child set.
* ``mic_assignment_reorder`` (drag-and-drop in the Mic Tracker) swaps
  ``PresenterSlot.presenter`` and deliberately leaves ``rf_number`` alone --
  RF numbers are hardware, the presenter moves between them.
* ``amp_reorder`` and ``amp_divider_reorder`` move ``Amp.sort_order``, a
  different column with no uniqueness requirement.
* ``amp_channel_inline_update`` cannot write ``channel_number`` at all; it is
  not in ``_INLINE_CHANNEL_FIELDS``. The admin inline marks it readonly and
  allows neither add nor delete.

With no path needing deferral, immediate constraints are strictly better here:

1. **Deferred constraints are invisible to SQLite, where the tests run.**
   Django's SQLite backend reports ``supports_deferrable_unique_constraints =
   False``, and ``UniqueConstraint.create_sql`` returns no SQL at all when the
   backend cannot honour ``deferrable``. The constraint would silently not
   exist locally -- the exact local-SQLite-vs-prod-Postgres divergence that
   produced issue #56 -- and every test below would pass against nothing.
2. **Deferred violations surface at COMMIT, not at the offending statement.**
   The traceback would land in the transaction middleware instead of the line
   that wrote the bad row.
3. **Django does not use deferrable constraints for ``validate_unique()``.**
   Immediate constraints give the admin's ``MicSession`` inline a clean "Mic
   assignment with this Session and Rf number already exists" form error
   instead of a 500 from a raw ``IntegrityError``.

Pre-flight check
----------------
``AddConstraint`` on a table that already holds a duplicate fails with a bare
``psycopg2.errors.UniqueViolation`` naming an index, which says nothing about
what to do next. ``check_for_duplicates`` runs first and aborts with the
cleanup commands spelled out instead. It is a no-op on a clean database.
"""

from django.conf import settings
from django.db import migrations, models
from django.db.models import Count


def _duplicate_report(model, parent_field, number_field):
    """Rows of ``model`` sharing ``number_field`` within one parent.

    The explicit ``order_by`` is load-bearing: both models carry a
    ``Meta.ordering``, and a ``values().annotate()`` inherits it straight into
    the GROUP BY, which would group by ``id`` / ``rf_number`` as well and
    return no duplicates at all.
    """
    dupes = (
        model.objects
        .values(parent_field, number_field)
        .annotate(n=Count('pk'))
        .filter(n__gt=1)
        .order_by(parent_field, number_field)
    )
    return [
        '  {}={} {}={} ({} rows)'.format(
            parent_field, row[parent_field],
            number_field, row[number_field], row['n'],
        )
        for row in dupes
    ]


def check_for_duplicates(apps, schema_editor):
    """Abort with instructions rather than letting AddConstraint blow up.

    Deliberately not reversible-sensitive and deliberately read-only: a
    migration is the wrong place to delete a customer's rows. The cleanup
    commands are dry-run by default and are the supported way to do it.
    """
    AmpChannel = apps.get_model('planner', 'AmpChannel')
    MicAssignment = apps.get_model('planner', 'MicAssignment')

    problems = []

    amp_lines = _duplicate_report(AmpChannel, 'amp', 'channel_number')
    if amp_lines:
        problems.append(
            'AmpChannel rows share a channel_number within one amp:\n'
            + '\n'.join(amp_lines)
            + '\n\n  Inspect:  python manage.py report_duplicate_amp_channels'
              '\n  Dry-run:  python manage.py cleanup_duplicate_amp_channels'
              '\n  Apply:    python manage.py cleanup_duplicate_amp_channels '
              '--apply'
        )

    mic_lines = _duplicate_report(MicAssignment, 'session', 'rf_number')
    if mic_lines:
        problems.append(
            'MicAssignment rows share an rf_number within one session:\n'
            + '\n'.join(mic_lines)
            + '\n\n  Inspect:  python manage.py '
              'report_duplicate_mic_assignments'
              '\n  Dry-run:  python manage.py '
              'cleanup_duplicate_mic_assignments'
              '\n  Apply:    python manage.py '
              'cleanup_duplicate_mic_assignments --apply'
        )

    if not problems:
        return

    raise RuntimeError(
        'Cannot add the uniqueness constraints: this database still holds '
        'duplicate rows (issue #100).\n\n'
        + '\n\n'.join(problems)
        + '\n\nBoth cleanup commands are dry-run unless given --apply; read '
          'the dry-run before applying it, and take a Railway Postgres '
          'backup first. On Railway, run them inside the container:\n'
          '  railway ssh --service ShowStack -- /opt/venv/bin/python '
          '/app/manage.py report_duplicate_amp_channels\n'
          'Then re-run this migration.'
    )


def noop_reverse(apps, schema_editor):
    """Nothing to undo -- the forward direction only reads."""


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0197_alter_pacableschedule_cable'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(check_for_duplicates, noop_reverse),
        migrations.AddConstraint(
            model_name='ampchannel',
            constraint=models.UniqueConstraint(
                fields=('amp', 'channel_number'),
                name='unique_amp_channel_number',
            ),
        ),
        migrations.AddConstraint(
            model_name='micassignment',
            constraint=models.UniqueConstraint(
                fields=('session', 'rf_number'),
                name='unique_session_rf_number',
            ),
        ),
    ]
