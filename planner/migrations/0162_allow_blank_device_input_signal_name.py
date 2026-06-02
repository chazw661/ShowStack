"""DeviceInput custom-name combobox.

Allow ``DeviceInput.signal_name`` to be blank and backfill it from the
existing ``console_input.source`` for legacy rows that left signal_name
empty (the old inline form bound only the FK and never wrote
signal_name — see views.py:8091 comment). Without this backfill, the
new combobox UI would render an empty cell for every existing row even
though the patch info is still in the DB.

We deliberately keep the ``console_input`` FK column so the device PDF's
"Console Source" column ("Console A - Input 12") still renders for rows
created before this change. New rows authored via the combobox just
store signal_name and leave the FK null.
"""
from django.db import migrations, models


def backfill_signal_name(apps, schema_editor):
    DeviceInput = apps.get_model('planner', 'DeviceInput')
    qs = (DeviceInput.objects
          .filter(signal_name='', console_input__isnull=False)
          .select_related('console_input'))
    for inp in qs:
        source = (inp.console_input.source or '').strip()
        if source:
            inp.signal_name = source[:100]
            inp.save(update_fields=['signal_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0161_remove_galaxyinput_origin_device_output_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deviceinput',
            name='signal_name',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(backfill_signal_name, migrations.RunPython.noop),
    ]
