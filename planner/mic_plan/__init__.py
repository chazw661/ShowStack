"""Mic Plan: import a run-of-show PDF ("showflow") per ShowDay.

extract   PDF bytes -> table rows, by column name (pdfplumber; no Django)
parser    rows -> times, segments, people, send/catch events, flags (pure)
importer  saves the result and rebuilds a day's people and events (Django)

The parser takes rows rather than a file so a crew-name edit or a merge can
re-run it from the stored rows: the PDF itself is never kept.
"""
