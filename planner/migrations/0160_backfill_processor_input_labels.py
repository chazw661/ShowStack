"""Issue #16 data migration.

Before the next migration drops origin_device_output from P1Input/GalaxyInput,
copy the device-output's signal_name (or 'Output N' fallback) into label for
any row where label is empty/null and an origin is set. This preserves the
informational content the FK used to render in admin/exports.
"""
from django.db import migrations


def _label_from_origin(origin_output):
    """Mirror the old admin dropdown label logic."""
    if origin_output is None:
        return ''
    name = (getattr(origin_output, 'signal_name', '') or '').strip()
    if name:
        return name
    num = getattr(origin_output, 'output_number', None)
    return f'Output {num}' if num else 'Unnamed Output'


def backfill_labels(apps, schema_editor):
    P1Input = apps.get_model('planner', 'P1Input')
    GalaxyInput = apps.get_model('planner', 'GalaxyInput')

    for inp in P1Input.objects.filter(origin_device_output__isnull=False).select_related('origin_device_output'):
        if (inp.label or '').strip():
            continue
        new_label = _label_from_origin(inp.origin_device_output)[:100]
        if new_label:
            inp.label = new_label
            inp.save(update_fields=['label'])

    for inp in GalaxyInput.objects.filter(origin_device_output__isnull=False).select_related('origin_device_output'):
        if (inp.label or '').strip():
            continue
        new_label = _label_from_origin(inp.origin_device_output)[:100]
        if new_label:
            inp.label = new_label
            inp.save(update_fields=['label'])


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0159_remove_consoleauxoutput_default_record_color_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_labels, migrations.RunPython.noop),
    ]
