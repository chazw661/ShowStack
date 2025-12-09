from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('planner', '0111_audiochecklist_created_at_audiochecklist_name_and_more'),
    ]

    operations = [
        # Remove the global unique constraint on date
        migrations.RunSQL(
            sql='ALTER TABLE planner_showday DROP CONSTRAINT IF EXISTS planner_showday_date_key;',
            reverse_sql='ALTER TABLE planner_showday ADD CONSTRAINT planner_showday_date_key UNIQUE (date);',
        ),
        # Add composite unique constraint on project + date
        migrations.RunSQL(
            sql='ALTER TABLE planner_showday ADD CONSTRAINT planner_showday_project_date_unique UNIQUE (project_id, date);',
            reverse_sql='ALTER TABLE planner_showday DROP CONSTRAINT IF EXISTS planner_showday_project_date_unique;',
        ),
    ]
