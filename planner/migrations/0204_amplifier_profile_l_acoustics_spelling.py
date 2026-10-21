"""One spelling for the manufacturer: "L-Acoustics".

load_amp_profiles shipped LA8, LA4X and LA12X as "L'Acoustics" and the
LA7.16i as "L-Acoustics" (the spelling AmpModel uses throughout), so the
manufacturer filter listed the brand twice. Name only: no power figure,
channel count or other field is touched.
"""

from django.db import migrations

VARIANTS = ("L'Acoustics", 'L’Acoustics')


def normalize(apps, schema_editor):
    AmplifierProfile = apps.get_model('planner', 'AmplifierProfile')
    AmplifierProfile.objects.filter(manufacturer__in=VARIANTS).update(
        manufacturer='L-Acoustics')


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0203_la7_16i_profile_16_channels'),
    ]

    # No reverse: the old spelling was the inconsistency, and the original
    # per-row spelling is not worth recording to restore.
    operations = [
        migrations.RunPython(normalize, migrations.RunPython.noop),
    ]
