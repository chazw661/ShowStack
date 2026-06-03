"""Issue #23 follow-up: model couplers separately from fan-outs.

The COUPLER entries that used to live in PAFanOut.FAN_OUT_CHOICES are
moved to their own PACoupler table so the cable edit page can show an
"Add Coupler" affordance distinct from "Add Fan-out". Migrates existing
coupler-type fan-outs to PACoupler rows and deletes the originals
(their PAFanOutExtension children, if any, cascade — couplers don't
carry extensions in the new model).
"""
import django.core.validators
from django.db import migrations, models


# Legacy fan_out_type value -> new PACoupler.coupler_type value.
# 'CACOM COUPLER' was stored with a space; normalize to the underscore
# form used by the new model's choices.
_LEGACY_COUPLER_MAP = {
    'NL4_COUPLER': 'NL4_COUPLER',
    'NL8_COUPLER': 'NL8_COUPLER',
    'CACOM COUPLER': 'CACOM_COUPLER',
}


def backfill_couplers(apps, schema_editor):
    PAFanOut = apps.get_model('planner', 'PAFanOut')
    PACoupler = apps.get_model('planner', 'PACoupler')
    legacy_fan_outs = PAFanOut.objects.filter(fan_out_type__in=_LEGACY_COUPLER_MAP.keys())
    to_delete = []
    for fo in legacy_fan_outs:
        PACoupler.objects.create(
            cable_schedule=fo.cable_schedule,
            coupler_type=_LEGACY_COUPLER_MAP[fo.fan_out_type],
            quantity=max(fo.quantity or 1, 1),
        )
        to_delete.append(fo.id)
    PAFanOut.objects.filter(id__in=to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0163_pafanoutextension'),
    ]

    operations = [
        migrations.CreateModel(
            name='PACoupler',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('coupler_type', models.CharField(choices=[('NL4_COUPLER', 'NL4 Coupler'), ('NL8_COUPLER', 'NL8 Coupler'), ('CACOM_COUPLER', 'CACOM Coupler')], max_length=20)),
                ('quantity', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('cable_schedule', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='couplers', to='planner.pacableschedule')),
            ],
            options={
                'verbose_name': 'PA Coupler',
                'verbose_name_plural': 'PA Couplers',
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(backfill_couplers, migrations.RunPython.noop),
    ]
