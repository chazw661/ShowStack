"""Read a showflow PDF's table into rows keyed by column name.

Columns are found by their header text, never by position: the layouts seen
so far differ in width (9 and 14 columns), in whether the first column is
blank, "LINE #" or "CUE", and in which extra columns sit between the ones we
use. The header usually appears only on page 1; later pages continue the same
table, so the mapping carries over as long as the column count matches.

No Django imports: the importer and the tests call this directly.
"""

import io
import re
import time

from .parser import parse_clock

# Header text -> the field it fills. Matched on letters and digits alone (see
# _key): any case, and a narrow column wraps its header mid-word ("DURATIO N").
HEADER_ALIASES = {
    'line': ('', 'line', 'line #', '#', 'ln', 'cue', 'cue #'),
    'start': ('start', 'start time'),
    'end': ('end', 'end time'),
    'duration': ('duration', 'dur', 'run time', 'length'),
    'description': ('description', 'event', 'segment', 'item', 'content'),
    'speaker': ('speaker name', 'speaker', 'speakers', 'speaker names', 'talent', 'presenter',
                'presenters'),
    'bsm': ('bsm', 'bsm notes', "bsm's"),
    'audio': ('audio', 'audio notes'),
    'notes': ('notes', 'note', 'general notes'),
}
FIELDS = tuple(HEADER_ALIASES)
# A header row names Start and a description, plus one of these.
HEADER_ANY = {'end', 'speaker', 'bsm'}
# Client F: a Speaker cell that says nobody speaks on this row.
NOBODY = {'x', '-', '\u2013', '\u2014', 'n/a'}
# Client G: the headings of a showflow laid out as a document, on one short
# line ("TIME EVENT/ PRESENTER SUPPORT"). Any three of them.
DOCUMENT_HEADINGS = {'time', 'event', 'presenter', 'support'}
DOCUMENT_HEADING_WORDS = 6
DOCUMENT_LAYOUT = ('This showflow is laid out as a document, not a table. Mic Planner reads table-style '
                   'run-of-shows today; document-style support is planned.')

# A longer file is refused before pdfplumber reads a page; see MAX_PAGES in
# the importer for the timing behind the number.
MAX_PAGES_DEFAULT = 60
# Stop reading past this, whatever the page count: one pathological page
# must not hold a gunicorn worker until its 30 s timeout kills it.
TIME_BUDGET_S = 15


class ShowflowError(ValueError):
    """The PDF could not be read as a showflow. The message is shown as is.
    ``layout``: 'document' or 'unknown' when no table header was found."""

    def __init__(self, message, layout=None):
        super().__init__(message)
        self.layout = layout


def _norm(cell):
    return re.sub(r'\s+', ' ', (cell or '').replace('\n', ' ')).strip()


def _key(cell):
    return re.sub(r'[^a-z0-9]', '', (cell or '').lower())


_LOOKUP = {_key(alias): field for field, aliases in HEADER_ALIASES.items() for alias in aliases}


def _column_map(cells):
    """{column index: field} for the cells that name a column we use. Unknown
    columns map to nothing and are ignored; the first of a field wins."""
    mapping = {}
    for i, cell in enumerate(cells):
        field = _LOOKUP.get(_key(cell))
        if field and field not in mapping.values():
            mapping[i] = field
    return mapping


def header_map(cells):
    """{column index: field} if ``cells`` is a showflow header row, else None.

    A header names Start and a description, plus at least one of End, Speaker
    or BSM, so a stray row that happens to say "Start" is not taken for one.
    """
    mapping = _column_map(cells)
    found = set(mapping.values())
    return mapping if {'start', 'description'} <= found and found & HEADER_ANY else None


def _named_fields(cells):
    """The fields ``cells`` names in words (a blank cell names no column)."""
    return {field for i, field in _column_map(cells).items() if cells[i]}


def _near_miss(cells):
    """What to say about the row closest to a header."""
    named = [c for c in cells if c]
    shown = ', '.join(named[:6]) + ('\u2026' if len(named) > 6 else '')
    found = _named_fields(cells)
    missing = [word for field, word in (('start', 'the start time'), ('description', 'the description'))
               if field not in found]
    if missing:
        return 'Found a header row with {} but no column Mic Planner recognises as {}.'.format(
            shown, ' or '.join(missing))
    return 'Found a header row with {} but no End, Speaker or BSM column.'.format(shown)


_LINE_NO = re.compile(r'^\d{1,4}[a-z]?$')
_TIME_LIKE = re.compile(r'(?i)^\d{1,2}(?::\d{2}|\s*[ap]\.?m)')


def _find_line_column(rows, raw, mapping, columns):
    """The line-number column when the header doesn't say which it is (one
    file heads it "a" and leaves the blank-headed column empty): the
    unmapped column whose filled cells are nearly all line numbers."""
    for i in range(len(raw[0])):
        if i in mapping and mapping[i] != 'line':
            continue
        filled = [cells[i] for cells in raw if cells[i]]
        if len(filled) >= max(3, len(raw) // 4) and \
                sum(bool(_LINE_NO.match(c)) for c in filled) >= 0.9 * len(filled):
            for row, cells in zip(rows, raw):
                row['line'] = cells[i]
            columns[i]['field'] = 'line'
            for col in columns:
                if col is not columns[i] and col['field'] == 'line':
                    col['field'] = None
            return


def _title_row(cells, mapping):
    """Client F: a page's show title or date, above its repeated header. One
    cell filled, and neither a line number nor a column we read."""
    filled = [i for i, c in enumerate(cells) if c]
    return (len(filled) == 1 and mapping.get(filled[0], 'line') == 'line'
            and not _LINE_NO.match(cells[filled[0]]))


def _appendix_row(row):
    """Client F: past the show, the same grid holds another table (a preset
    list) under its own headings. Its Start and End columns hold text."""
    return bool(row['start'] and row['end'] and not _TIME_LIKE.match(row['start'])
                and not _TIME_LIKE.match(row['end']))


def rows_from_tables(pages, document=False):
    """Rows from ``pages``: a list (one per page) of tables, each a list of
    rows of cells. Separated from pdfplumber so tests can feed tables in.
    ``document``: a page with no table carried document-style headings.

    Returns ``(rows, columns, warnings)``: each row a dict of FIELDS plus
    ``page_no``; ``columns`` the header as [{'header', 'field'}].
    """
    mapping = None
    width = None
    columns = []
    rows = []
    raw = []          # each row's cells as read, for _find_line_column
    warnings = []
    best, best_score = None, 1     # the row closest to a header: two named columns at least
    clock_seen = stopped = False
    for page_no, tables in enumerate(pages, start=1):
        for table in tables:
            table_start = len(rows)
            for cells in table:
                cells = [_norm(c) for c in cells]
                found = header_map(cells)
                if found:
                    if mapping is None:
                        mapping, width = found, len(cells)
                        columns = [{'header': c, 'field': found.get(i)} for i, c in enumerate(cells)]
                    # A repeated header on a later page: titles above it are not rows.
                    while len(rows) > table_start and _title_row(raw[-1], mapping):
                        rows.pop()
                        raw.pop()
                    continue
                if mapping is None:
                    score = len(_named_fields(cells))
                    if score > best_score:
                        best, best_score = cells, score
                    continue
                if stopped or not any(cells):
                    continue
                if len(cells) != width:
                    warnings.append('Page {}: a table with {} columns where the header has {}; '
                                    'its rows were skipped.'.format(page_no, len(cells), width))
                    break
                row = {field: '' for field in FIELDS}
                for i, field in mapping.items():
                    row[field] = cells[i]
                if clock_seen and _appendix_row(row):
                    stopped = True
                    warnings.append('Page {}: "{}" starts a table that is not part of the run of show; '
                                    'it and the rows after it were skipped.'.format(page_no, row['start']))
                    continue
                clock_seen = clock_seen or bool(parse_clock(row['start']))
                if row['speaker'].lower() in NOBODY:
                    row['speaker'] = ''
                row['page_no'] = page_no
                rows.append(row)
                raw.append(cells)
    if mapping is not None and rows and not any(r['line'] for r in rows):
        _find_line_column(rows, raw, mapping, columns)
    if mapping is None:
        if best is not None:
            raise ShowflowError(_near_miss(best), layout='unknown')
        if document:
            raise ShowflowError(DOCUMENT_LAYOUT, layout='document')
        raise ShowflowError(
            "Couldn't find the column header on any page. Mic Planner looks for a row that "
            "names Start and Description (or Event), plus End, Speaker (or Presenter) or BSM.",
            layout='unknown')
    fields = set(mapping.values())
    if 'bsm' not in fields:
        warnings.append('No BSM column: send/catch cues cannot be read, so people come from '
                        'the Speaker column and welcome lines only.')
    if 'speaker' not in fields:
        warnings.append('No Speaker column: people come from welcome lines and BSM cues only.')
    return rows, columns, list(dict.fromkeys(warnings))


def _only_line_numbers(page):
    """True if the page's text is nothing but digits: an empty grid, at most
    numbered down the side. Finding the table on such a page costs more than
    on a full one (a 27-column ruled grid, 0.26 s against 0.08 s) and can
    only yield blank rows, so it is skipped."""
    return not any(not (c['text'].isdigit() or c['text'].isspace()) for c in page.chars)


def _document_headings(page):
    """True if a short line of the page's text is document-style headings."""
    for line in (page.extract_text() or '').split('\n'):
        words = re.findall(r'[a-z]+', line.lower())
        if len(words) <= DOCUMENT_HEADING_WORDS and len(DOCUMENT_HEADINGS.intersection(words)) >= 3:
            return True
    return False


def extract(data, max_pages=MAX_PAGES_DEFAULT, time_budget=TIME_BUDGET_S):
    """Rows from PDF bytes. Raises ShowflowError for anything unreadable.

    Returns ``(rows, columns, warnings, page count)``.
    """
    import pdfplumber

    if not data.startswith(b'%PDF-'):
        raise ShowflowError('That file is not a PDF.')
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
        pdf.pages  # parses the page tree: a broken file fails here
    except Exception as exc:  # pdfminer raises a zoo of types
        raise ShowflowError("That PDF couldn't be opened ({}).".format(type(exc).__name__))
    with pdf:
        count = len(pdf.pages)
        if count > max_pages:
            raise ShowflowError('That PDF has {} pages; Mic Planner reads up to {}. Split it into '
                                'parts (an AM and a PM file, say) and import each.'.format(
                                    count, max_pages))
        pages = []
        document = False
        started = time.monotonic()
        for page in pdf.pages:
            try:
                tables = [] if _only_line_numbers(page) else page.extract_tables()
                document = document or (not tables and _document_headings(page))
                pages.append(tables)
            except Exception as exc:
                raise ShowflowError("Page {} couldn't be read ({}).".format(
                    page.page_number, type(exc).__name__))
            page.close()  # drop pdfplumber's per-page object cache as we go
            if time.monotonic() - started > time_budget:
                raise ShowflowError('That PDF is taking too long to read (stopped at page {} of '
                                    '{}). Split it into parts and import each.'.format(
                                        page.page_number, count))
    rows, columns, warnings = rows_from_tables(pages, document)
    return rows, columns, warnings, count
