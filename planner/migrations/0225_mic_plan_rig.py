import django.core.validators
from django.db import migrations, models


def to_rig(body, hh, spare):
    """(wireless_channels, handheld_channels, spare_handhelds) for the old
    counts. The old spare came out of hh_count, so capacity is unchanged:
    a rig only when both counts were set."""
    if body is not None and hh is not None:
        channels = body + hh
        return (channels or None), (hh if channels else 0), (min(1, hh) if spare and channels else 0)
    return None, 0, (1 if spare else 0)


def forwards(apps, schema_editor):
    MicPlanSettings = apps.get_model('planner', 'MicPlanSettings')
    for s in MicPlanSettings.objects.all():
        s.wireless_channels, s.handheld_channels, s.spare_handhelds = to_rig(
            s.body_pack_count, s.hh_count, s.emergency_spare_hh)
        s.save(update_fields=['wireless_channels', 'handheld_channels', 'spare_handhelds'])


def backwards(apps, schema_editor):
    MicPlanSettings = apps.get_model('planner', 'MicPlanSettings')
    for s in MicPlanSettings.objects.all():
        if s.wireless_channels is not None:
            s.body_pack_count = s.wireless_channels - s.handheld_channels
            s.hh_count = s.handheld_channels
        s.emergency_spare_hh = s.spare_handhelds > 0
        s.save(update_fields=['body_pack_count', 'hh_count', 'emergency_spare_hh'])


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0224_mic_plan_push'),
    ]

    operations = [
        migrations.AddField(
            model_name='micplansettings',
            name='wireless_channels',
            field=models.PositiveSmallIntegerField(blank=True, null=True, validators=[
                django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(200)],
                verbose_name='Wireless channels'),
        ),
        migrations.AddField(
            model_name='micplansettings',
            name='handheld_channels',
            field=models.PositiveSmallIntegerField(default=0, validators=[
                django.core.validators.MaxValueValidator(200)], verbose_name='Handhelds (last N channels)'),
        ),
        migrations.AddField(
            model_name='micplansettings',
            name='spare_handhelds',
            field=models.PositiveSmallIntegerField(default=0, validators=[
                django.core.validators.MaxValueValidator(200)],
                verbose_name='Spare handhelds (kept unassigned at the end)'),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name='micplansettings', name='body_pack_count'),
        migrations.RemoveField(model_name='micplansettings', name='hh_count'),
        migrations.RemoveField(model_name='micplansettings', name='emergency_spare_hh'),
    ]
