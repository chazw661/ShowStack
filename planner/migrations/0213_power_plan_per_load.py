"""Power plans move to the per-load manufacturer figures (phase 3B).

Schema:
* PowerDistributionPlan.power_factor (assumed, default 0.95).
* AmplifierAssignment.duty_cycle (speech / light / heavy / EDM / test tone,
  a multiplier on the 1/8-power figure) becomes ``programme`` (idle /
  normal = 1/8 power / heavy = 1/3 power). Old values map:
      speech, light_music              -> normal
      heavy_music, edm_concert, test_tone -> heavy
  Reversing maps normal -> light_music, heavy -> heavy_music, idle -> speech.
* AmplifierAssignment.load_ohms (blank = lowest published load) and
  calculated_watts_per_unit.

Data: every assignment's cached current and watts are recomputed with
planner.utils.power_estimate, so the plan pages and PDFs show the new
figures without anyone re-saving a row. This changes stored values on
deploy.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models

FORWARD = {
    'speech': 'normal', 'light_music': 'normal',
    'heavy_music': 'heavy', 'edm_concert': 'heavy', 'test_tone': 'heavy',
}
BACKWARD = {'normal': 'light_music', 'heavy': 'heavy_music', 'idle': 'speech'}


def map_forward(apps, schema_editor):
    Assignment = apps.get_model('planner', 'AmplifierAssignment')
    for old, new in FORWARD.items():
        Assignment.objects.filter(duty_cycle=old).update(programme=new)


def map_backward(apps, schema_editor):
    Assignment = apps.get_model('planner', 'AmplifierAssignment')
    for new, old in BACKWARD.items():
        Assignment.objects.filter(programme=new).update(duty_cycle=old)


def recompute(apps, schema_editor):
    from planner.utils.power_estimate import estimate, plan_voltage, uniform_channel_loads
    Assignment = apps.get_model('planner', 'AmplifierAssignment')
    rows = (Assignment.objects.select_related('distribution_plan', 'amplifier')
            .prefetch_related('amplifier__load_ratings', 'amplifier__voltage_factors'))
    for a in rows:
        plan = a.distribution_plan
        draw = estimate(a.amplifier, a.programme,
                        uniform_channel_loads(a.amplifier, a.load_ohms),
                        plan_voltage(plan.service_type), plan.power_factor)
        per_unit = (draw.current * Decimal(plan.transient_headroom)).quantize(
            Decimal('0.01'), ROUND_HALF_UP)
        a.calculated_current_per_unit = per_unit
        a.calculated_total_current = per_unit * a.quantity
        a.calculated_watts_per_unit = draw.watts
        a.save(update_fields=['calculated_current_per_unit', 'calculated_total_current',
                              'calculated_watts_per_unit'])


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0212_la716_provisional_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='powerdistributionplan',
            name='power_factor',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0.95'), max_digits=3,
                help_text="Assumed power factor, used only where an amp's current "
                          "is not published (current = watts / (volts x PF))"),
        ),
        migrations.AddField(
            model_name='amplifierassignment',
            name='programme',
            field=models.CharField(
                choices=[('idle', 'Idle (no signal)'),
                         ('normal', 'Normal programme (1/8 power)'),
                         ('heavy', 'Heavy programme (1/3 power)')],
                default='normal', max_length=10),
        ),
        migrations.RunPython(map_forward, map_backward),
        migrations.RemoveField(model_name='amplifierassignment', name='duty_cycle'),
        migrations.AddField(
            model_name='amplifierassignment',
            name='load_ohms',
            field=models.DecimalField(
                blank=True, decimal_places=1, max_digits=4, null=True,
                help_text='Blank = the lowest published load (highest draw)',
                verbose_name='Load per channel (Ω)'),
        ),
        migrations.AddField(
            model_name='amplifierassignment',
            name='calculated_watts_per_unit',
            field=models.IntegerField(
                blank=True, null=True,
                help_text='Estimated power per amplifier at the programme level'),
        ),
        migrations.RunPython(recompute, migrations.RunPython.noop),
    ]
