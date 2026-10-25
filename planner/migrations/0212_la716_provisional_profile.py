"""Data: give the LA7.16 (touring) amp model power figures, provisionally.

* AmpModel manufacturer "L'Acoustics" -> "L-Acoustics" (any row).
* An "L-Acoustics LA7.16" AmplifierProfile with load ratings and voltage
  factors copied from the LA7.16i, marked provisional (figures_status set,
  ratings unverified). Skipped when there is no LA7.16i profile yet: a fresh
  database gets it from load_amp_profiles instead.
* The LA7.16 AmpModel linked to it, where it has no profile.

LA7.16 and LA7.16i stay separate rows: they are different products.
Matches by manufacturer / model, never by id. Idempotent; nothing that
already exists is changed. Reversing it does nothing (the rows are kept).
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from planner.utils.provisional_profiles import apply
    apply(apps.get_model('planner', 'AmpModel'),
          apps.get_model('planner', 'AmplifierProfile'),
          apps.get_model('planner', 'AmplifierLoadRating'),
          apps.get_model('planner', 'AmplifierVoltageFactor'))


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0211_amplifier_profile_figures_status'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
