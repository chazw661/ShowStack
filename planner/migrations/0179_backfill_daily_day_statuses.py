from django.db import migrations


def backfill_day_statuses(apps, schema_editor):
    """Issue #55: copy existing day1..day4 statuses into the flexible
    day_statuses JSON for every daily task, so no per-day progress is lost when
    the UI switches to variable day columns. Setup tasks keep using day1_status.
    """
    AudioChecklistTask = apps.get_model('planner', 'AudioChecklistTask')
    for task in AudioChecklistTask.objects.filter(task_type='daily'):
        task.day_statuses = {
            '1': task.day1_status,
            '2': task.day2_status,
            '3': task.day3_status,
            '4': task.day4_status,
        }
        task.save(update_fields=['day_statuses'])


def noop(apps, schema_editor):
    """day1..day4 columns are retained, so no reverse work is needed."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0178_audiochecklist_num_days_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_day_statuses, noop),
    ]
