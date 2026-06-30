from django.db import migrations


SEED_OPTIONS = [
    'Shure AD1',
    'Shure AD2',
    'Shure ADX1',
    'Shure ADX2',
    'Shure - Beta 87',
    'Senn - MKH416',
    'Senn - MD431',
    'USB DI',
    'AVIO',
    'Arcadia Dante',
    'RUIO-16',
    'FOH',
    'RME',
    'XLR',
    'Shure - B91',
    'Shure - B52',
    'Shure - B98',
    'Shure - Beta 181',
    'Shure - SM58',
    'Shure - SM57',
    'Shure - KSM137',
    'Shure - KSM141',
    'Shure - KSM32',
    'Shure - KSM27',
    'Direct Box',
    'Senn - e604',
    'Senn - e901',
    'Senn - e904',
    'Senn - e906',
    'Senn - e935s',
    'Senn - e945',
    'Senn - MD421',
]


def seed_options(apps, schema_editor):
    SourceHardwareOption = apps.get_model('planner', 'SourceHardwareOption')
    for index, label in enumerate(SEED_OPTIONS, start=1):
        SourceHardwareOption.objects.update_or_create(
            label=label,
            defaults={'sort_order': index * 10},
        )


def unseed_options(apps, schema_editor):
    SourceHardwareOption = apps.get_model('planner', 'SourceHardwareOption')
    SourceHardwareOption.objects.filter(label__in=SEED_OPTIONS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0173_sourcehardwareoption_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_options, unseed_options),
    ]
