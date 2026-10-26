"""CH-block routing on amps with more than four channels is the role only.

* The field's choices gain role-only values (PA, LF, HF, SB). The rack page
  offers those on an amp with more than four channels, and keeps role + A-D
  (PA_A ... SB_D) on a 4-channel amp.
* DATA: every channel of an amp whose model has more than four channels that
  holds a suffixed value is converted to its role ('PA_B' -> 'PA'). Prints how
  many rows changed. Idempotent: a second run changes nothing.

4-channel amps and amps with no model are not touched. Reversing it does not
put the suffixes back (which input it was is gone); the choices revert.
"""

from django.db import migrations, models


def forwards(apps, schema_editor):
    from planner.utils.channel_routing import strip_input_suffix
    changed = strip_input_suffix(apps.get_model('planner', 'AmpChannel'))
    print(f'\n  planner.0214: {changed} channel setting(s) on amps with more than '
          f'4 channels converted to role only.')


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0213_power_plan_per_load'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ampchannel',
            name='channel_setting',
            field=models.CharField(blank=True, choices=[('', '---------'), ('PA_A', 'PA_A'), ('PA_B', 'PA_B'), ('PA_C', 'PA_C'), ('PA_D', 'PA_D'), ('LF_A', 'LF_A'), ('LF_B', 'LF_B'), ('LF_C', 'LF_C'), ('LF_D', 'LF_D'), ('HF_A', 'HF_A'), ('HF_B', 'HF_B'), ('HF_C', 'HF_C'), ('HF_D', 'HF_D'), ('SB_A', 'SB_A'), ('SB_B', 'SB_B'), ('SB_C', 'SB_C'), ('SB_D', 'SB_D'), ('PA', 'PA'), ('LF', 'LF'), ('HF', 'HF'), ('SB', 'SB')], default='', help_text='Speaker-zone routing label for this channel', max_length=20, verbose_name='Channel Setting'),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
