"""Issue #41: ensure the LA7.16i AmpModel template is 16-out SC32, not NL4.

The startCommand on Railway runs `load_amp_profiles` (which seeds the
AmplifierProfile table) but NOT `populate_amp_models`, so without this
migration, prod's existing LA7.16i AmpModel row keeps whatever shape it
was created with (which #41 reports as wrong). This migration upserts
the canonical values so the rack view renders the SC32 Out block.
"""

from django.db import migrations


def upsert_la7_16i(apps, schema_editor):
    AmpModel = apps.get_model('planner', 'AmpModel')
    AmpModel.objects.update_or_create(
        manufacturer='L-Acoustics',
        model_name='LA7.16i',
        defaults={
            'channel_count': 16,
            'has_analog_inputs': False,
            'has_aes_inputs': True,
            'has_avb_inputs': True,
            'nl4_connector_count': 0,
            'nl8_connector_count': 0,
            'cacom_output_count': 0,
            'sc32_connector_count': 1,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0169_soundvisionprediction_show_day_set_null'),
    ]

    operations = [
        migrations.RunPython(upsert_la7_16i, migrations.RunPython.noop),
    ]
