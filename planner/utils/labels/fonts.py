"""The embedded label font.

ReportLab's built-in Helvetica is a Type 1 font with WinAnsi encoding: it has
no glyph for "ễ", "Đ" or "Ł", and draws a blank box for them. Presenter names
come from every country a corporate show flies speakers in from, so the
labels embed Noto Sans (SIL OFL 1.1, Latin + Latin Extended + Vietnamese).
ReportLab subsets on embed, so a PDF carries only the glyphs it uses.

The files live in planner/data/fonts/, outside static/: the server reads them
and nothing serves them. Version and checksums are in that folder's README.
"""

import re
import unicodedata
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).resolve().parents[2] / 'data' / 'fonts'

REGULAR = 'ShowStackLabel'
SEMIBOLD = 'ShowStackLabel-SemiBold'
BOLD = 'ShowStackLabel-Bold'

_FILES = {
    REGULAR: 'NotoSans-Regular.ttf',
    SEMIBOLD: 'NotoSans-SemiBold.ttf',
    BOLD: 'NotoSans-Bold.ttf',
}

_registered = False


def register_fonts():
    """Register the label fonts with ReportLab once per process."""
    global _registered
    if _registered:
        return
    for name, filename in _FILES.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
    _registered = True


def string_width(text, font, size):
    register_fonts()
    return pdfmetrics.stringWidth(text, font, size)


def ascent(font, size):
    """Distance above the baseline the font reserves, in points. Noto's
    ascent covers stacked Vietnamese diacritics, so a line placed by it
    stays inside its box with "Ễ" in it."""
    register_fonts()
    return pdfmetrics.getFont(font).face.ascent * size / 1000


def descent(font, size):
    """Distance below the baseline, as a positive number of points."""
    register_fonts()
    return -pdfmetrics.getFont(font).face.descent * size / 1000


def missing_glyphs(text, font=REGULAR):
    """The characters of ``text`` the font has no glyph for (after the same
    normalisation the labels apply)."""
    register_fonts()
    cmap = pdfmetrics.getFont(font).face.charToGlyph
    return [c for c in normalise(text) if ord(c) not in cmap]


_SPACES = re.compile(r'\s+')


def normalise(text):
    """NFC, trimmed, runs of whitespace as one space.

    NFC matters: a name typed or pasted as "e" + combining circumflex + tilde
    is three code points, and the font draws the precomposed "ễ" -- the
    decomposed form would come out as a bare "e" with floating marks.
    """
    return _SPACES.sub(' ', unicodedata.normalize('NFC', text or '')).strip()
