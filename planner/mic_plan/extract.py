"""Read a showflow PDF's table into rows keyed by column name.

Columns are found by their header text, never by position: the layouts seen
so far differ in width (9 and 14 columns), in whether the first column is
blank or "LINE #", and in which extra columns sit between the ones we use.
The header usually appears only on page 1; later pages continue the same
table, so the mapping carries over as long as the column count matches.

No Django imports: the importer and the tests call this directly.
"""

import io
import re
import time

# Header text (lower-cased, spaces collapsed) -> the field it fills. Matched
# case-insensitively, and again with the spaces taken out, because a narrow
# column wraps its header mid-word ("DURATIO N").
HEADER_ALIASES = {
    'line': ('', 'line', 'line #', 'line#', '#', 'ln'),
    'start': ('start', 'start time'),
    'end': ('end', 'end time'),
    'duration': ('duration', 'dur', 'run time', 'length'),
    'description': ('description', 'segment', 'item'),
    'speaker': ('speaker name', 'speaker', 'speakers', 'speaker names', 'talent', 'presenter',
                'presenters'),
    'bsm': ('bsm', 'bsm notes', "bsm's"),
    'notes': ('notes', 'note', 'general notes'),
}
FIELDS = tuple(HEADER_ALIASES)
_LOOKUP = {alias: field for field, aliases in HEADER_ALIASES.items() for alias in aliases}
_LOOKUP_COMPACT = {alias.replace(' ', ''): field for alias, field in _LOOKUP.items()}

# A longer file is refused before pdfplumber reads a page; see MAX_PAGES in
# the importer for the timing behind the number.
MAX_PAGES_DEFAULT = 30
# Stop reading past this, whatever the page count: one pathological page
# must not hold a gunicorn worker until its 30 s timeout kills it.
TIME_BUDGET_S = 15


class ShowflowError(ValueError):
    """The PDF could not be read as a showflow. The message is shown as is."""


def _norm(cell):
    return re.sub(r'\s+', ' ', (cell or '').replace('\n', ' ')).strip()


def _key(cell):
    return _norm(cell).lower().rstrip(':')


def header_map(cells):
    """{column index: field} if ``cells`` is a showflow header row, else None.

    A header names Start and Description, plus at least one of End, Speaker
    or BSM, so a stray row that happens to say "Start" is not taken for one.
    Unknown columns map to nothing and are ignored.
    """
    mapping = {}
    for i, cell in enumerate(cells):
        key = _key(cell)
        field = _LOOKUP.get(key) or _LOOKUP_COMPACT.get(key.replace(' ', ''))
        if field and field not in mapping.values():
            mapping[i] = field
    found = set(mapping.values())
    if {'start', 'description'} <= found and found & {'end', 'speaker', 'bsm'}:
        return mapping
    return None


_LINE_NO = re.compile(r'^\d{1,4}[a-z]?$')


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


def rows_from_tables(pages):
    """Rows from ``pages``: a list (one per page) of tables, each a list of
    rows of cells. Separated from pdfplumber so tests can feed tables in.

    Returns ``(rows, columns, warnings)``: each row a dict of FIELDS plus
    ``page_no``; ``columns`` the header as [{'header', 'field'}].
    """
    mapping = None
    width = None
    columns = []
    rows = []
    raw = []          # each row's cells as read, for _find_line_column
    warnings = []
    for page_no, tables in enumerate(pages, start=1):
        for table in tables:
            for cells in table:
                cells = [_norm(c) for c in cells]
                found = header_map(cells)
                if found:
                    if mapping is None:
                        mapping, width = found, len(cells)
                        columns = [{'header': c, 'field': found.get(i)} for i, c in enumerate(cells)]
                    continue  # a repeated header on a later page
                if mapping is None or not any(cells):
                    continue
                if len(cells) != width:
                    warnings.append('Page {}: a table with {} columns where the header has {}; '
                                    'its rows were skipped.'.format(page_no, len(cells), width))
                    break
                row = {field: '' for field in FIELDS}
                for i, field in mapping.items():
                    row[field] = cells[i]
                row['page_no'] = page_no
                rows.append(row)
                raw.append(cells)
    if mapping is not None and rows and not any(r['line'] for r in rows):
        _find_line_column(rows, raw, mapping, columns)
    if mapping is None:
        raise ShowflowError(
            "Couldn't find the column header on any page. Mic Plan looks for a row that "
            "names Start and Description, plus End, Speaker Name or BSM.")
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
            raise ShowflowError('That PDF has {} pages; Mic Plan reads up to {}. Split it into '
                                'parts (an AM and a PM file, say) and import each.'.format(
                                    count, max_pages))
        pages = []
        started = time.monotonic()
        for page in pdf.pages:
            try:
                pages.append([] if _only_line_numbers(page) else page.extract_tables())
            except Exception as exc:
                raise ShowflowError("Page {} couldn't be read ({}).".format(
                    page.page_number, type(exc).__name__))
            page.close()  # drop pdfplumber's per-page object cache as we go
            if time.monotonic() - started > time_budget:
                raise ShowflowError('That PDF is taking too long to read (stopped at page {} of '
                                    '{}). Split it into parts and import each.'.format(
                                        page.page_number, count))
    rows, columns, warnings = rows_from_tables(pages)
    return rows, columns, warnings, count
