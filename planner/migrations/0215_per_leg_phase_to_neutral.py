"""Per-leg current at the phase-to-neutral voltage.

A power plan row's current is now its estimated watts / (phase-to-neutral
volts x the plan's assumed power factor), times the transient headroom:
120 V on 208Y/120, 240 V on 240/415, 230 V on 230/400, the service voltage on
single-phase. It used to be the published current converted to the service
voltage (208 V), which understated a 208Y/120 leg by about 208/120 = 1.73.

Schema: service_type gains 3-Phase 5-Wire 230/400V, and 3-Phase 4-Wire 240V
is relabelled 240/415V (the key is unchanged). power_factor's help text.

Data: every assignment's cached current is recomputed, so the plan pages,
the admin and the system report PDF show the new figures without anyone
re-saving a row. This changes stored values on deploy. Watts are unchanged.
Not reversed: roll back from a backup.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models


def recompute(apps, schema_editor):
    from planner.utils.power_estimate import plan_estimate, uniform_channel_loads
    Assignment = apps.get_model('planner', 'AmplifierAssignment')
    rows = (Assignment.objects.select_related('distribution_plan', 'amplifier')
            .prefetch_related('amplifier__load_ratings', 'amplifier__voltage_factors'))
    changed = 0
    for a in rows:
        plan = a.distribution_plan
        draw = plan_estimate(a.amplifier, a.programme,
                             uniform_channel_loads(a.amplifier, a.load_ohms),
                             plan.service_type, plan.power_factor)
        per_unit = (draw.current * Decimal(plan.transient_headroom)).quantize(
            Decimal('0.01'), ROUND_HALF_UP)
        if per_unit != a.calculated_current_per_unit:
            changed += 1
        a.calculated_current_per_unit = per_unit
        a.calculated_total_current = per_unit * a.quantity
        a.calculated_watts_per_unit = draw.watts
        a.save(update_fields=['calculated_current_per_unit', 'calculated_total_current',
                              'calculated_watts_per_unit'])
    print(f"\n  planner.0215: {changed} power plan row(s) recomputed at the "
          f"phase-to-neutral voltage.")


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0214_channel_setting_role_only'),
    ]

    operations = [
        migrations.AlterField(
            model_name='powerdistributionplan',
            name='power_factor',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.95'), help_text='Assumed power factor: current on a leg = watts / (phase-to-neutral volts x PF)', max_digits=3),
        ),
        migrations.AlterField(
            model_name='powerdistributionplan',
            name='service_type',
            field=models.CharField(choices=[('3phase_4wire_208', '3-Phase 4-Wire 208V'), ('3phase_5wire_208', '3-Phase 5-Wire 208V'), ('3phase_4wire_240', '3-Phase 4-Wire 240/415V'), ('3phase_5wire_400', '3-Phase 5-Wire 230/400V'), ('single_phase_120', 'Single Phase 120V'), ('single_phase_240', 'Single Phase 240V')], default='3phase_4wire_208', max_length=50),
        ),
        migrations.RunPython(recompute, migrations.RunPython.noop),
    ]
