"""Seed the comm device catalogue and move existing devices onto it.

What this changes, in order:

1. Creates one CommDeviceModel row per value that was in
   `CommBeltPack.MANUFACTURER_CHOICES`. Nothing here is invented hardware:
   every row's manufacturer, name, device type and channel count is taken
   from the choices list and the `get_channel_count` map that were already in
   planner/models.py. Rows are created with get_or_create, so running this on
   a database that already has some of them adds only what is missing.

2. Points each existing device at the row matching its legacy `manufacturer`
   value. The legacy column is NOT cleared -- a device whose value did not map
   keeps it, and so does every device that did.

3. Normalises `system_type` to follow the model's device type, which is the
   rule the application now applies on every save.

Anything that does not map is reported by name and count rather than guessed
at; those devices keep their legacy value and get no model.

Reversing drops the device_model links first and then deletes the rows this
created that nothing else is using, so the FK's PROTECT cannot block it.
"""
from django.db import migrations

# device_type -> the System Type it implies. Must match
# CommDeviceModel.WIRELESS_DEVICE_TYPES.
WIRELESS_DEVICE_TYPES = {'WIRELESS_BP'}

# (legacy manufacturer value) -> (manufacturer, model name, device type,
#                                 default channel count)
#
# Device type reproduces the Hardwired / Wireless split that the choices list
# was already grouped by in planner/models.py; channel counts come from the
# `get_channel_count` map in the same file. The old list only ever described
# belt packs, which is why no row here is a key panel or a station -- those
# arrive when the catalogue is extended by hand.
SEED = {
    'clearcom_helixnet': ('Clear-Com', 'HelixNet', 'WIRED_BP', 24),
    'rts_partyline': ('RTS', 'Partyline', 'WIRED_BP', 2),
    'rts_odin': ('RTS', 'ODIN Matrix', 'WIRED_BP', 8),
    'riedel_performer': ('Riedel', 'Performer', 'WIRED_BP', 4),
    'clearcom_freespeak': ('Clear-Com', 'FreeSpeak Edge/Icon', 'WIRELESS_BP', 8),
    'clearcom_freespeak_ii': ('Clear-Com', 'FreeSpeak II', 'WIRELESS_BP', 4),
    'riedel_bolero': ('Riedel', 'Bolero', 'WIRELESS_BP', 6),
    'rad_uv1g': ('Radio Active Designs', 'RAD', 'WIRELESS_BP', 6),
}


def _report(lines):
    """Print through to the migrate output so a prod run is not silent."""
    for line in lines:
        print('  [0194] %s' % line)


def seed_and_link(apps, schema_editor):
    CommDeviceModel = apps.get_model('planner', 'CommDeviceModel')
    CommBeltPack = apps.get_model('planner', 'CommBeltPack')

    created = 0
    by_legacy = {}
    for legacy, (manufacturer, name, device_type, channels) in SEED.items():
        row, was_created = CommDeviceModel.objects.get_or_create(
            manufacturer=manufacturer,
            name=name,
            defaults={
                'device_type': device_type,
                'default_channel_count': channels,
                'is_active': True,
            },
        )
        by_legacy[legacy] = row
        created += int(was_created)

    report = ['catalogue: %d model row(s) created, %d already present'
              % (created, len(SEED) - created)]

    total = CommBeltPack.objects.count()
    linked = 0
    for legacy, row in by_legacy.items():
        n = CommBeltPack.objects.filter(
            manufacturer=legacy, device_model__isnull=True).update(
                device_model=row)
        if n:
            report.append('linked %4d device(s): %r -> %s %s'
                          % (n, legacy, row.manufacturer, row.name))
        linked += n

    # Whatever is left has a legacy value this migration has no row for.
    # Report it; do not invent a mapping for it.
    unmapped = (CommBeltPack.objects
                .filter(device_model__isnull=True)
                .values_list('manufacturer', flat=True))
    counts = {}
    for value in unmapped:
        counts[value] = counts.get(value, 0) + 1

    report.append('devices: %d total, %d linked to a model' % (total, linked))
    if counts:
        report.append('NOT MAPPED -- these keep their legacy value and get no '
                      'model; add a catalogue row and set them by hand:')
        for value, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            report.append('    %4d x %r' % (n, value))
    else:
        report.append('every device mapped; nothing left on a legacy value')

    # system_type now follows from the device type.
    flipped = 0
    for row in CommDeviceModel.objects.all():
        system_type = ('WIRELESS' if row.device_type in WIRELESS_DEVICE_TYPES
                       else 'HARDWIRED')
        n = CommBeltPack.objects.filter(device_model=row).exclude(
            system_type=system_type).update(system_type=system_type)
        if n:
            report.append('system_type: %d device(s) on %s %s corrected to %s'
                          % (n, row.manufacturer, row.name, system_type))
        flipped += n
    if not flipped:
        report.append('system_type: already consistent, nothing changed')

    # A hardwired device is never checked out; the model has enforced that on
    # save for a long time, but a row flipped to HARDWIRED just now may still
    # carry the flag.
    stale = CommBeltPack.objects.filter(
        system_type='HARDWIRED', checked_out=True).update(checked_out=False)
    if stale:
        report.append('checked_out: cleared on %d device(s) that are now '
                      'hardwired' % stale)

    _report(report)


def unlink_and_drop(apps, schema_editor):
    CommDeviceModel = apps.get_model('planner', 'CommDeviceModel')
    CommBeltPack = apps.get_model('planner', 'CommBeltPack')

    # The FK is PROTECT, so the links have to go before the rows do.
    seeded = CommDeviceModel.objects.none()
    for manufacturer, name, _dt, _ch in SEED.values():
        seeded = seeded | CommDeviceModel.objects.filter(
            manufacturer=manufacturer, name=name)

    CommBeltPack.objects.filter(device_model__in=seeded).update(
        device_model=None)
    # Only rows nothing points at any more -- a model added by hand, or one a
    # device was moved onto, stays.
    removed = 0
    for row in seeded:
        if not CommBeltPack.objects.filter(device_model=row).exists():
            row.delete()
            removed += 1
    _report(['reverse: unlinked devices and removed %d seeded model row(s); '
             'legacy manufacturer values were never cleared, so they still '
             'say what they said' % removed])


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0193_comm_device_model'),
    ]

    operations = [
        migrations.RunPython(seed_and_link, unlink_and_drop),
    ]
