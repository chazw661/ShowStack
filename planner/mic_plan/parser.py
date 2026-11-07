"""Showflow rows -> timeline, people, send/catch events and flags.

Pure functions over the row dicts ``extract`` produces (keys: line, start,
end, duration, description, speaker, bsm, audio, notes). No Django, no pdfplumber:
the importer re-runs ``analyse`` from stored rows whenever crew names or
merges change, and the tests feed it rows directly.

The rules are written up in docs/mic_plan/PARSING_RULES.md.
"""

import difflib
import re
from dataclasses import dataclass, field

# ==========================================================================
# Layout rules
# ==========================================================================
# Everything below was added because a real showflow needed it. Each line
# names the layout: Client A (four files, 14-column, plus an upper-case BSM
# export), Client B (9-column, no send/catch cues), Client C (14-column,
# panels), Client D (27-column, line numbers under an "a" header), Client E
# (14-column, no send/catch cues, "TITLE:" Speaker cells, first names
# after an intro), Client F (14-column under CUE / Event / Presenter, no BSM
# column, "X" for nobody). The fixtures in planner/tests/showflow_fixture.py copy
# each layout with made-up names. Change a rule here, not in the code below.

# -- Speaker separators ----------------------------------------------------
_TOKEN = re.compile(r"[^\s,&()/+;]+|[,&()/+;]")
SEPARATORS = {
    ',', '&', 'and', '/',      # Client A: "Name, Name & Name"
    '+',                       # Client B: "Name + Name"
    ';',                       # Client C: "ORDER; Name, Name"
}
PUNCT = {'(', ')', '-', '–'}   # Client A: "Name - Role"

# -- Name stop-words: capitalised words that are never part of a name ------
NOT_NAMES = (
    # Client A: cue and screen words around names; "Pickle" is a clicker
    {'pickle', 'pickles', 'both', 'everyone', 'all', 'presenters', 'presenter', 'titles', 'gfx',
     'video', 'ppt', 'vo', 'the', 'team'}
    # Client A (BSM export): VOG/TITLE rows and Enter/Exit stage notes
    | {'title', 'vog', 'enter', 'exit', 'partner'}
    # Client A (BSM export): chatter after a name in a cue ("Sends Kim Needs Clicker")
    | {'needs', 'need', 'grab', 'get', 'gets', 'has', 'have', 'clicker', 'mic', 'exits',
       'enters', 'walks', 'wraps', 'send', 'sends', 'catch', 'catches', 'on', 'with', 'to',
       'people', 'speaker', 'speakers', 'winners'}
    # Client B: "DJ Audio Throughout" in the Speaker column
    | {'dj', 'audio', 'music', 'throughout'}
    # Client C: "(Name Stays)", "ORDER: ...", "TBD with ..."
    | {'stays', 'order', 'tbd', 'tba'}
    # Client D: "Send Person 1", "Name (Moderator)"
    | {'person', 'moderator'}
)
# Client B: lower-case name parts that still belong to a name ("Rory vandeberg")
NAME_PARTICLES = ('mac', 'mc', 'van', 'von', 'de', 'da', 'di', 'du', 'del', 'la', 'le', 'st')
# Client B: Speaker-cell text that is not a person and needs no mic: dropped, not flagged
_NOT_A_PERSON = re.compile(r'(?i)\b(?:dj|audio|music|playback|walk-?in|tbd|tba|n/?a)\b')

# -- Speaker-cell strips -------------------------------------------------------
_STAGE_NOTES = re.compile(
    r'\{[^}]*\}'                       # Client A (BSM export): "{CLICKER 1}"
    r'|\([^)]{0,40}\)'                 # Client A "(SL)", Client C "(MC)", Client A "(F)"
    r'|\b(?:Enter|Exit)\s*:\s*\S*'      # Client A (BSM export): "Enter: BSL Exit: BSR"
    r'|\b(?:OS)?(?:BS|US|DS)[LRC]\b'    # Client A (BSM export): bare stage codes
    r'|\b(?:SL|SR|CS|N/A)\b')           # Client A: bare stage positions
_GRAPHICS = re.compile(r'\b(?:GFX|TITLES):.*$')                   # Client A: graphics cues
# Client A "Titles (Stacked):"; Client E "TITLE:", "2-UP TITLE:", "5-UP TITLE:". A row
# that starts this way introduces the people it names.
_TITLES_PREFIX = re.compile(r'(?i)^(?:\d+\s*-\s*up\s+)?titles?\s*(?:\([^)]*\))?\s*:\s*')
# Client E: "Dr. Name Surname". The title stays part of the name; a title and a
# surname alone ("Dr. Kim") never make a person, they refer back to one.
HONORIFICS = {'dr', 'mr', 'mrs', 'ms', 'mx', 'prof'}

# -- Welcome lines and job titles --------------------------------------------
_WELCOME = re.compile(r'(?i)\bplease\s+welcome\b(.*)$')            # Client A: "please welcome ..."
# Client E: a description bringing people on ("introduces the 3 presenters.
# Name, Name"). Names after it that no nearby Speaker cell carries are flagged.
_BRINGS_ON = re.compile(r'(?i)\b(?:welcom(?:e|es|ing)|joins?|introduc(?:e|es|ing)'
                        r'|brings?\s+(?:up|on)|invites?)\b')
# Client A (BSM export) lists the Speaker two rows before the VOG welcome, so
# the Speaker cells checked run this many rows either side.
DESC_NEARBY_ROWS = 3
# Words that make a capitalised item a company, team or talk, not a person:
# Client D "Title, Company, Name" welcomes, Client C a company and product
# name, Client E game-show and talk titles, Client A "Product Management".
ORG_WORDS = (
    {'consulting', 'intelligence', 'threat', 'strategy', 'security', 'practice', 'communications'}
    | {'health', 'intro'}
    | {'feud', 'keynote', 'reporting', 'powered', 'game', 'session', 'our', 'your'}
    | {'product', 'management', 'inc', 'llc', 'group', 'summit'}
)
# Client A "Name, President & CEO"; Client D "Title, Company, Name" welcomes
TITLE_WORDS = {
    'president', 'ceo', 'cfo', 'coo', 'cto', 'cmo', 'cio', 'chair', 'chairman', 'chairwoman',
    'chief', 'officer', 'board', 'vice', 'vp', 'evp', 'svp', 'director', 'manager', 'founder',
    'executive', 'senior', 'head', 'md', 'gm',
}
TITLE_CONNECTORS = {'&', 'and', 'of', '/', 'the'}                  # Client A: "President & CEO"

# -- Exits and re-entries (cue-free parts) -------------------------------------
# Client E: "Max Exits", "Ola exit after ...", "Gil exits when ...",
# "Max and Dr. Reyes Exit", "both exit". Client C: "Panel Exits (Kit Stays)".
# Client F: "Gil departs", "Bo walks off stage".
# A verb followed by ":" is a stage note ("Exit: BSR"), not an exit.
_EXIT = re.compile(r'(?i)\b(?:exit(?:s|ing)?|depart(?:s|ing)?|leaves?|leaving|walks?\s+off|goe?s?\s+off\s*stage'
                   r'|off\s*stage)\b(?!\s*:)')
_REENTER = re.compile(r'(?i)\b(?:re-?\s?enter(?:s|ing)?|returns?)\b(?!\s*:)')
_STAYS = re.compile(r'(?i)\b(?:stays?|remains?)\b')
# Group words before an exit: everyone on stage, except hosts and anyone
# named as staying ("Presenters Exit", "Panel Exits (Kit Stays)") ...
GROUP_ALL = {'all', 'everyone', 'everybody', 'panel', 'panelist', 'panelists', 'panellists',
             'presenter', 'presenters', 'speakers', 'guests'}
# ... or the two people most recently brought on ("Bo thanks Zed; both exit").
GROUP_BOTH = {'both'}

# -- Names in a "not listed" description, for "Add people from this line" ------
# Client E "Name, Name, MD, Name": a suffix after a comma belongs to the name before it.
NAME_SUFFIXES = {'md', 'do', 'phd', 'rn', 'np', 'pa-c', 'pa', 'dnp', 'dds', 'mba', 'jr', 'sr',
                 'ii', 'iii', 'iv', 'esq', 'cpa', 'facs', 'faad'}

# -- Send / catch cues ---------------------------------------------------------
_VERB = re.compile(r'(?i)^(?:sends?|sending|catch(?:es)?|catching)$')  # Client A
CUE_FILLERS = ('to', 'will')        # Client A: "Lee to send ...", "Sam will ..."
# Client D: a BSM cell that opens with the verb ("Send Alex") is a cue with no crew name
CUE_VERB_OPENS_CELL = True

# -- Mic hints -------------------------------------------------------------------
_HH = re.compile(r'(?i)\bHH\b|\bhand-?helds?\b')    # Client B "handheld(s)", Client B "Need HH"
_BACKUP = re.compile(r'(?i)\bback-?up\s+mic\b')     # Client A "Sam with Name Backup mic"

# -- Mic numbers in the showflow ---------------------------------------------------
# Client F, Audio column: an "A2: Mic Presenters" list ("Lav #1: Name Lav #5 - Name")
# and number-only cells ("Lav 2", "Lav 3,6"). The word gives the kind; a list item
# has one number, then ":" or a dash, then a name. "Lav 1-3" is a range.
MIC_KINDS = {'lav': 'Lav', 'lavalier': 'Lav', 'headset': 'Headset', 'hh': 'HH', 'handheld': 'HH',
             'mic': 'Mic', 'rf': 'RF'}
MIC_POOLS = {'Lav': 'body', 'Headset': 'body', 'HH': 'HH'}        # 'Mic', 'RF': no type said
_CALLOUT = re.compile(r'(?i)(?<![\w-])(lavalier|lav|headset|hand-?held|hh|mic|rf)s?\s*#?\s*'
                      r'(\d{1,3}(?:\s*(?:,|&|and|-|\u2013|/)\s*#?\s*\d{1,3})*)(?![\d.:]*\d)')
_NUMBERS = re.compile(r'\d{1,3}')
_RANGE = re.compile(r'^(\d{1,3})\s*[-\u2013]\s*(\d{1,3})$')
_NAME_FOLLOWS = re.compile(r'\s*[:\-\u2013\u2014]\s*')
# A wired mic has a number too: not a pack.
_WIRED = re.compile(r'(?i)\b(?:podium|lectern|stand|aisle|table|floor|wired|choir|vog|boom)\s*$')
MIC_RANGE_MAX = 20
# How close a list's spelling must be to a name in the Speaker column.
MIC_NAME_CUTOFF = 0.85

# -- Flags -----------------------------------------------------------------------
# Client B (no cues), Client C (one stray cue in 171 rows): "No cue" means
# nothing when cues cover fewer than this share of the people listed.
NO_CUE_MIN_COVERAGE = 0.5

# -- Segment headings ------------------------------------------------------------
# Client E: the row carrying a segment's times is often a VOG line or "END
# RECORDS"; the segment's name is the first row that is none of these.
_NOT_A_HEADING = re.compile(r'(?i)^\s*(?:vog\b|\[|roll\s+records|end\s+records|stage\s+set'
                            r'|.*\bwalk-?\s?in\b)')
_BREAK = re.compile(r'(?i)^\s*(?:lunch(?:\s+break)?|break)\b')     # Client E "BREAK", "LUNCH BREAK"
# A segment named like a break is one unless its heading row names someone
# to speak: Client A "Networking Break", Client B "BREAK" with "DJ Audio
# Throughout" as its Speaker; not Client A "Back from Break" or "... & Lunch
# Transition", where presenters walk on.
_BREAK_NAME = re.compile(r'(?i)\b(?:break|lunch|networking|intermission|recess|coffee|refresh'
                         r'|reception|transition|meal)')
# Nobody named and no Speaker text for this long is a break too (Client A Doors).
BREAK_QUIET_MIN = 15

# --------------------------------------------------------------------------
# Times
# --------------------------------------------------------------------------

_CLOCK = re.compile(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp])?\.?\s*[Mm]?\.?$')
_HMS = re.compile(r'^\d{1,2}:\d{2}:\d{2}$')
_HM = re.compile(r'^\d{1,2}:\d{2}$')

# A clock time with no AM/PM is read as whichever of the two lies closest
# after the previous one, and dropped if that is more than this far ahead.
AMBIGUOUS_WINDOW_MIN = 120
# A send's time is the start of the next segment only if that segment begins
# within this many rows; further away, the cue is mid-segment ("Host
# Enters") and the row's own interpolated time is nearer the truth.
SEND_LOOKAHEAD_ROWS = 4
# A speaker counts as covered by a send/catch window that opens up to this
# many minutes after their segment starts.
COVER_SLACK_MIN = 6


def parse_clock(text):
    """(hour, minute, 'A'|'P'|None) for a clock time, None otherwise.

    The Start column also carries video run times: "0:05:13" (hour 0) and
    timecode "00:04:08:00" (four fields) are not clock times.
    """
    m = _CLOCK.match((text or '').strip())
    if not m:
        return None
    hour, minute = int(m[1]), int(m[2])
    if hour == 0 or hour > 23 or minute > 59:
        return None
    return hour, minute, (m[4] or '').upper() or None


def _minutes(hour, minute, ampm):
    if ampm:
        hour = hour % 12 + (12 if ampm == 'P' else 0)
    return hour * 60 + minute


def resolve_clock(parsed, after):
    """Minutes from midnight for a parse_clock() result, given the previous
    anchor ``after`` (or None). None if the time cannot be placed."""
    hour, minute, ampm = parsed
    if ampm or hour > 12:
        t = _minutes(hour, minute, ampm)
        return t if after is None or t >= after else None
    readings = [_minutes(hour, minute, 'A'), _minutes(hour, minute, 'P')]
    if after is None:
        # First anchor of the file: a show day runs roughly 6a to 6p.
        return readings[0] if 6 <= hour <= 11 else readings[1]
    ahead = [t for t in readings if after <= t <= after + AMBIGUOUS_WINDOW_MIN]
    return min(ahead) if ahead else None


@dataclass
class RowTime:
    minute: float = None      # interpolated where the row has no clock time
    exact: bool = False       # the row's own Start time
    is_segment: bool = False
    t0: float = None
    t1: float = None


def build_times(rows):
    """[RowTime] per row, plus warnings."""
    out = [RowTime() for _ in rows]
    warnings = []
    anchors = {}
    guessed = set()           # anchors read without AM/PM
    last = None
    for i, row in enumerate(rows):
        parsed = parse_clock(row['start'])
        if not parsed:
            continue
        explicit = bool(parsed[2]) or parsed[0] > 12
        if explicit and last is not None:
            # "10:45:00" read as 10:45a, then "10:41 AM" on the next segment:
            # the explicit time wins and the guesses past it are dropped.
            t = _minutes(*parsed)
            for k in sorted(anchors, reverse=True):
                if k not in guessed or anchors[k] <= t:
                    break
                del anchors[k]
            last = max(anchors.values()) if anchors else None
        t = resolve_clock(parsed, last)
        if t is None and explicit and len(anchors) >= 2:
            # One stray time ahead of the rest ("9:33 AM" on a VOG line, then
            # the 9:00 segment): if this time fits after the anchor before
            # it, the stray one is what is wrong. Drop that instead.
            prev, stray = sorted(anchors)[-2:]
            t = _minutes(*parsed)
            if anchors[prev] <= t < anchors[stray]:
                warnings.append(('time_backwards', stray, 'Line {}: start time {} is later than '
                                 'the times after it; ignored.'.format(
                                     rows[stray]['line'] or '?', rows[stray]['start'])))
                del anchors[stray]
                guessed.discard(stray)
                last = anchors[prev]
            else:
                t = None
        if t is None:
            if parsed[2]:
                warnings.append(('time_backwards', i, 'Line {}: start time {} is earlier than '
                                 'the line before it; ignored.'.format(row['line'] or '?', row['start'])))
            continue
        anchors[i] = last = t
        if not explicit:
            guessed.add(i)
    if not anchors:
        warnings.append(('no_times', None, 'No clock times found in the Start column.'))
        return out, warnings
    keys = sorted(anchors)
    for i in range(len(rows)):
        if i in anchors:
            out[i].minute, out[i].exact = anchors[i], True
            continue
        before = [k for k in keys if k < i]
        after = [k for k in keys if k > i]
        if not before:
            out[i].minute = anchors[after[0]]
        elif not after:
            out[i].minute = anchors[before[-1]]
        else:
            a, b = before[-1], after[0]
            out[i].minute = anchors[a] + (anchors[b] - anchors[a]) * (i - a) / (b - a)

    segments = find_segments(rows, anchors)
    for n, i in enumerate(segments):
        rt = out[i]
        rt.is_segment, rt.t0 = True, anchors[i]
        end = parse_clock(rows[i]['end'])
        t1 = resolve_clock(end, rt.t0) if end else None
        if t1 is None or t1 - rt.t0 > 12 * 60:
            if n + 1 < len(segments):
                t1 = anchors[segments[n + 1]]
            else:
                t1 = rt.t0 + (_duration_min(rows[i]['duration']) or 0)
        rt.t1 = max(t1, rt.t0)
    return out, warnings


def find_segments(rows, anchors):
    """Rows that open a segment: a clock Start and a clock End, plus a
    Duration in the form the file uses for segments.

    Files differ. Where segments carry "0:30:00", a "0:24" beside a Start and
    End is a slide count inside one, not a segment; where they carry "0:30",
    that is the form; and some leave Duration blank throughout.
    """
    timed = [i for i in sorted(anchors) if parse_clock(rows[i]['end'])]
    for form in (_HMS, _HM):
        found = [i for i in timed if form.match(rows[i]['duration'].strip())]
        if found:
            return found
    return timed


def hm(t):
    """'8:46a' for a minute-of-day value."""
    if t is None:
        return ''
    t = round(t)
    h, m = divmod(t, 60)
    return '{}:{:02d}{}'.format((h - 1) % 12 + 1, m, 'a' if h % 24 < 12 else 'p')


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------

def name_key(name):
    key = re.sub(r'\s+', ' ', name).strip(' .,;:').lower()
    # "Dr Name" and "Dr. Name" are one person.
    return re.sub(r'^({})\.?\s'.format('|'.join(sorted(HONORIFICS))), r'\1. ', key)


def _honorific(tok):
    return _clean_token(tok).lower() in HONORIFICS


def _bare(name):
    """The name without a leading title: "Dr. Ann Lee" -> "Ann Lee"."""
    words = name.split()
    return ' '.join(words[1:]) if len(words) > 1 and _honorific(words[0]) else name


def _tokens(text):
    return _TOKEN.findall(text or '')


def _clean_token(tok):
    return tok.strip('.:;!?"“”')


def _is_name_word(tok):
    w = _clean_token(tok)
    return (bool(w) and w[0].isupper() and not any(ch.isdigit() for ch in w)
            and w.lower() not in NOT_NAMES)


def _is_name_part(tok):
    """A later word of a name: capitalised, or a particle ("vandeberg")."""
    w = _clean_token(tok)
    return _is_name_word(w) or (w.isalpha() and w.lower().startswith(NAME_PARTICLES)
                                and w.lower() not in NOT_NAMES)


def _first_name(name):
    words = name.split()
    if len(words) > 1 and _honorific(words[0]):
        words = words[1:]
        if len(words) == 1:
            return None   # "Dr. Kim" has no first name
    if len(words) == 1:
        return words[0].split('-')[0] if '-' in words[0] else None
    return words[0]


def _surname(name):
    words = _bare(name).split()
    return words[-1] if len(words) > 1 else None


AMBIGUOUS = object()   # Refs: more than one person fits a short name


class Refs:
    """Who a short reference means, walking the rows in order (Client E).

    "Rob" or "Dr. Kim" in a Speaker cell is the person most recently
    introduced in full with that first name or surname: by a TITLE row, a
    welcome line or an earlier full-name Speaker cell. Not any roster match:
    a later person with the same first name must not take the earlier one's
    lines. ``intro`` keeps the first row that introduced each person.
    """

    def __init__(self, roster):
        self.roster = roster
        self.row = None
        self.last = {}          # ('first'|'surname', lower) -> (row, display name)
        self.on_row = {}        # same key -> names introduced on that row
        self.intro = {}         # display name -> first row introducing them
        self.ambiguous = []     # (row, word, [candidates])

    def saw(self, name):
        """``name`` was just named in full on the current row."""
        self.intro.setdefault(name, self.row)
        for kind, word in (('first', _first_name(name)), ('surname', _surname(name))):
            if not word:
                continue
            key = (kind, word.lower())
            if self.last.get(key, (None,))[0] != self.row:
                self.on_row[key] = set()
            self.last[key] = (self.row, name)
            self.on_row[key].add(name)

    def lookup(self, kind, word):
        """The display name ``word`` refers to, AMBIGUOUS, or None (no idea:
        the caller falls back to the roster)."""
        key = (kind, word.lower())
        if key in self.last:
            if len(self.on_row[key]) > 1:
                return AMBIGUOUS
            return self.last[key][1]
        owners = self.candidates(kind, word)
        return AMBIGUOUS if len(owners) > 1 else owners[0] if owners else None

    def candidates(self, kind, word):
        pick = _first_name if kind == 'first' else _surname
        return sorted(n for n in self.roster.names if (pick(n) or '').lower() == word.lower())

    def short_at(self, toks, i):
        """(display name | AMBIGUOUS | None, tokens used) for a first name or a
        title + surname standing alone at toks[i]."""
        def boundary(j):
            return j >= len(toks) or toks[j] in SEPARATORS or toks[j] in PUNCT \
                or not _is_name_part(toks[j])
        word = _clean_token(toks[i])
        if not _is_name_word(word) or name_key(word) in self.roster.manual:
            return None, 0
        if (_honorific(word) and i + 1 < len(toks) and _is_name_word(toks[i + 1])
                and boundary(i + 2)):
            surname = _clean_token(toks[i + 1])
            found = self.lookup('surname', surname)
            if found is AMBIGUOUS:
                self.ambiguous.append((self.row, surname, self.candidates('surname', surname)))
            # Unknown: no person is made from it; the cell's leftover flags it.
            return (found, 2) if found else (None, 0)
        if _honorific(word) or not boundary(i + 1):
            return None, 0
        found = self.lookup('first', word)
        if found is AMBIGUOUS:
            self.ambiguous.append((self.row, word, self.candidates('first', word)))
        return (found, 1) if found else (None, 0)


class Roster:
    """The people of a part, and every spelling that refers to each.

    ``canon`` maps a lower-cased token sequence to a display name. Full
    names and the user's merged aliases always count; a first name counts
    only while it is unique among the people found.
    """

    def __init__(self, known=()):
        self.names = {}          # display name -> set(lower aliases)
        self.manual = {}         # lower alias -> display name (from merges)
        self.bsm_only = set()
        for display, aliases in known:
            self.names.setdefault(display, set())
            self.manual[name_key(display)] = display
            for alias in aliases:
                self.manual[name_key(alias)] = display
        self.found = set()       # display names this part mentions
        self._index = None

    def resolve(self, raw):
        """Display name for a spelling, adding the person if new."""
        key = name_key(raw)
        if key in self.manual:
            return self.manual[key]
        idx = self.index()
        if key in idx:
            return idx[key]
        display = re.sub(r'\s+', ' ', raw).strip(' .,;:')
        if display.isupper() and len(display) > 3:
            display = display.title()  # "ROBIN COLE" in a VOG line
        words = display.split()
        if len(words) > 1 and _honorific(words[0]):
            words[0] = _clean_token(words[0]).capitalize() + '.'   # "Dr Ann Lee" -> "Dr. Ann Lee"
            display = ' '.join(words)
        self.names.setdefault(display, set())
        self._index = None
        return display

    def add(self, raw):
        display = self.resolve(raw)
        self.found.add(display)
        return display

    def index(self):
        if self._index is None:
            idx = {}
            firsts = {}
            for display in self.names:
                idx[name_key(display)] = display
                if _bare(display) != display and len(_bare(display).split()) > 1:
                    idx.setdefault(name_key(_bare(display)), display)   # "Ann Lee" -> "Dr. Ann Lee"
                first = _first_name(display)
                if first:
                    firsts.setdefault(first.lower(), set()).add(display)
            for first, owners in firsts.items():
                if len(owners) == 1 and first not in idx:
                    idx[first] = next(iter(owners))
            idx.update(self.manual)
            self._index = idx
            self.longest = max((len(k.split()) for k in idx), default=1)
        return self._index

    def match_at(self, toks, i):
        """(display name, tokens used) for the longest spelling at toks[i]."""
        idx = self.index()
        for n in range(min(self.longest, len(toks) - i), 0, -1):
            window = toks[i:i + n]
            if any(t in SEPARATORS or t in PUNCT for t in window):
                continue  # "Alex ," must not read as "Alex" and swallow the comma
            words = [_clean_token(t) for t in window]
            if not all(words) or not words[0][0].isupper():
                continue
            key = name_key(' '.join(words))
            if key in idx:
                return idx[key], n
            if n > 2 and _honorific(words[0]):
                key = name_key(' '.join(words[1:]))     # "Dr. Ann Lee" for a known "Ann Lee"
                if key in idx and len(key.split()) > 1:
                    return idx[key], n
        return None, 0


def _welcome_names(text, speaker_text=None):
    """Names in a "please welcome" line. Titles and companies sit in the
    same comma list ("welcome to the stage, Vice President, Acme Consulting,
    Alex Host"), so with ``speaker_text`` (every Speaker cell, lower-cased)
    a name only counts if a Speaker or Titles cell carries it too."""
    m = _WELCOME.search(re.sub(r'\([^)]*\)', ' ', text or ''))
    if not m:
        return []
    rest = m[1]
    for ellipsis in ('…', '...'):
        if ellipsis in rest:
            rest = rest.rsplit(ellipsis, 1)[1]
    rest = re.sub(r'(?i)^\W*(?:to\s+the\s+stage|back)\b', '', rest)
    names = []
    for part in re.split(r',|&|\band\b', rest):
        words = [w for w in part.strip(' .…:;!').split() if w]
        while len(words) > 2 and words[0].lower().strip('.') in TITLE_WORDS:
            words = words[1:]
        if not words or len(words) > 4 or not all(_is_name_word(w) for w in words):
            continue
        if len(words) == 1 and '-' not in words[0]:
            continue  # a lone first name is too weak to add someone
        name = ' '.join(words)
        if speaker_text is not None and name.lower() not in speaker_text:
            continue
        names.append(name)
    return names


def _speaker_text(text):
    text = _GRAPHICS.sub('', text or '')
    text = _TITLES_PREFIX.sub('', text.strip())
    return _STAGE_NOTES.sub(' ', text)


def split_cell(text, roster, discover, refs=None):
    """Names in a Speaker/Titles cell, and the text no name accounts for.

    Speaker cells run names together without separators ("Dana Able Chris
    Baker"), so known spellings are matched first. With ``discover``, what is
    left becomes a name if it is two or three words standing alone between
    separators ("Tess St. Clair", "Rory vandeberg"), or a run of
    capitalised pairs. Anything else is left over for the reviewer, unless it
    is plainly not a person ("DJ Audio Throughout").

    With ``refs`` (the final pass, rows in order), a first name or a title +
    surname standing alone is whoever ``refs`` says was introduced last, and
    every full name matched counts as an introduction.
    """
    toks = _tokens(_speaker_text(text))
    names, leftovers, chunk = [], [], []
    bounded = [True]   # the chunk began at the cell's start or a separator
    # The chunk follows "Name -": an affiliation ("Alex Host - Acme AI Robin
    # Cole - Initech"), possibly with the next person's name at its end.
    after_dash = [False]
    named_last = [False]

    def close_chunk(bounded_end=True):
        if not chunk:
            bounded[0] = bounded_end
            return
        words = [_clean_token(t) for t in chunk]
        alone = bounded[0] and bounded_end
        digits = any(ch.isdigit() for ch in ' '.join(words))
        dash, after_dash[0] = after_dash[0], False
        named_last[0] = True
        if dash and not digits:
            if (discover and bounded_end and len(words) >= 3 and _is_name_word(words[-2])
                    and _is_name_part(words[-1])):
                names.append(roster.add(' '.join(words[-2:])))
            elif len(words) > 4:
                leftovers.append(' '.join(chunk).strip(' -–'))
                named_last[0] = False
        elif (discover and len(words) == 3 and _honorific(words[0])
                and all(_is_name_part(w) for w in words[1:])):
            names.append(roster.add(' '.join(words)))   # "Dr. Sol Tate" mid-cell
        elif (discover and alone and len(words) in (2, 3) and _is_name_word(words[0])
                and all(_is_name_part(w) for w in words[1:])
                and not (len(words) == 2 and _honorific(words[0]))):   # "Dr. Kim" is no one new
            names.append(roster.add(' '.join(words)))
        elif (discover and len(words) % 2 == 0 and all(_is_name_word(w) for w in words)
                and not any(_honorific(w) for w in words)):
            for j in range(0, len(words), 2):
                names.append(roster.add(' '.join(words[j:j + 2])))
        else:
            named_last[0] = False
            text_ = ' '.join(chunk).strip(' -–')
            if text_ and not _NOT_A_PERSON.search(text_):
                leftovers.append(text_)
        chunk.clear()
        bounded[0] = bounded_end

    i = 0
    while i < len(toks):
        if refs is not None and not chunk:
            ref, used = refs.short_at(toks, i)
            if used:
                if ref is not AMBIGUOUS:   # an ambiguous one is flagged by the caller
                    names.append(ref)
                    roster.found.add(ref)
                i += used
                bounded[0] = False
                named_last[0] = True
                continue
        name, used = roster.match_at(toks, i)
        if name and used == 1 and chunk:
            name = None  # "Tess St. Clair": a first name mid-name is not that person
        if name:
            close_chunk(bounded_end=False)
            names.append(name)
            roster.found.add(name)
            if refs is not None and used > 1:
                refs.saw(name)
            i += used
            # Client F "Tom K.": a first name and the initial of their surname.
            if used == 1 and i < len(toks) and re.fullmatch(r'[A-Z]\.?', toks[i]) \
                    and (_surname(name) or '').startswith(toks[i][0]):
                i += 1
            # "Name, President & CEO" / "Name - Patient": a title, not text to flag.
            if i < len(toks) and toks[i] in (',', '-', '–'):
                j = i + 1
                if (j < len(toks) and _is_name_word(toks[j]) and not roster.match_at(toks, j)[0]
                        and (toks[i] != ',' or _clean_token(toks[j]).lower() in TITLE_WORDS)):
                    j += 1
                    while j < len(toks):
                        low = _clean_token(toks[j]).lower()
                        if low in TITLE_WORDS:
                            j += 1
                        elif low in TITLE_CONNECTORS and j + 1 < len(toks):
                            j += 2
                        else:
                            break
                    after_dash[0] = toks[i] in ('-', '–')
                    i = j
            bounded[0] = False
            named_last[0] = True
            continue
        if toks[i] in SEPARATORS or toks[i] in ('-', '–', '(', ')'):
            close_chunk()
            if toks[i] in ('-', '–') and named_last[0]:
                after_dash[0] = True
        else:
            if chunk and _honorific(toks[i]):
                close_chunk()   # "Ann Lee Dr. Bo Chen": the title starts the next name
            chunk.append(toks[i])
            if (len(chunk) == 3 and _honorific(chunk[0]) and i + 1 < len(toks)
                    and _is_name_word(toks[i + 1])):
                close_chunk()   # "Dr. Bo Chen Ann Lee": title + two words is one name
        i += 1
    close_chunk()
    return list(dict.fromkeys(names)), leftovers


# --------------------------------------------------------------------------
# Send / catch
# --------------------------------------------------------------------------



def _bsm_stream(rows):
    """[(row index, token)] over every BSM cell in order: one stream, so a cue
    that spills into the next row or onto the next page reads as one."""
    return [(i, tok) for i, row in enumerate(rows) for tok in _tokens(row['bsm'])]


def _opens_cell(stream, k):
    """True if token k is the first word of its BSM cell."""
    return k == 0 or stream[k - 1][0] != stream[k][0]


def detect_crew(rows, roster):
    """Capitalised words right before a send/catch verb that are not people:
    the crew names to suggest on a first import."""
    stream = _bsm_stream(rows)
    found = []
    for k, (_, tok) in enumerate(stream):
        if not _VERB.match(tok) or _opens_cell(stream, k):
            continue
        j = k - 1
        if j >= 0 and stream[j][1].lower() in CUE_FILLERS:
            j -= 1
        if j >= 0:
            word = _clean_token(stream[j][1])
            if _is_name_word(word) and not roster.match_at([word], 0)[0]:
                found.append(word)
    return list(dict.fromkeys(found))


def find_events(rows, crew, roster):
    """(events, unknown-crew flags). Each event: (kind, display name, row).

    A cue is "<crew> (to) send(s)/catch(es) <names>", names joined by commas,
    "and" or "&"; or, with no crew, a cell that opens with the verb ("Send
    Alex"). The list ends at the first word that is neither a name nor
    a separator, so "...Robin and Morgan Robin and Dana have pickles" stops at
    Morgan. A capitalised name nobody else mentions is kept as a BSM-only
    person, to be merged on the review page.
    """
    crew_keys = {c.strip().lower() for c in crew if c.strip()}
    stream = _bsm_stream(rows)
    toks = [t for _, t in stream]
    events, flags = [], []
    k = 0
    while k < len(toks):
        if not _VERB.match(toks[k]):
            k += 1
            continue
        j = k - 1
        if j >= 0 and toks[j].lower() in CUE_FILLERS:
            j -= 1
        who = _clean_token(toks[j]).lower() if j >= 0 else ''
        row = stream[k][0]
        crewless = (CUE_VERB_OPENS_CELL and who not in crew_keys and _opens_cell(stream, k)
                    and toks[k][:1].isupper())
        if who not in crew_keys and not crewless:
            if (who and _clean_token(toks[j])[:1].isupper()
                    and not roster.match_at([_clean_token(toks[j])], 0)[0]):
                flags.append(('unknown_crew', row, 'Line {}: "{} {}" was not read as a cue: {} is '
                              'not in the crew names.'.format(
                                  rows[row]['line'] or '?', _clean_token(toks[j]), toks[k],
                                  _clean_token(toks[j]))))
            k += 1
            continue
        kind = 'send' if toks[k].lower().startswith('send') else 'catch'
        got = []
        p = k + 1
        expect = True
        while p < len(toks):
            if expect and got and toks[p].lower() in SEPARATORS:
                p += 1  # ", and Robin"
                continue
            if expect:
                name, used = roster.match_at(toks, p)
                if name:
                    got.append(name)
                    p += used
                    expect = False
                    continue
                run = []
                while (p + len(run) < len(toks) and len(run) < 3
                       and _is_name_word(toks[p + len(run)])
                       and _clean_token(toks[p + len(run)]).lower() not in crew_keys
                       and not _VERB.match(toks[p + len(run)])):
                    run.append(_clean_token(toks[p + len(run)]))
                if not run:
                    break
                raw = ' '.join(run)
                new = name_key(raw) not in roster.index()
                name = roster.add(raw)
                if new:
                    roster.bsm_only.add(name)
                got.append(name)
                p += len(run)
                expect = False
            elif toks[p].lower() in SEPARATORS:
                p += 1
                expect = True
            else:
                break
        for name in dict.fromkeys(got):
            events.append((kind, name, row))
            roster.found.add(name)
        k = p if got else k + 1
    return events, flags


# --------------------------------------------------------------------------
# The whole part
# --------------------------------------------------------------------------

@dataclass
class Event:
    kind: str
    name: str
    row: int
    minute: float = None


@dataclass
class Analysis:
    times: list
    people: dict                      # display name -> {'rows': [...], 'mic_hint': str, 'bsm_only': bool}
    events: list
    flags: list                       # (kind, row index or None, text, name or None)
    crew: list
    segments: list = field(default_factory=list)
    span: tuple = (None, None)


def _next_segment(times, row):
    for i in range(row + 1, len(times)):
        if times[i].is_segment:
            return i
    return None


def _duration_min(text):
    """Minutes in "H:MM:SS" or "H:MM", else None."""
    m = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?$', (text or '').strip())
    return int(m[1]) * 60 + int(m[2]) + int(m[3] or 0) / 60 if m else None


def event_minute(times, kind, row, rows=None, sent_here=False):
    """When a cue happens. A row with its own clock time wins; otherwise a
    send is the start of the segment that follows (if it follows closely),
    and a catch the start of the next segment. Sent and caught on the same
    row ("Sam sends Pat Lee catches Pat") is a walk-on: the catch is
    the send plus the row's Duration, or 5 minutes."""
    if sent_here:
        send = event_minute(times, 'send', row)
        dur = _duration_min(rows[row]['duration']) if rows else None
        return send + (dur if dur else 5) if send is not None else None
    if times[row].exact:
        return times[row].minute
    nxt = _next_segment(times, row)
    if nxt is not None and (kind == 'catch' or nxt - row <= SEND_LOOKAHEAD_ROWS):
        return times[nxt].t0
    if kind == 'catch' and nxt is None:
        # Caught after the last segment starts: off when that segment ends.
        last = next((times[i] for i in range(row, -1, -1) if times[i].is_segment), None)
        if last is not None:
            return last.t1
    return times[row].minute


def analyse(rows, crew=None, known=()):
    """Everything PR 1 shows for one part. ``crew`` None = detect it;
    ``known`` = [(display name, [aliases])] for the day's people."""
    times, time_warnings = build_times(rows)
    roster = Roster(known)
    mentions = {}

    def mention(name, i):
        mentions.setdefault(name, set()).add(i)

    # Discover: welcome lines, then Titles cells, then Speaker cells. Titles
    # before Speaker so the run-together Speaker cells split on real names.
    speaker_text = ' '.join(re.sub(r'\s+', ' ', row['speaker']) for row in rows).lower()
    for i, row in enumerate(rows):
        for raw in _welcome_names(row['description'], speaker_text):
            mention(roster.add(raw), i)
    titled = [i for i, row in enumerate(rows) if _TITLES_PREFIX.match(row['speaker'] or '')]
    for i in titled + [i for i in range(len(rows)) if i not in titled]:
        if rows[i]['speaker']:
            split_cell(rows[i]['speaker'], roster, discover=True)

    if crew is None:
        crew = detect_crew(rows, roster)
    events_raw, flags = find_events(rows, crew, roster)
    flags = [(kind, row, text, None) for kind, row, text in flags]
    flags += [(kind, row, text, None) for kind, row, text in time_warnings]

    # Final pass with the whole roster known, rows in order: who each cell
    # names (a short name is whoever was introduced last), and what is left.
    speakers = {}
    exits, enters, unknown_exits = {}, {}, []
    refs = Refs(roster)
    for i, row in enumerate(rows):
        refs.row = i
        for raw in _welcome_names(row['description'], speaker_text):
            refs.saw(roster.resolve(raw))
        if row['speaker']:
            names, leftovers = split_cell(row['speaker'], roster, discover=False, refs=refs)
        else:
            names, leftovers = [], []
        out, back, unknown = exits_and_entries(row['description'], roster, refs)
        for name in out:
            exits.setdefault(name, set()).add(i)
        for name in back:
            enters.setdefault(name, set()).add(i)
        for word in unknown:
            unknown_exits.append((i, word))
        if not row['speaker']:
            continue
        speakers[i] = names
        for name in names:
            mention(name, i)
        if leftovers:
            flags.append(('unmatched_speaker', i, 'Line {}: {} in the Speaker column is not a '
                          'person ShowStack recognised. Decide its mics (a group may need '
                          'handhelds).'.format(row['line'] or '?',
                                               ', '.join('"{}"'.format(t) for t in leftovers)), None))
    for i, word, owners in refs.ambiguous:
        flags.append(('which_first', i, 'Line {}: which {}? {} are {} on this day and nothing '
                      'just before says which. Merge or check the showflow.'.format(
                          rows[i]['line'] or '?', word, ' and '.join(owners) or 'Several people',
                          'both' if len(owners) == 2 else 'all'), None))
    flags += _description_flags(rows, roster, speakers)
    mics, mic_flags = _mic_numbers(rows, roster, speakers)
    flags += mic_flags

    sends = {(name, row) for kind, name, row in events_raw if kind == 'send'}
    events = [Event(kind, name, row, event_minute(
        times, kind, row, rows, sent_here=kind == 'catch' and (name, row) in sends))
        for kind, name, row in events_raw]
    for e in events:
        mention(e.name, e.row)

    hints = {}
    for i, row in enumerate(rows):
        for cell in (row['bsm'], row['notes'], row['speaker'], row['description']):
            hint = 'HH' if _HH.search(cell or '') else 'backup' if _BACKUP.search(cell or '') else ''
            if not hint:
                continue
            toks = _tokens(cell)
            named = [roster.match_at(toks, p)[0] for p in range(len(toks))]
            named = [n for n in named if n and name_key(n) not in {c.lower() for c in crew}]
            # "no clicker, handheld" names nobody: it is about the row's speakers.
            for name in named or speakers.get(i, ()):
                if hints.get(name) != 'HH':
                    hints[name] = hint

    segments = [i for i, t in enumerate(times) if t.is_segment]
    window_flags = _window_flags(rows, times, events, segments, speakers)
    listed = {name for names in speakers.values() for name in names}
    cued = {e.name for e in events}
    if not listed or len(listed & cued) < NO_CUE_MIN_COVERAGE * len(listed):
        # Cues are absent or too sparse to mean anything: on/off comes from segment times.
        window_flags = [f for f in window_flags if f[0] != 'no_cue']
        # Exits decide off times only where there are no cues: say which
        # exit lines name nobody ShowStack knows.
        for i, word in unknown_exits:
            flags.append(('who_exits', i, 'Line {}: who exits? "{}" is not a person ShowStack '
                          'recognised, so nobody comes off here.'.format(rows[i]['line'] or '?', word), None))
    flags += window_flags
    for name in sorted(roster.bsm_only):
        first = min(mentions.get(name, {None}) - {None}, default=None)
        flags.append(('bsm_only', first, 'Line {}: {} is named in a BSM cue but nowhere else. If '
                      "this is someone's nickname, merge it into them.".format(
                          (rows[first]['line'] if first is not None else '') or '?', name), name))

    people = {name: {'rows': sorted(mentions.get(name, ())), 'mic_hint': hints.get(name, ''),
                     'bsm_only': name in roster.bsm_only, 'intro': refs.intro.get(name),
                     'exits': sorted(exits.get(name, ())), 'enters': sorted(enters.get(name, ())),
                     'mics': mics.get(name, [])}
              for name in roster.found | set(mentions)}
    starts = [times[i].t0 for i in segments]
    ends = [times[i].t1 for i in segments]
    if starts:
        span = (min(starts), max(ends))
    else:
        known_t = [t.minute for t in times if t.minute is not None]
        span = (min(known_t), max(known_t)) if known_t else (None, None)
    return Analysis(times=times, people=people, events=events, flags=_dedupe(flags),
                    crew=list(crew), segments=segments, span=span)


def _brought_on(text, roster):
    """Names a description brings on stage: the "Name Surname" items listed
    after welcome / join / introduce wording, and any known full name there.
    Titles, companies and single first names are not counted."""
    m = _BRINGS_ON.search(re.sub(r'\([^)]*\)', ' ', text or ''))
    if not m:
        return []
    rest = text[m.end():]
    names = []
    for part in re.split(r',|&|\band\b|;|:|…|\.\.\.|\.\s', rest):
        words = part.split()
        while words and not words[0][:1].isupper():
            words = words[1:]   # "to Ann Lee"
        while words and not _is_name_part(words[-1]):
            words = words[:-1]
        if (2 <= len(words) <= 4 and _is_name_word(words[0])
                and all(_is_name_part(w) for w in words[1:])
                and not any(_clean_token(w).lower() in TITLE_WORDS | ORG_WORDS
                            or _clean_token(w).lower().split('-')[-1] in ORG_WORDS for w in words)
                and not (len(words) == 2 and _honorific(words[0]))):
            names.append(' '.join(_clean_token(w) for w in words))
    toks = _tokens(rest)
    for i in range(len(toks)):
        name, used = roster.match_at(toks, i)
        if name and used > 1:
            names.append(name)
    return list(dict.fromkeys(names))


def _description_flags(rows, roster, speakers):
    """Client E: a description brings people on that no Speaker cell on its
    row or a few rows either side names. Flagged only: they are not made into
    people."""
    flags = []
    for i, row in enumerate(rows):
        names = _brought_on(row['description'], roster)
        if not names:
            continue
        near = range(max(0, i - DESC_NEARBY_ROWS), min(len(rows), i + DESC_NEARBY_ROWS + 1))
        text = ' '.join(rows[j]['speaker'] or '' for j in near).lower()
        listed = {name_key(_bare(n)) for j in near for n in speakers.get(j, ())}

        def present(name):
            bare = _bare(name)
            if name_key(bare) in listed or bare.lower() in text:
                return True
            # Still counts if its first name or surname is there ("Ann" or "Dr. Lee").
            return any(re.search(r'\b{}\b'.format(re.escape(w.lower())), text)
                       for w in (_first_name(name), _surname(name)) if w)
        if not all(present(n) for n in names):
            flags.append(('description_names', i, 'Line {}: description names people not in the '
                          'Speaker column — check who goes on'.format(row['line'] or '?'), None))
    return flags


def _verbs(text):
    """[(kind, start, end)] of exit / re-entry / stays words in ``text``, in order."""
    found = [(kind, m.start(), m.end()) for kind, rx in (('exit', _EXIT), ('enter', _REENTER), ('stay', _STAYS))
             for m in rx.finditer(text or '')]
    return sorted(found, key=lambda v: v[1])


def _trailing_names(toks, roster, refs):
    """Names ending the token list, joined by "," "and" "&": who an exit verb
    right after them is about. (names, unresolved last word or None)."""
    end = len(toks)
    while end and toks[end - 1] in (',', ';'):
        end -= 1
    names = []
    while end:
        hit = None
        for start in range(max(0, end - 5), end):
            name, used = roster.match_at(toks, start)
            if name and start + used == end:
                hit = (start, name)
                break
        if hit is None and refs is not None:
            for start in (end - 2, end - 1):
                if start < 0:
                    continue
                name, used = refs.short_at(toks, start)
                if name and name is not AMBIGUOUS and start + used == end:
                    hit = (start, name)
                    break
        if hit is None:
            break
        names.insert(0, hit[1])
        end = hit[0]
        if end and toks[end - 1].lower() in (',', '&', 'and'):
            end -= 1
            continue
        break
    unresolved = None
    if not names and toks:
        last = _clean_token(toks[-1])
        if last and _is_name_word(last) and last.lower() not in GROUP_ALL | GROUP_BOTH \
                and not (last.isupper() and len(last) <= 4):
            unresolved = last
    return names, unresolved


def group_exit(text):
    """('all' | 'both', [lower-cased words named as staying]) for a
    description whose exit is said of a group, else None. Pure: the plan
    reads it straight from the stored rows."""
    verbs = _verbs(text)
    kind, stays = None, []
    prev = 0
    for verb, start, end in verbs:
        words = [_clean_token(t).lower() for t in _tokens(text[prev:start]) if _clean_token(t)]
        if verb == 'exit' and words:
            if words[-1] in GROUP_ALL:
                kind = kind or 'all'
            elif words[-1] in GROUP_BOTH:
                kind = kind or 'both'
        elif verb == 'stay':
            run = []
            for w in reversed(words):
                if w in (',', '&', 'and'):
                    continue
                if not w[:1].isalpha() or w in NOT_NAMES:
                    break
                run.insert(0, w)
            stays += run
        prev = end
    return (kind, stays) if kind else None


def mic_callouts(text):
    """[(kind, [numbers], name text or '')] in one cell, in order. ``kind`` is
    a value of MIC_KINDS; a name comes with a list item only ("Lav #1: Ann
    Reed", up to the next callout). A wired mic ("Podium mic 1") is skipped."""
    text = text or ''
    found = [m for m in _CALLOUT.finditer(text) if not _WIRED.search(text[:m.start()])]
    out = []
    for k, m in enumerate(found):
        kind = MIC_KINDS[m[1].lower().replace('-', '')]
        numbers = [int(n) for n in _NUMBERS.findall(m[2])]
        span = _RANGE.match(m[2])
        if span and int(span[1]) < int(span[2]) <= int(span[1]) + MIC_RANGE_MAX:
            numbers = list(range(int(span[1]), int(span[2]) + 1))
        name = ''
        rest = text[m.end():found[k + 1].start() if k + 1 < len(found) else len(text)]
        after = _NAME_FOLLOWS.match(rest)
        if after and len(numbers) == 1:
            name = rest[after.end():].strip()
        out.append((kind, numbers, name))
    return out


def mic_label(kind, number):
    return '{} {}'.format(kind, number)


def _list_name(text, roster):
    """Who a list item means: (display name or None, the words read). The
    words at its start that could be a name, then any trailing cell text is
    ignored ("Ann Reed Fade music"). A spelling a little off a known full
    name is that person when only one is that close (Client F: a surname
    with an extra s); nobody is made from a list."""
    toks = _tokens(text)
    words = []
    for tok in toks:
        if tok in SEPARATORS or tok in PUNCT or not (_is_name_part(tok) or _honorific(tok)) or len(words) == 4:
            break
        words.append(_clean_token(tok))
    if not words:
        return None, []
    name, used = roster.match_at(words, 0)
    if name and (used > 1 or len(words) == 1):
        return name, words
    if len(words) < 2:
        return None, words
    full = {name_key(n): n for n in roster.names if len(_bare(n).split()) > 1}
    full.update({name_key(_bare(n)): n for n in roster.names if len(_bare(n).split()) > 1})
    for size in sorted({len(words), 2}, reverse=True):
        near = difflib.get_close_matches(name_key(' '.join(words[:size])), full, n=3, cutoff=MIC_NAME_CUTOFF)
        owners = {full[k] for k in near}
        if len(owners) == 1:
            return owners.pop(), words
    return None, words


def _mic_entry(row, kind, number, via):
    return {'row': row, 'kind': kind, 'n': number, 'label': mic_label(kind, number),
            'pool': MIC_POOLS.get(kind), 'via': via}


def _mic_numbers(rows, roster, speakers):
    """({display name: [entries]}, flags). Lists first, over every row, then
    number-only cells, which need them. One number and one speaker on a row
    is that speaker's; any other mix is never matched by position (Client F
    writes "Lav 3,6" over two people in the other order): it agrees with the
    lists, or it is flagged. A list name nobody has is flagged, no one is made."""
    entries, flags, bare = {}, [], {}
    for i, row in enumerate(rows):
        seen = set()
        for cell in (row.get('audio'), row.get('bsm'), row.get('notes')):
            for kind, numbers, text in mic_callouts(cell):
                if not text:
                    bare.setdefault(i, [])
                    bare[i] += [(kind, n) for n in numbers if (kind, n) not in bare[i]]
                    continue
                name, words = _list_name(text, roster)
                if name is None:
                    if len(words) > 1:
                        flags.append(('mic_name', i, 'Line {}: {} is listed for "{}", who is not in the Speaker '
                                      'column. Merge or add them to use this number.'.format(
                                          row['line'] or '?', mic_label(kind, numbers[0]), ' '.join(words)), None))
                elif (name, kind, numbers[0]) not in seen:
                    seen.add((name, kind, numbers[0]))
                    entries.setdefault(name, []).append(_mic_entry(i, kind, numbers[0], 'list'))
    for i, called in sorted(bare.items()):
        who = speakers.get(i, [])
        if not who:
            continue
        if len(who) == 1 and len(called) == 1:
            entries.setdefault(who[0], []).append(_mic_entry(i, called[0][0], called[0][1], 'cell'))
            continue
        latest = {max((e for e in entries.get(name, ()) if e['row'] <= i), key=lambda e: e['row'])['label']
                  for name in who if any(e['row'] <= i for e in entries.get(name, ()))}
        labels = {mic_label(*c) for c in called}
        if labels != latest or len(latest) != len(who):
            flags.append(('mic_which', i, 'Line {}: {} for {} people \u2014 which is which? Not used.'.format(
                rows[i]['line'] or '?', ', '.join(mic_label(*c) for c in called), len(who)), None))
    for found in entries.values():
        found.sort(key=lambda e: e['row'])
    return entries, flags


def _subject(toks, roster, refs):
    """The name opening a sentence, for "Ann intros Bo, then departs"."""
    name, _ = roster.match_at(toks, 0)
    if not name and refs is not None:
        name, _ = refs.short_at(toks, 0)
    return [name] if name and name is not AMBIGUOUS else []


def exits_and_entries(text, roster, refs=None):
    """(names exiting, names re-entering, words not recognised before an exit)
    in one description. Names are read as in Speaker cells: full names, a
    first name meaning whoever was introduced last, "Dr. Surname"."""
    exits, enters, unknown = [], [], []
    prev = 0
    for verb, start, end in _verbs(text):
        toks = _tokens(text[prev:start])
        prev = end
        if verb == 'stay' or not toks:
            continue
        if _clean_token(toks[-1]).lower() in GROUP_ALL | GROUP_BOTH:
            continue
        names, unresolved = _trailing_names(toks, roster, refs)
        if not names and toks[-1].lower() == 'then':
            names = _subject(toks, roster, refs)
        (exits if verb == 'exit' else enters).extend(names)
        if unresolved and verb == 'exit':
            unknown.append(unresolved)
    return list(dict.fromkeys(exits)), list(dict.fromkeys(enters)), unknown


def description_candidates(text):
    """The names a "not listed" description brings on, for the user to check:
    the text after the welcome / introduce wording (else all of it), split on
    "," "and" "&", a suffix such as "MD" kept on the name before it, and only
    items of two to four capitalised words ("Title - Name" keeps the name)."""
    text = re.sub(r'\([^)]*\)', ' ', text or '')
    m = _BRINGS_ON.search(text)
    rest = text[m.end():] if m else text
    # "the 3 presenters. Name, Name": what follows the last full stop or colon
    # before the first name list.
    pieces, piece = [], ''
    for chunk in re.split(r'(\.\.\.|…|:|\.\s)', rest):
        last = piece.split()[-1].lower() if piece.split() else ''
        if chunk in ('...', '…', ':') or (chunk == '. ' or chunk.startswith('.') and not chunk.strip('. ')) \
                and not (last in HONORIFICS or len(last) == 1):
            pieces.append(piece)
            piece = ''
        else:
            piece += chunk
    pieces = [p for p in pieces + [piece] if p.strip()]
    out = []
    for piece in pieces:
        items = [i.strip() for i in re.split(r',|&|\band\b', piece)]
        for item in items:
            if not item:
                continue
            if out and item.strip('. ').lower() in NAME_SUFFIXES:
                out[-1] = '{}, {}'.format(out[-1], item.strip(' .'))
                continue
            item = re.split(r'\s[-–—]\s', item)[-1]       # "your MC's - Name"
            words = item.split()
            while words and not _is_name_word(words[0]) and not _honorific(words[0]):
                words = words[1:]
            while words and not _is_name_part(words[-1]):
                words = words[:-1]
            if not 2 <= len(words) <= 4 or len(words) == 2 and _honorific(words[0]):
                continue
            if not all(_is_name_part(w) or _honorific(w) for w in words):
                continue
            if any(_clean_token(w).lower() in TITLE_WORDS | ORG_WORDS for w in words):
                continue
            out.append(' '.join(w.strip(',;:!?"“”') for w in words))
    return list(dict.fromkeys(out))


def segment_heading(rows, start, end, named=(), minutes=None):
    """(name, is_break) for the segment whose rows are rows[start:end]: the
    first description that is not a VOG line, records cue or stage set
    (Client E), and whether it is a break. ``named``: indexes of rows that
    name a person to speak; ``minutes``: the segment's length."""
    descs = [(r['description'] or '').strip() for r in rows[start:end]]
    name = re.sub(r'\s+', ' ', next((d for d in descs if d and not _NOT_A_HEADING.match(d)),
                                    descs[0] if descs else ''))
    speakers = any((r['speaker'] or '').strip() for r in rows[start:end])
    anyone = any(k in named for k in range(start, end))
    is_break = ((any(_BREAK.match(d) for d in descs) and not speakers)
                or (bool(_BREAK_NAME.search(name)) and start not in named)
                or (minutes is not None and minutes >= BREAK_QUIET_MIN and not speakers and not anyone))
    return name, is_break


def _dedupe(flags):
    seen, out = set(), []
    for f in flags:
        if f[2] not in seen:
            seen.add(f[2])
            out.append(f)
    return out


def _window_flags(rows, times, events, segments, speakers):
    """Sent-never-caught, caught-but-still-listed, and listed-with-no-cue."""
    flags = []
    windows = {}
    for e in sorted(events, key=lambda e: (e.minute if e.minute is not None else 0, e.row,
                                           e.kind != 'send')):
        ws = windows.setdefault(e.name, [])
        if e.kind == 'send':
            if ws and ws[-1]['off'] is None:
                continue  # already on stage
            ws.append({'on': e.minute, 'off': None, 'row': e.row, 'off_row': None})
        elif ws and ws[-1]['off'] is None:
            ws[-1]['off'], ws[-1]['off_row'] = e.minute, e.row

    listed = set()

    def line(i):
        return rows[i]['line'] or '?'

    def seg_label(i):
        return '"{}" ({}–{})'.format(rows[i]['description'][:60], hm(times[i].t0), hm(times[i].t1))

    for name, ws in windows.items():
        for w in ws:
            if w['on'] is None:
                continue
            if w['off'] is None:
                flags.append(('never_caught', w['row'], 'Line {}: {} is sent but never caught.'.format(
                    line(w['row']), name), name))
                continue
            # The segment that follows the catch still lists them: they stay on.
            nxt = next((i for i in segments if i > w['off_row']), None)
            if nxt is not None and name in speakers.get(nxt, ()):
                listed.add((name, nxt))
                flags.append(('caught_but_listed', w['off_row'], 'Line {}: {} is caught but still '
                              'listed as a speaker in {}, so kept on.'.format(
                                  line(w['off_row']), name, seg_label(nxt)), name))
    for i in segments:
        for name in speakers.get(i, ()):
            if (name, i) in listed:
                continue
            covered = any(w['on'] is not None and w['on'] - COVER_SLACK_MIN <= times[i].t0
                          and (w['off'] is None or times[i].t0 <= w['off'])
                          for w in windows.get(name, ()))
            if not covered:
                flags.append(('no_cue', i, 'Line {}: {} is listed as a speaker in {} with no send '
                              'or catch.'.format(line(i), name, seg_label(i)), name))
    return flags
