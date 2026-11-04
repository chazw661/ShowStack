"""Comparing a name someone typed with the one on screen.

Used by the typed-name delete confirmations (a Mic Session, all of a Show
Day's sessions) and by Send to Mic Tracker's match-by-name. Case, any kind of
dash (an en dash in "8:00–8:45" cannot be typed on most keyboards) and
whitespace, including around a dash, do not count.
"""

import re

DASHES = re.compile('[‐‑‒–—―−﹘﹣－-]')
SPACE = re.compile(r'\s+')
AROUND_DASH = re.compile(r'\s*-\s*')


def loose(name):
    name = DASHES.sub('-', name or '')
    name = SPACE.sub(' ', name).strip()
    return AROUND_DASH.sub('-', name).casefold()


def same_name(typed, expected):
    return bool(loose(expected)) and loose(typed) == loose(expected)
