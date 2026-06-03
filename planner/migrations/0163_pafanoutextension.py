"""Issue #23: PA Cable extension redesign.

Move the single (extension_cable, extension_length) pair on PAFanOut into
its own PAFanOutExtension child model so a fan-out can have N extensions
each with its own quantity. Backfills one extension per existing fan-out
that had both fields populated, then drops the old fields.
"""
import django.core.validators
from django.db import migrations, models


def backfill_extensions(apps, schema_editor):
    PAFanOut = apps.get_model('planner', 'PAFanOut')
    PAFanOutExtension = apps.get_model('planner', 'PAFanOutExtension')
    qs = PAFanOut.objects.exclude(extension_cable='').exclude(extension_length=0)
    for fo in qs:
        # Historically the summary multiplied extension count by fan-out
        # quantity. Preserve that interpretation in the new per-extension
        # quantity field so totals don't shift on deploy. Engineers can
        # tweak ext.quantity afterwards.
        PAFanOutExtension.objects.create(
            cable_schedule=fo.cable_schedule,
            fan_out=fo,
            extension_cable=fo.extension_cable,
            extension_length=fo.extension_length,
            quantity=max(fo.quantity or 1, 1),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0162_allow_blank_device_input_signal_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='PAFanOutExtension',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('extension_cable', models.CharField(choices=[('NL4', 'NL4'), ('NL8', 'NL8')], max_length=10, verbose_name='Extension Cable')),
                ('extension_length', models.IntegerField(choices=[(6, "6'"), (25, "25'"), (50, "50'"), (100, "100'"), (150, "150'")], verbose_name='Extension Length')),
                ('quantity', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('cable_schedule', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='fan_out_extensions', to='planner.pacableschedule')),
                ('fan_out', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='extensions', to='planner.pafanout')),
            ],
            options={
                'verbose_name': 'Fan-out Extension',
                'verbose_name_plural': 'Fan-out Extensions',
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(backfill_extensions, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='pafanout',
            name='extension_cable',
        ),
        migrations.RemoveField(
            model_name='pafanout',
            name='extension_length',
        ),
    ]
