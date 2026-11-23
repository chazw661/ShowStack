"""What the input pickers list, shared by both (wiring diagram, PR 2b-2 / 2b-3).

``amp_sources`` (amp channel inputs) and ``processor_sources`` (P1 / Galaxy
AES and Analog inputs) each build their ``Source`` list; this module makes
every entry pickable and keeps linked text current.

Two sources that would read the same are lengthened, never left out: first
the owner's location ("(Stage Left)"), then its IP ("(Stage Left, 10.0.0.5)").
Two still alike after that read "(duplicate device)": that text names no one
output, so picking it links nothing, and ``duplicate_warnings`` lists the
devices for the Warnings panel so the engineer can fix the data.

A linked input's text is a copy of its source's entry. ``changed(project)``
is called by the signals whenever something an entry reads is saved or
deleted; it rewrites every linked text of the project that no longer reads as
its source's entry does now -- the whole project, because a rename can
lengthen or shorten an entry that was not the one renamed. With nothing
linked it costs one query. Inside ``batched()`` (a device save that adds its
outputs one by one, a project copy) the rewrite runs once, at the end.
"""
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, replace

DUPLICATE_SUFFIX = ' (duplicate device)'


@dataclass(frozen=True)
class Source:
    model: str          # 'p1output' / 'deviceoutput' / 'consolematrixoutput' ...
    pk: int
    field: str          # the input field it can feed ('' when it feeds every one)
    text: str           # its datalist entry, and what the field stores when linked
    group: str = ''     # the datalist header: its device / console / processor
    owner: tuple = ()   # ('device', pk): what a duplicate warning names
    location: str = ''
    ip: str = ''
    duplicate: bool = False
    network: str = ''   # comm pickers: its Dante network, when not the picking device's

    @property
    def key(self):
        return (self.model, self.pk)


def _clashes(sources):
    """Indexes of sources whose (field, text) another source also reads."""
    seen = defaultdict(set)
    for s in sources:
        seen[(s.field, s.text)].add(s.key)
    return {i for i, s in enumerate(sources) if len(seen[(s.field, s.text)]) > 1}


def disambiguate(sources):
    """Every source with a text of its own, or marked a duplicate."""
    base = [s.text for s in sources]
    out = list(sources)
    for parts in (lambda s: [s.location], lambda s: [s.location, s.ip]):
        clash = _clashes(out)
        if not clash:
            return out
        for i in clash:
            extra = ', '.join(p for p in parts(out[i]) if p)
            out[i] = replace(out[i], text=f'{base[i]} ({extra})' if extra else base[i])
    for i in _clashes(out):
        out[i] = replace(out[i], text=base[i] + DUPLICATE_SUFFIX, duplicate=True)
    return out


def picker(sources, max_length):
    """{field: {entry text: Source}} -- every entry naming exactly one output
    and short enough to store (``max_length(field)``), in list order."""
    out = defaultdict(dict)
    for s in sources:
        if not s.duplicate and len(s.text) <= max_length(s.field):
            out[s.field][s.text] = s
    return out


def listing(sources, field, max_length):
    """The datalist for ``field``: every entry once, duplicates included (they
    pick nothing, but are listed so nothing vanishes from the list)."""
    seen, out = set(), []
    for s in sources:
        if s.field == field and s.text not in seen and len(s.text) <= max_length:
            seen.add(s.text)
            out.append(s)
    return out


def duplicate_warnings(sources):
    """[(title, [owner names])], one per set of devices that read the same."""
    names = {}
    by_text = defaultdict(set)
    for s in sources:
        if s.duplicate:
            by_text[(s.field, s.text)].add(s.owner)
            label = s.group + (f' ({s.location})' if s.location else '')
            names[s.owner] = label
    sets = sorted({frozenset(owners) for owners in by_text.values()},
                  key=lambda o: sorted(names[x] for x in o))
    return [sorted(names[o] for o in owners) for owners in sets]


# -- keeping linked text current ----------------------------------------------

_state = threading.local()


@contextmanager
def batched():
    """Hold ``changed`` calls until the outermost block ends, then rewrite
    each project once."""
    depth = getattr(_state, 'depth', 0)
    if depth == 0:
        _state.pending = set()
    _state.depth = depth + 1
    try:
        yield
    finally:
        _state.depth -= 1
        if _state.depth == 0:
            pending, _state.pending = _state.pending, set()
            for project_id in sorted(pending):
                refresh_linked_text(project_id)


def changed(project_id):
    """Something a picker entry reads changed in this project."""
    if project_id is None:
        return
    if getattr(_state, 'depth', 0):
        _state.pending.add(project_id)
    else:
        refresh_linked_text(project_id)


def refresh_linked_text(project_id):
    """Rewrite every linked input of the project whose text is not its
    source's entry as it reads now. Returns how many fields changed."""
    from planner.connections import amp_sources, processor_sources
    from planner.models import Connection, Project
    rows = list(Connection.objects.filter(project_id=project_id)
                .values_list('from_ct_id', 'from_id', 'to_ct_id', 'to_id', 'transport'))
    if not rows:
        return 0
    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return 0
    return (amp_sources.rewrite(project, rows) + processor_sources.rewrite(project, rows))
