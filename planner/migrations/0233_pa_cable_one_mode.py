"""PA cable runs: one entry mode (PR 2b-1).

``amp_location`` was a hidden FK to the equipment ``Location`` that nothing
ever wrote. It becomes the run's "From amp rack", an FK to ``AmpLocation``.
Re-pointing a column that held values would silently attach them to
unrelated amp racks, so the migration refuses to run if any row has one.
"""
import django.db.models.deletion
from django.db import migrations, models


def refuse_if_amp_location_written(apps, schema_editor):
    PACableSchedule = apps.get_model('planner', 'PACableSchedule')
    rows = list(PACableSchedule.objects.filter(amp_location__isnull=False)
                .values_list('pk', flat=True)[:20])
    if rows:
        raise RuntimeError(
            'PACableSchedule.amp_location is set on rows {} -- it was never meant to be '
            'written. Clear or move those values before re-pointing the column at '
            'AmpLocation.'.format(rows))


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0232_mic_planner_walkthrough'),
    ]

    operations = [
        migrations.RunPython(refuse_if_amp_location_written, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='pazone',
            options={'ordering': ['id'], 'verbose_name': 'Cable Label', 'verbose_name_plural': 'Cable Labels'},
        ),
        migrations.AddField(
            model_name='pacableschedule',
            name='speaker_arrays',
            field=models.ManyToManyField(blank=True, help_text='Optional: the Soundvision arrays this run feeds.', related_name='pa_cable_runs', to='planner.speakerarray', verbose_name='Linked speaker arrays'),
        ),
        migrations.AlterField(
            model_name='pacableschedule',
            name='amp',
            field=models.ForeignKey(blank=True, help_text='The amp this cable leaves from. Sets From amp rack to its rack.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pa_cables', to='planner.amp', verbose_name='From amp'),
        ),
        migrations.AlterField(
            model_name='pacableschedule',
            name='amp_location',
            field=models.ForeignKey(blank=True, help_text='The amp rack this cable leaves from, when no single amp is picked.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pa_cables', to='planner.amplocation', verbose_name='From amp rack'),
        ),
        migrations.AlterField(
            model_name='pacableschedule',
            name='destination',
            field=models.CharField(default='', help_text="Speaker or fan-out destination, e.g. 'KIVA DELAY 2 & 3'", max_length=50, null=True, verbose_name='To'),
        ),
        migrations.AlterField(
            model_name='pacableschedule',
            name='entry_mode',
            field=models.CharField(choices=[('text', 'Free text'), ('linked', 'From Soundvision / Amps')], default='text', editable=False, max_length=10),
        ),
        migrations.AlterField(
            model_name='pacableschedule',
            name='label',
            field=models.ForeignKey(blank=True, help_text='The label printed on the cable, e.g. HL, FF1', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cables', to='planner.pazone', verbose_name='Cable Label'),
        ),
        migrations.AlterField(
            model_name='pacableschedule',
            name='speaker_array',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pa_cables', to='planner.speakerarray'),
        ),
        migrations.AlterField(
            model_name='pazone',
            name='name',
            field=models.CharField(help_text='Short cable label (e.g., HL, HR, FF1)', max_length=20),
        ),
        migrations.AlterField(
            model_name='pazone',
            name='zone_type',
            field=models.CharField(choices=[('MAIN', 'Main Array'), ('SUB', 'Subwoofer'), ('FILL', 'Fill'), ('DELAY', 'Delay'), ('MONITOR', 'Monitor'), ('CUSTOM', 'Custom')], default='CUSTOM', help_text='Category', max_length=20),
        ),
    ]
