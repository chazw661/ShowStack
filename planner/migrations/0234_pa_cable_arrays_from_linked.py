"""Copy each linked-mode run's one Speaker Array into ``speaker_arrays``.

Only ``entry_mode='linked'`` rows: a free-text row could carry a stale
``speaker_array`` the old form hid, and the old screens never showed it.
The FK column stays (dropped in a later cleanup PR), so reversing needs no
copy back; the through rows go with the M2M when 0233 is reversed.
"""
from django.db import migrations


def copy_linked_arrays(apps, schema_editor):
    PACableSchedule = apps.get_model('planner', 'PACableSchedule')
    Through = PACableSchedule.speaker_arrays.through
    Through.objects.bulk_create([
        Through(pacableschedule_id=pk, speakerarray_id=array_id)
        for pk, array_id in PACableSchedule.objects
        .filter(entry_mode='linked', speaker_array__isnull=False)
        .values_list('pk', 'speaker_array_id')
    ], ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0233_pa_cable_one_mode'),
    ]

    operations = [
        migrations.RunPython(copy_linked_arrays, migrations.RunPython.noop),
    ]
