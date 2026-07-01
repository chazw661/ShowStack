from django.db import migrations


def copy_fks_to_m2m(apps, schema_editor):
    MicAssignment = apps.get_model('planner', 'MicAssignment')
    PresenterSlot = apps.get_model('planner', 'PresenterSlot')

    for assignment in MicAssignment.objects.exclude(group__isnull=True).only('id', 'group_id'):
        assignment.groups.add(assignment.group_id)

    for slot in PresenterSlot.objects.exclude(group__isnull=True).only('id', 'group_id'):
        slot.groups.add(slot.group_id)

    for slot in PresenterSlot.objects.exclude(a2_group__isnull=True).only('id', 'a2_group_id'):
        slot.a2_groups.add(slot.a2_group_id)


def clear_m2m(apps, schema_editor):
    MicAssignment = apps.get_model('planner', 'MicAssignment')
    PresenterSlot = apps.get_model('planner', 'PresenterSlot')
    for assignment in MicAssignment.objects.all():
        assignment.groups.clear()
    for slot in PresenterSlot.objects.all():
        slot.groups.clear()
        slot.a2_groups.clear()


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0171_add_mic_groups_m2m'),
    ]

    operations = [
        migrations.RunPython(copy_fks_to_m2m, clear_m2m),
    ]
