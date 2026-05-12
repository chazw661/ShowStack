from django.db import migrations


# These operations use PostgreSQL-specific DDL (DROP CONSTRAINT IF EXISTS).
# SQLite does not support that syntax, so each operation is wrapped in a
# database-engine guard that no-ops on SQLite (used for local test runs).
#
# The actual schema change was applied to the Railway PostgreSQL database
# when this migration was first deployed.  The guard makes the migration
# idempotent in SQLite test environments without changing prod behaviour.

def _run_if_postgres(sql):
    """Return a RunSQL that executes only on PostgreSQL backends."""
    def forward(apps, schema_editor):
        if schema_editor.connection.vendor == 'postgresql':
            schema_editor.execute(sql)

    return migrations.RunPython(forward, migrations.RunPython.noop)


class Migration(migrations.Migration):
    dependencies = [
        ('planner', '0111_audiochecklist_created_at_audiochecklist_name_and_more'),
    ]

    operations = [
        # Remove the global unique constraint on date
        _run_if_postgres(
            'ALTER TABLE planner_showday DROP CONSTRAINT IF EXISTS planner_showday_date_key;'
        ),
        # Add composite unique constraint on project + date
        _run_if_postgres(
            'ALTER TABLE planner_showday ADD CONSTRAINT planner_showday_project_date_unique UNIQUE (project_id, date);'
        ),
    ]
