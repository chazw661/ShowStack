"""Issue #29: split amp-rack locations into their own table (AmpLocation)
so the Amp Assignment page no longer lists equipment locations.

Data migration: any Location currently referenced by an Amp or AmpDivider
is copied into AmpLocation, the FK is repointed, and the original Location
row is deleted only if no other equipment (Console, Device, SystemProcessor,
CommBeltPack) still references it.
"""
from django.db import migrations, models
import django.db.models.deletion


def forwards_copy_amp_locations(apps, schema_editor):
    Location = apps.get_model('planner', 'Location')
    AmpLocation = apps.get_model('planner', 'AmpLocation')
    Amp = apps.get_model('planner', 'Amp')
    AmpDivider = apps.get_model('planner', 'AmpDivider')

    # Collect Location IDs currently referenced by amps or amp dividers.
    used_ids = set(Amp.objects.exclude(location__isnull=True)
                   .values_list('location_id', flat=True))
    used_ids |= set(AmpDivider.objects.exclude(location__isnull=True)
                    .values_list('location_id', flat=True))

    # Copy each used Location into AmpLocation, keep an old_id → new_id map.
    old_to_new = {}
    for loc in Location.objects.filter(pk__in=used_ids):
        new_loc = AmpLocation.objects.create(
            project=loc.project,
            name=loc.name,
            sort_order=loc.sort_order,
            description=loc.description,
        )
        old_to_new[loc.pk] = new_loc.pk

    # Repoint the temp FK on every Amp and AmpDivider.
    for amp in Amp.objects.exclude(location__isnull=True):
        new_id = old_to_new.get(amp.location_id)
        if new_id is not None:
            amp.amp_location_temp_id = new_id
            amp.save(update_fields=['amp_location_temp'])

    for div in AmpDivider.objects.exclude(location__isnull=True):
        new_id = old_to_new.get(div.location_id)
        if new_id is not None:
            div.amp_location_temp_id = new_id
            div.save(update_fields=['amp_location_temp'])


def reverse_copy_amp_locations(apps, schema_editor):
    # Forward is data only — reverse just clears the temp FK and AmpLocation
    # rows. Schema rollback is handled by Django's reverse operations.
    Amp = apps.get_model('planner', 'Amp')
    AmpDivider = apps.get_model('planner', 'AmpDivider')
    AmpLocation = apps.get_model('planner', 'AmpLocation')
    Amp.objects.update(amp_location_temp=None)
    AmpDivider.objects.update(amp_location_temp=None)
    AmpLocation.objects.all().delete()


def cleanup_orphan_locations(apps, schema_editor):
    """Delete Location rows that USED to be amp locations and are no longer
    referenced by any non-amp equipment. A row counts as 'used to be an amp
    location' if there's a matching AmpLocation in the same project with the
    same name (we copied it earlier with identical fields)."""
    Location = apps.get_model('planner', 'Location')
    AmpLocation = apps.get_model('planner', 'AmpLocation')

    amp_pairs = set(AmpLocation.objects.values_list('project_id', 'name'))
    for loc in Location.objects.all():
        if (loc.project_id, loc.name) not in amp_pairs:
            continue
        in_use = (
            loc.devices.exists()
            or loc.consoles.exists()
            or loc.system_processors.exists()
            or loc.comm_beltpacks.exists()
        )
        if not in_use:
            loc.delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0165_add_amp_preset'),
    ]

    operations = [
        migrations.CreateModel(
            name='AmpLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='e.g., HL LA Racks, HR LA Racks, SL Sub Racks', max_length=100)),
                ('sort_order', models.IntegerField(default=0)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='planner.project')),
            ],
            options={
                'verbose_name': 'Amp Location',
                'verbose_name_plural': 'Amp Locations',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AlterField(
            model_name='location',
            name='name',
            field=models.CharField(help_text='e.g., FOH, Monitor World, Stage', max_length=100),
        ),
        migrations.AddField(
            model_name='amp',
            name='amp_location_temp',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='amps_temp',
                to='planner.amplocation',
            ),
        ),
        migrations.AddField(
            model_name='ampdivider',
            name='amp_location_temp',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='amp_dividers_temp',
                to='planner.amplocation',
            ),
        ),
        migrations.RunPython(forwards_copy_amp_locations, reverse_copy_amp_locations),
        migrations.RemoveField(
            model_name='amp',
            name='location',
        ),
        migrations.RemoveField(
            model_name='ampdivider',
            name='location',
        ),
        migrations.RenameField(
            model_name='amp',
            old_name='amp_location_temp',
            new_name='location',
        ),
        migrations.RenameField(
            model_name='ampdivider',
            old_name='amp_location_temp',
            new_name='location',
        ),
        migrations.AlterField(
            model_name='amp',
            name='location',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='amps',
                to='planner.amplocation',
            ),
        ),
        migrations.AlterField(
            model_name='ampdivider',
            name='location',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='amp_dividers',
                to='planner.amplocation',
            ),
        ),
        migrations.RunPython(cleanup_orphan_locations, noop),
    ]
