"""Does a presenter name look like a mic position rather than a person?

Engineers routinely name a "presenter" after the mic -- HH13, Q&A 2, A2 OS --
and put a different speaker's photo on it in each session. A photo on such a
presenter must stay with the session, not follow the name everywhere, so new
presenters whose name matches here start with ``is_mic_label`` set. It is only
a starting guess: the flag is editable on the presenter, and nothing re-applies
this pattern to a presenter that already exists.

Tuned against every presenter name on prod (959, October 2026). Matches, with
case ignored and runs of whitespace collapsed:

* a mic or position token as the first word -- HH, H.H, LAV, HS, BP, RF, A1,
  A2, OS, OSM, POD, PODIUM, LECTERN, SPARE, QA, Q&A
  ("HH OSM", "HH B/U 12", "Q&A Mic 2", "Pod Q&A HL", "SPARE HH", "A2")
* one of those mic tokens run straight into a number -- "HH13", "QA1", "Q&A 1",
  "QA - 2", "H.H 10"
* house left/right with a number -- "HL -1", "HR - 2"
* Q&A anywhere -- "Stand Q&A HR"
* an OS / OSM suffix -- "A2 OS", "Stage RF OS", "RF OSM", "Producer OS"
* a role followed only by a number -- "Chair # 2", "Panelist 1", "Talent 3",
  "Drummer 2", "Consultant 1"

Deliberately NOT matched, because on prod they are people: a mic type after a
name ("Franco HH", "Steven Paulson DPA", "Marnie Sprenger SL"), crew with a
role ("ASM - Jane", "SM"), and backups ("VP 58 BU", "Abott BU").
"""

import re

_MIC = r'(?:HH|H\.H|LAV|HS|BP|RF|QA|Q\s*&\s*A)'

MIC_LABEL_RE = re.compile(
    r'^(?:HH|H\.H|LAV|HS|BP|RF|A1|A2|OS|OSM|POD|PODIUM|LECTERN|SPARE|QA|Q\s*&\s*A)\b'
    rf'|^{_MIC}\s*-?\s*\d+'
    r'|^(?:HL|HR)\s*-?\s*\d+'
    r'|(?<!\w)Q\s*&\s*A(?!\w)'
    r'|\b(?:OS|OSM)$'
    r'|^(?:CHAIR|PANELIST|PANEL|TALENT|DRUMMER|CONSULTANT|SPEAKER|PRESENTER|GUEST|MIC)\s*#?\s*\d+$',
    re.IGNORECASE,
)


def looks_like_mic_label(name):
    return bool(MIC_LABEL_RE.search(' '.join((name or '').split())))
