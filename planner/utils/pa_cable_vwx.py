"""Import a Vectorworks cable worksheet into the PA Cable Schedule.

``tools/vectorworks/showstack_link_cables.py`` fills each cable's fields and a
worksheet exports one row per cable. The file is parsed and planned here, and
nothing is written until ``apply_plan``: the preview page shows the plan, and
Confirm builds it again from the same file and refuses if ``digest`` no longer
matches what was previewed.

The file
--------
Classic Mac CR line endings, columns matched by header name, a database
summary row of numbers under the header (``4,2,4,2,135.1,2`` -- its "label" is
a count, so a blank label does not identify it), trailing rows of nothing.

Runs
----
A cable's identity is its label, which is a project ``PAZone``. A new label
creates a zone with the model's defaults, the same as the "+" on the entry
form. An existing entry is updated only when it is the one entry with that
label, is free text, and has at most one fan-out: anything else could be the
wrong cable, so the row is an error. Blank Destination or Fan-Out in the file
keeps what the entry has: the linker leaves them blank when nothing is close
enough, which says nothing about the entry.

``length`` is whole feet and always rounds up. Stock lengths are whole feet
too, so this cannot change the cables ordered, where rounding 50.2 down to 50
would order a 50' for a run it does not reach.

Extensions
----------
A row with Extension Of is a stock-length extension on that run's fan-out.
Identical ones are one row with a summed quantity, as they are entered by
hand. The file replaces the fan-out's extensions, unless it has no Extension
Of column (older exports say nothing about them) or one of the run's
extension rows failed (a partial list would lose a cable).
"""

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from planner.models import PACableSchedule, PAFanOut, PAFanOutExtension, PAZone

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
#: Beyond any real run, and well inside what the integer column can hold.
MAX_FEET = 5000

#: Worksheet header -> field, lower-case.
HEADERS = {
    'cable label': 'label',
    'destination': 'destination',
    'connector': 'connector',
    'fan-out': 'fan_out',
    'length (ft)': 'length',
    'extension of': 'extension_of',
}
OPTIONAL_HEADERS = {'extension_of'}

#: Vectorworks connector name or ID, lower-case -> PACableSchedule.cable.
CONNECTORS = {
    'speaker twist 4': 'NL_4',
    'speakertwist4': 'NL_4',
    'speaker twist 8': 'NL_8',
    'speakertwist8': 'NL_8',
    'ca-com 8 pin speaker': 'CA-COM',
    'cacom-8': 'CA-COM',
    'sc32': 'SC32',
}

#: Fan-out names the drawing uses that ShowStack does not, lower-case.
FAN_OUT_ALIASES = {
    'sub cable': 'NL8_TO_4XNL2',
}

#: A run's cable type -> the extension cable type. Nothing else extends.
EXTENSION_CABLES = {'NL_4': 'NL4', 'NL_8': 'NL8'}

_NUMBER = re.compile(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)')
_FILE_FIELDS = ('label', 'destination', 'connector', 'fan_out', 'length', 'extension_of')


class VwxFileError(Exception):
    """The file as a whole cannot be read. The message is shown to the user."""


@dataclass
class Row:
    line: int
    label: str = ''
    destination: str = ''
    connector: str = ''
    fan_out: str = ''
    length: str = ''
    extension_of: str = ''


@dataclass
class ParsedFile:
    rows: list
    has_extension_column: bool


@dataclass
class ExtensionRow:
    row: Row
    cable: str = ''
    stock: int = 0
    error: str = ''


@dataclass
class Run:
    """One cable run: from a file row, or (``row`` None) an entry already in
    the project that the file only adds extensions to."""
    label: str
    action: str
    row: Row = None
    entry: PACableSchedule = None
    cable: str = ''
    feet: int = 0
    destination: str = ''
    fan_code: str = ''
    fans: list = field(default_factory=list)
    extensions: list = field(default_factory=list)
    groups: Counter = field(default_factory=Counter)
    replace_extensions: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def status(self):
        return 'error' if self.errors else self.action

    @property
    def fan(self):
        return self.fans[0] if self.fans else None

    @property
    def cable_display(self):
        return dict(PACableSchedule.CABLE_TYPE_CHOICES).get(self.cable, '')

    @property
    def fan_display(self):
        code = self.fan_code or (self.fan.fan_out_type if self.fan else '')
        return dict(PACableSchedule.FAN_OUT_CHOICES).get(code, '')

    @property
    def groups_display(self):
        return ', '.join(_extension_text(key, qty) for key, qty in sorted(self.groups.items()))


@dataclass
class Plan:
    filename: str
    has_extension_column: bool
    runs: list = field(default_factory=list)
    orphans: list = field(default_factory=list)

    @property
    def to_write(self):
        return [run for run in self.runs if not run.errors]

    @property
    def created(self):
        return sum(1 for run in self.to_write if run.action == 'new')

    @property
    def updated(self):
        return sum(1 for run in self.to_write if run.action == 'update')

    @property
    def skipped(self):
        file_runs = sum(1 for run in self.runs if run.row and run.errors)
        extensions = [e for run in self.runs for e in run.extensions] + self.orphans
        return file_runs + sum(1 for e in extensions if e.error)

    @property
    def extension_count(self):
        return sum(sum(run.groups.values()) for run in self.to_write if run.replace_extensions)

    @property
    def has_changes(self):
        return any(run.action != 'extensions' or run.replace_extensions for run in self.to_write)


def read_upload(upload):
    """The uploaded file as text, or VwxFileError if it cannot be a CSV."""
    if upload.size > MAX_BYTES:
        raise VwxFileError('That file is over the 2 MB limit.')
    return decode(upload.read())


def decode(raw):
    if b'\x00' in raw:
        raise VwxFileError('That is not a CSV file.')
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('mac_roman')


def parse(text):
    """The file's cable rows. newline=None reads CR, LF and CRLF alike."""
    reader = csv.reader(io.StringIO(text, newline=None))
    rows = []
    try:
        header = next((cells for cells in reader if any(c.strip() for c in cells)), None)
        columns = _columns(header)
        for cells in reader:
            values = {name: cells[i].strip() for i, name in columns.items() if i < len(cells)}
            if _is_not_a_cable(values):
                continue
            rows.append(Row(line=reader.line_num, **values))
            if len(rows) > MAX_ROWS:
                raise VwxFileError('That file has more than {:,} rows.'.format(MAX_ROWS))
    except csv.Error:
        raise VwxFileError('That is not a CSV file.')
    if not rows:
        raise VwxFileError('That file has no cable rows.')
    return ParsedFile(rows, 'extension_of' in columns.values())


def _columns(header):
    columns = {}
    for index, title in enumerate(header or []):
        name = HEADERS.get(title.strip().lower())
        if name and name not in columns.values():
            columns[index] = name
    missing = [
        title for title, name in HEADERS.items()
        if name not in columns.values() and name not in OPTIONAL_HEADERS
    ]
    if missing:
        raise VwxFileError(
            'That file is not a ShowStack cable export. Missing column{}: {}.'.format(
                '' if len(missing) == 1 else 's', ', '.join(missing)))
    return columns


def _is_not_a_cable(values):
    """Blank rows and the worksheet's summary row: nothing but numbers. A real
    cable may be labelled 4, but its connector is a name."""
    return all(not value or _NUMBER.fullmatch(value) for value in values.values())


def whole_feet(value):
    """``value`` in whole feet, rounded up, or None if it is not a length."""
    feet = _feet(value)
    return None if feet is None else math.ceil(feet)


def _feet(value):
    if not _NUMBER.fullmatch(value or ''):
        return None
    feet = Decimal(value)
    return feet if 0 < feet <= MAX_FEET else None


def connector_cable(value):
    return CONNECTORS.get((value or '').strip().lower())


def fan_out_code(value):
    """The stored fan-out type for a name in the file, or None if unknown."""
    target = (value or '').strip().lower()
    if not target:
        return None
    for code, name in PACableSchedule.FAN_OUT_CHOICES:
        if code and name.lower() == target:
            return code
    return FAN_OUT_ALIASES.get(target)


def stock_length(feet):
    """The shortest extension stock that reaches ``feet``, or None."""
    lengths = sorted(value for value, _ in PAFanOutExtension.EXTENSION_LENGTH_CHOICES)
    return next((length for length in lengths if feet <= length), None)


def build_plan(parsed, project, filename):
    """What importing the file would do to ``project``. Writes nothing."""
    existing = {}
    entries = (PACableSchedule.objects.filter(project=project, label__isnull=False)
               .select_related('label').prefetch_related('fan_outs__extensions'))
    for entry in entries:
        existing.setdefault(entry.label.name, []).append(entry)

    plan = Plan(filename=filename, has_extension_column=parsed.has_extension_column)
    run_rows = [row for row in parsed.rows if not row.extension_of]
    label_counts = Counter(row.label for row in run_rows if row.label)
    by_label = {}
    for row in run_rows:
        run = _file_run(row, label_counts, existing.get(row.label, []))
        plan.runs.append(run)
        by_label.setdefault(row.label, run)

    for row in parsed.rows:
        if not row.extension_of:
            continue
        extension = _extension(row)
        run = by_label.get(row.extension_of)
        if run is None:
            matches = existing.get(row.extension_of, [])
            if not matches:
                extension.error = extension.error or (
                    'No run labelled "{}" in this file or project.'.format(row.extension_of))
                plan.orphans.append(extension)
                continue
            run = _project_run(row.extension_of, matches)
            by_label[row.extension_of] = run
            plan.runs.append(run)
        run.extensions.append(extension)

    for run in plan.runs:
        _settle_extensions(run, plan.has_extension_column)
    return plan


def _existing_problem(matches):
    """Why these entries, all carrying one label, cannot be updated, or ''."""
    if any(entry.entry_mode == 'linked' for entry in matches):
        return 'This label is on an entry linked to Soundvision / Amps. Rename one of them.'
    if len(matches) > 1:
        return '{} entries in this project share this label, so the one to update is unclear.'.format(len(matches))
    return ''


def _set_fans(run, entry):
    run.entry = entry
    run.fans = [fan for fan in entry.fan_outs.all() if fan.fan_out_type]


def _file_run(row, label_counts, matches):
    run = Run(label=row.label, action='update' if matches else 'new', row=row,
              destination=row.destination)
    if not row.label:
        run.errors.append('No Cable Label.')
    elif len(row.label) > PAZone._meta.get_field('name').max_length:
        run.errors.append('Cable Label is over {} characters.'.format(
            PAZone._meta.get_field('name').max_length))
    elif label_counts[row.label] > 1:
        run.errors.append('This label is on {} rows of the file. Labels must be unique.'.format(
            label_counts[row.label]))

    run.cable = connector_cable(row.connector) or ''
    if not run.cable:
        run.errors.append('Unknown Connector "{}".'.format(row.connector))
    run.feet = whole_feet(row.length) or 0
    if not run.feet:
        run.errors.append('Length "{}" is not a length in feet.'.format(row.length))
    if len(row.destination) > PACableSchedule._meta.get_field('destination').max_length:
        run.errors.append('Destination is over {} characters.'.format(
            PACableSchedule._meta.get_field('destination').max_length))
    if row.fan_out:
        run.fan_code = fan_out_code(row.fan_out) or ''
        if not run.fan_code:
            run.errors.append('Unknown Fan-Out "{}".'.format(row.fan_out))

    problem = _existing_problem(matches)
    if problem:
        run.errors.append(problem)
    elif matches:
        _set_fans(run, matches[0])
        if run.fan_code and len(run.fans) > 1:
            run.errors.append('This entry has {} fan-outs and the file describes one.'.format(len(run.fans)))

    if not row.destination:
        if matches and not problem and matches[0].destination:
            run.warnings.append('No Destination in the file. Keeps "{}".'.format(matches[0].destination))
        elif not matches or not problem:
            run.warnings.append('No Destination in the file.')
    if matches and not problem and not row.fan_out and run.fans:
        run.warnings.append('No Fan-Out in the file. Keeps {}.'.format(
            ', '.join(fan.get_fan_out_type_display() for fan in run.fans)))
    return run


def _project_run(label, matches):
    run = Run(label=label, action='extensions')
    problem = _existing_problem(matches)
    if problem:
        run.errors.append(problem)
    else:
        _set_fans(run, matches[0])
    return run


def _extension(row):
    extension = ExtensionRow(row=row)
    cable = connector_cable(row.connector)
    if cable not in EXTENSION_CABLES:
        extension.error = 'An extension must be NL4 or NL8, not "{}".'.format(row.connector)
        return extension
    extension.cable = EXTENSION_CABLES[cable]
    feet = _feet(row.length)
    if feet is None:
        extension.error = 'Length "{}" is not a length in feet.'.format(row.length)
        return extension
    extension.stock = stock_length(feet) or 0
    if not extension.stock:
        extension.error = "Length {} ft is longer than the longest extension.".format(row.length)
    return extension


def _settle_extensions(run, has_column):
    """Attach the run's extensions to its fan-out and decide whether the file
    replaces what the fan-out has."""
    for extension in run.extensions:
        if extension.error:
            continue
        if run.errors:
            extension.error = run.errors[0] if run.row is None else "This run's row has an error."
        elif not run.fan_code and not run.fans:
            extension.error = 'This run has no fan-out to attach to.'
        elif not run.fan_code and len(run.fans) > 1:
            extension.error = 'This run has {} fan-outs, so the one to extend is unclear.'.format(len(run.fans))

    if run.errors or not has_column or not (run.fan_code or run.extensions):
        return
    target = run.fan
    current = Counter()
    for stored in (target.extensions.all() if target else ()):
        current[(stored.extension_cable, stored.extension_length)] += stored.quantity

    if any(extension.error for extension in run.extensions):
        if current:
            run.warnings.append("An extension row failed, so this fan-out's extensions are left as they are.")
            return
    if not target and not run.fan_code:
        return
    run.groups = Counter((e.cable, e.stock) for e in run.extensions if not e.error)
    if current == run.groups:
        return
    run.replace_extensions = True
    if current:
        run.warnings.append('Replaces extensions on this fan-out: {}.'.format(
            ', '.join(_extension_text(key, qty) for key, qty in sorted(current.items()))))


def _extension_text(key, quantity):
    return "{} {}' x{}".format(key[0], key[1], quantity)


def digest(plan, project):
    """Fingerprint of the plan and of what it would change: the project, every
    planned value, and the stored values it was built against."""
    runs = []
    for run in plan.runs:
        entry = run.entry
        runs.append([
            run.row.line if run.row else None, run.label, run.action, run.cable, run.feet, run.destination,
            run.fan_code, sorted(run.groups.items()), run.replace_extensions, run.errors, run.warnings,
            [entry.pk, entry.cable, entry.length, entry.destination] if entry else None,
            [[fan.pk, fan.fan_out_type, fan.quantity,
              sorted((e.pk, e.extension_cable, e.extension_length, e.quantity) for e in fan.extensions.all())]
             for fan in run.fans],
            [[e.row.line, e.cable, e.stock, e.error] for e in run.extensions],
        ])
    state = [project.pk, plan.filename, runs, [[e.row.line, e.error] for e in plan.orphans]]
    return hashlib.sha256(json.dumps(state, default=str).encode()).hexdigest()


def apply_plan(plan, project):
    """Write the plan. The caller holds the transaction."""
    drawing_ref = plan.filename[:PACableSchedule._meta.get_field('drawing_ref').max_length]
    for run in plan.to_write:
        entry = run.entry
        if run.action == 'new':
            zone, _ = PAZone.objects.get_or_create(project=project, name=run.label)
            entry = PACableSchedule(project=project, label=zone, count=1, destination='',
                                    drawing_ref=drawing_ref)
        if run.action != 'extensions':
            entry.cable = run.cable
            entry.length = run.feet
            if run.destination:
                entry.destination = run.destination
            entry.save()

        fan = run.fan
        if run.fan_code:
            if fan is None:
                fan = PAFanOut.objects.create(cable_schedule=entry, fan_out_type=run.fan_code, quantity=1)
            elif fan.fan_out_type != run.fan_code or fan.quantity != 1:
                fan.fan_out_type = run.fan_code
                fan.quantity = 1
                fan.save()

        if run.replace_extensions:
            fan.extensions.all().delete()
            for (cable, stock), quantity in sorted(run.groups.items()):
                PAFanOutExtension.objects.create(
                    cable_schedule=entry, fan_out=fan, extension_cable=cable,
                    extension_length=stock, quantity=quantity,
                )
