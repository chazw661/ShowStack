"""Power plans generated from the amp module (Phase C).

Schema, all additive:
* Amp.leg (blank = auto).
* AmplifierProfile.needs_three_phase.
* PowerDistributionPlan: generated_at, source_fingerprint, programme,
  other_electronics_watts, the Split-Phase 120/240V service, and at most one
  generated plan per project.
* AmplifierAssignment: generated, source_amp, amp_leg.

other_electronics_watts is added at 0 and only then given its 2000 W
default, so plans that exist keep their totals; new plans get 2000 W.

Data: needs_three_phase is set on the L-Acoustics profiles other than the
LA4X (LA8, LA12X, LA7.16i, LA7.16). No plan, row or amp changes; no leg is
set on any amp. A fresh database gets the flag from load_amp_profiles.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


THREE_PHASE_MODELS = ['LA8', 'LA12X', 'LA7.16i', 'LA7.16']


def flag_three_phase(apps, schema_editor):
    Profile = apps.get_model('planner', 'AmplifierProfile')
    count = Profile.objects.filter(manufacturer='L-Acoustics',
                                   model__in=THREE_PHASE_MODELS).update(needs_three_phase=True)
    print(f"\n  planner.0216: {count} amplifier profile(s) marked as needing 3-phase distro.")


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0215_per_leg_phase_to_neutral'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='amp',
            name='leg',
            field=models.CharField(blank=True, choices=[('', 'Auto'), ('L1', 'L1'), ('L2', 'L2'), ('L3', 'L3')], default='', help_text='Mains leg; blank = balanced by the generated power plan', max_length=2),
        ),
        migrations.AddField(
            model_name='amplifierassignment',
            name='amp_leg',
            field=models.CharField(blank=True, default='', editable=False, max_length=2),
        ),
        migrations.AddField(
            model_name='amplifierassignment',
            name='generated',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='amplifierassignment',
            name='source_amp',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='power_plan_rows', to='planner.amp'),
        ),
        migrations.AddField(
            model_name='amplifierprofile',
            name='needs_three_phase',
            field=models.BooleanField(default=False, help_text='Power plans on a split- or single-phase service warn about this amp', verbose_name='Needs 3-phase distro'),
        ),
        migrations.AddField(
            model_name='powerdistributionplan',
            name='generated_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='powerdistributionplan',
            name='other_electronics_watts',
            field=models.PositiveIntegerField(default=0, help_text='Consoles, processors, playback; spread evenly across the legs', verbose_name='Other audio electronics (W)'),
        ),
        migrations.AlterField(
            model_name='powerdistributionplan',
            name='other_electronics_watts',
            field=models.PositiveIntegerField(default=2000, help_text='Consoles, processors, playback; spread evenly across the legs', verbose_name='Other audio electronics (W)'),
        ),
        migrations.AddField(
            model_name='powerdistributionplan',
            name='programme',
            field=models.CharField(choices=[('idle', 'Idle (no signal)'), ('normal', 'Normal programme (1/8 power)'), ('heavy', 'Heavy programme (1/3 power)')], default='normal', help_text='Programme level of the rows generated from the amp module', max_length=10),
        ),
        migrations.AddField(
            model_name='powerdistributionplan',
            name='source_fingerprint',
            field=models.CharField(blank=True, default='', editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='powerdistributionplan',
            name='service_type',
            field=models.CharField(choices=[('3phase_4wire_208', '3-Phase 4-Wire 208V'), ('3phase_5wire_208', '3-Phase 5-Wire 208V'), ('3phase_4wire_240', '3-Phase 4-Wire 240/415V'), ('3phase_5wire_400', '3-Phase 5-Wire 230/400V'), ('split_phase_120_240', 'Split-Phase 120/240V'), ('single_phase_120', 'Single Phase 120V'), ('single_phase_240', 'Single Phase 240V')], default='3phase_4wire_208', max_length=50),
        ),
        migrations.AddConstraint(
            model_name='powerdistributionplan',
            constraint=models.UniqueConstraint(condition=models.Q(('generated_at__isnull', False)), fields=('project',), name='one_generated_power_plan_per_project'),
        ),
        migrations.RunPython(flag_three_phase, migrations.RunPython.noop),
    ]
