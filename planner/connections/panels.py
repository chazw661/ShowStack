"""What an amp model's rear panel calls its inputs. Pure.

The wiring diagram names an amp's input slots after the panel: on the
L-Acoustics amps below, input rows 1-4 of the rack view are "IN A".."IN D",
analog (XLR) or AES on the same letter. AVB has no panel socket and stays
"AVB n". A model not listed here, or a row past the panel's last input, keeps
the numeric name ("XLR 5").

Keyed by the Amp Model Template's manufacturer and model name, compared on
letters and digits only, so "L-Acoustics LA7.16i" and "L'Acoustics la716i"
are the same model.
"""

L_ACOUSTICS_INPUTS = ('IN A', 'IN B', 'IN C', 'IN D')

PANEL_INPUTS = {
    ('lacoustics', 'la12x'): L_ACOUSTICS_INPUTS,
    ('lacoustics', 'la4x'): L_ACOUSTICS_INPUTS,
    ('lacoustics', 'la8'): L_ACOUSTICS_INPUTS,
    ('lacoustics', 'la716i'): L_ACOUSTICS_INPUTS,
}


def _key(text):
    return ''.join(ch for ch in (text or '').casefold() if ch.isalnum())


def panel_inputs(manufacturer, model_name):
    """The panel's input names in row order, or () for an unmapped model."""
    return PANEL_INPUTS.get((_key(manufacturer), _key(model_name)), ())


def panel_name(panel, number):
    """Row ``number``'s panel name, or None past the panel (or unmapped)."""
    if isinstance(number, int) and 1 <= number <= len(panel):
        return panel[number - 1]
    return None
