"""The CH block's routing on amps with more than four channels is the role
only (PA/LF/HF/SB). Their input routing is done in LA Network Manager, so an
A-D input suffix there means nothing. Migration 0214 calls this; so do the
tests.
"""

ROLE_AND_INPUT_MAX_CHANNELS = 4  # AmpChannel.ROLE_AND_INPUT_MAX_CHANNELS


def strip_input_suffix(AmpChannel):
    """'PA_B' -> 'PA' on every channel of an amp whose model has more than
    four channels. Returns how many rows changed. Idempotent: a role-only or
    empty value is left alone, and 4-channel amps are never touched."""
    rows = (AmpChannel.objects
            .filter(amp__amp_model__channel_count__gt=ROLE_AND_INPUT_MAX_CHANNELS,
                    channel_setting__contains='_')
            .only('pk', 'channel_setting'))
    changed = 0
    for ch in rows:
        ch.channel_setting = ch.channel_setting.partition('_')[0]
        ch.save(update_fields=['channel_setting'])
        changed += 1
    return changed
