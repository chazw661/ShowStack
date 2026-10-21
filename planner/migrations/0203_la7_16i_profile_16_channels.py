"""#15: the LA7.16i Amplifier Profile has 16 channels, not 7.

load_amp_profiles shipped it as 7 and skips on every deploy once any profile
exists, so fixing the command alone would never reach prod. Only a row still
carrying the shipped value is changed; one a superuser has edited by hand is
left as it is. Display only: the power maths reads idle/rated watts, voltage
and power factor, not the channel count.
"""

from django.db import migrations

OLD_NOTES = '7 channels, 800W @ 4Ω per channel, touring grade'
NEW_NOTES = '16 channels, 800W @ 4Ω per channel, touring grade'


def sixteen(apps, schema_editor):
    AmplifierProfile = apps.get_model('planner', 'AmplifierProfile')
    rows = AmplifierProfile.objects.filter(model='LA7.16i', channels=7)
    rows.filter(notes=OLD_NOTES).update(notes=NEW_NOTES)
    rows.update(channels=16)


def seven(apps, schema_editor):
    AmplifierProfile = apps.get_model('planner', 'AmplifierProfile')
    rows = AmplifierProfile.objects.filter(model='LA7.16i', channels=16)
    rows.filter(notes=NEW_NOTES).update(notes=OLD_NOTES)
    rows.update(channels=7)


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0202_staff_for_owners_and_paid_accounts'),
    ]

    operations = [
        migrations.RunPython(sixteen, seven),
    ]
