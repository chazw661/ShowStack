"""Read-only: which Console-page Patch cells read differently after the
B-patch change (PR #219), because Source (B) text stopped taking part in
name matching.

Before, a channel's Source (B) was a name an unlinked port could match: it
made "B" feeds by name, and it made an A name *ambiguous* when the same text
was another channel's Source (B) -- on this console or another one. After,
only A names (Source) are matched, so such a port reads *by name* on the one
channel whose A name it is, and no B feed is ever found by name.

For every non-template console this prints each channel whose A patch reads
differently, before -> after (the text the console PDF prints), and, with
``--b``, the by-name B feeds that are no longer shown. Nothing is written;
there is no --apply.

It reads only columns that exist before migration 0237, so it runs against a
restore of production at main's schema without migrating it::

    DATABASE_URL=postgres://localhost/showstack_restore \\
        ./venv/bin/python manage.py report_patch_by_name_changes [--project N] [--b]

"Before" is main's matching, copied verbatim below (``_before``); "after" is
this branch's own ``PortIndex.inputs_for``. Ports are loaded once per project
without the B column (B is blank everywhere until someone sets one, so it
changes no A cell).
"""
from itertools import groupby

from django.core.management.base import BaseCommand

from planner.models import Console, DeviceInput, Project
from planner.utils.console_patch import (
    AMBIGUOUS, BY_NAME, LINKED, Cell, Feed, Port, PortIndex, _linked, _ORDER, feed_label,
)
from planner.utils.device_patch import norm


def _ports(project_id):
    """PortIndex.inputs as main built it: no B column."""
    rows = (DeviceInput.objects
            .filter(device__project_id=project_id, input_number__isnull=False)
            .order_by('device__name', 'device_id', 'input_number', 'pk')
            .values_list('device_id', 'device__name', 'signal_name',
                         'console_input__console_id', 'console_input_id', 'pk'))
    ports = []
    for _, device_rows in groupby(rows, key=lambda r: r[0]):
        for number, (device_id, device_name, name, ct_id, pk, row_pk) in enumerate(device_rows, 1):
            ports.append(Port(device_id, device_name, number, (name or '').strip(),
                              (ct_id, pk) if pk else None, row_pk))
    return ports


def _before_input_names(project_id):
    """main's PortIndex.input_names: A and B names on every console."""
    from planner.models import ConsoleInput
    rows = (ConsoleInput.objects
            .filter(console__project_id=project_id, console__is_template=False)
            .values_list('console_id', 'console__name', 'source', 'source_b'))
    names = {}
    for console_id, console_name, *values in rows:
        for value in values:
            if norm(value):
                names.setdefault(norm(value), {})[console_id] = console_name
    return names


def _before(ports, input_names, channels):
    """main's PortIndex.inputs_for, verbatim but for its inputs."""
    channels = [c for c in channels if c.pk]
    if not channels:
        return {}
    console = channels[0].console
    cells = {c.pk: Cell() for c in channels}
    saved = {c.pk: c.source for c in channels}
    labels = {c.pk: f'ch {c.input_ch}' for c in channels}
    by_name = {}  # name -> {channel pk: slot}; A wins over B on one channel
    for c in channels:
        for value, slot in ((c.source_b, 'B'), (c.source, 'A')):
            if norm(value):
                by_name.setdefault(norm(value), {})[c.pk] = slot

    for port in ports:
        if port.link:
            if port.link[1] in cells:
                cells[port.link[1]].feeds.append(_linked(port, saved[port.link[1]]))
            continue
        hits = by_name.get(norm(port.name), {})
        if not hits:
            continue
        consoles = PortIndex._other_consoles(input_names, port.name, console.pk)
        if consoles:
            others = tuple(sorted([console.name, *consoles], key=str.casefold))
            for pk, slot in hits.items():
                cells[pk].feeds.append(Feed(port, AMBIGUOUS, slot, others=others, across=True))
        elif len(hits) == 1:
            (pk, slot), = hits.items()
            cells[pk].feeds.append(Feed(port, BY_NAME, slot))
        else:
            others = tuple(labels[pk] for pk in hits)
            for pk, slot in hits.items():
                cells[pk].feeds.append(Feed(port, AMBIGUOUS, slot, others=others))

    for cell in cells.values():
        cell.feeds.sort(key=lambda f: (f.slot, _ORDER[f.how], f.port.device_name, f.port.number))
        for slot in ('A', 'B'):
            linked = [f for f in cell.feeds if f.slot == slot and f.how == LINKED]
            if len(linked) > 1:
                for f in linked:
                    f.conflict = True
    return cells


def _texts(cell, slot):
    return [feed_label(f, 'In') for f in (cell.feeds if cell else ()) if f.slot == slot]


def changes(project):
    """[(console, channel, before A texts, after A texts, lost B texts)] for
    every channel whose A cell differs or that loses a by-name B feed."""
    ports = _ports(project.pk)
    names_before = _before_input_names(project.pk)
    after_index = PortIndex(project.pk)
    after_index.__dict__['inputs'] = ports      # the same ports, no B column read
    out = []
    for console in (Console.objects.filter(project=project, is_template=False)
                    .order_by('name', 'pk')):
        channels = list(console.consoleinput_set.all())
        for c in channels:
            c.console = console
        before = _before(ports, names_before, channels)
        after = after_index.inputs_for(channels)
        for c in sorted(channels, key=lambda c: (_num(c.input_ch), c.pk)):
            a_before, a_after = _texts(before.get(c.pk), 'A'), _texts(after.get(c.pk), 'A')
            b_lost = _texts(before.get(c.pk), 'B')
            if a_before != a_after or b_lost:
                out.append((console, c, a_before, a_after, b_lost))
    return out


def _num(value):
    text = (value or '').strip()
    return (0, int(text), '') if text.isdigit() else (1, 0, text)


class Command(BaseCommand):
    help = ('Read-only. List Console-page Patch cells whose A patch reads differently '
            'now that Source (B) no longer takes part in name matching (PR #219).')

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, help='Only this project id.')
        parser.add_argument('--b', action='store_true',
                            help='Also list the by-name B feeds that are no longer shown.')

    def handle(self, *args, project=None, b=False, **options):
        projects = Project.objects.order_by('pk')
        if project:
            projects = projects.filter(pk=project)
        total_a = total_b = 0
        for p in projects:
            rows = changes(p)
            a_rows = [r for r in rows if r[2] != r[3]]
            b_rows = [r for r in rows if r[4]]
            total_a += len(a_rows)
            total_b += len(b_rows)
            if not a_rows and not (b and b_rows):
                continue
            self.stdout.write(f'\nProject {p.pk}: {p.name}')
            for console, c, before, after, _ in a_rows:
                self.stdout.write(f'  {console.name} ch {c.input_ch} "{(c.source or "").strip()}"')
                self.stdout.write(f'    before: {" | ".join(before) or "(blank)"}')
                self.stdout.write(f'    after:  {" | ".join(after) or "(blank)"}')
            if b:
                for console, c, _, _, lost in b_rows:
                    self.stdout.write(f'  {console.name} ch {c.input_ch} B no longer shown: '
                                      f'{" | ".join(lost)}')
        self.stdout.write(f'\n{total_a} channel(s) whose A patch reads differently; '
                          f'{total_b} channel(s) losing a by-name B feed'
                          f'{"" if b else " (list them with --b)"}. Nothing was written.')
