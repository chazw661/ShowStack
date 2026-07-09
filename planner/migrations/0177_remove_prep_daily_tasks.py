from django.db import migrations


def delete_prep_daily_tasks(apps, schema_editor):
    """Issue #53: the Prep ("Pre Pro") checklist no longer has a Daily Tasks
    column. Delete any daily task rows users manually added to Prep checklists.

    Scope is Prep only — FOH and A2 daily tasks are left untouched.
    """
    AudioChecklistTask = apps.get_model('planner', 'AudioChecklistTask')
    AudioChecklistTask.objects.filter(
        task_type='daily',
        checklist__name='Prep Check List',
    ).delete()


def noop(apps, schema_editor):
    """No reverse — deleted user data cannot be reconstructed."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0176_expand_ampchannel_avb_stream'),
    ]

    operations = [
        migrations.RunPython(delete_prep_daily_tasks, noop),
    ]
