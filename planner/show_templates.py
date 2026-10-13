"""Save a console into a ShowTemplate, and load one back into a project.

Kept out of admin.py so the admin action, the library view and the
``migrate_console_templates`` command all copy through the same code.

Fields are copied by introspection rather than by naming them. The import
this replaces named its fields by hand and silently dropped every one added
after it was written (source_b, source_hardware, color, default_record, the
stereo outputs, the location). ``test_show_templates`` asserts each
Console* field has a mirror on its Template* model, so a new field either
lands in templates automatically or fails a test -- it cannot vanish.

Loading ALWAYS ADDS. It never deletes, overwrites or merges into an
existing console. A name that is already taken in the target project is
reported by :func:`preview_load` with a suggested rename, and
:func:`apply_load` refuses to run until every name is free.
"""

from django.db import transaction

from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput,
    ConsoleStereoOutput, Location, Project, ShowTemplate, TemplateConsole,
    TemplateConsoleAux, TemplateConsoleInput, TemplateConsoleMatrix,
    TemplateConsoleStereo,
)

CONSOLE_PAYLOAD_VERSION = 1

# (live model, template mirror, live reverse accessor, template related_name,
#  order_by for the live rows)
CONSOLE_CHILDREN = [
    (ConsoleInput, TemplateConsoleInput, 'consoleinput_set', 'inputs', 'id'),
    (ConsoleAuxOutput, TemplateConsoleAux, 'consoleauxoutput_set', 'auxes', 'id'),
    (ConsoleMatrixOutput, TemplateConsoleMatrix, 'consolematrixoutput_set', 'matrices', 'id'),
    (ConsoleStereoOutput, TemplateConsoleStereo, 'consolestereooutput_set', 'stereos', 'id'),
]

# Console fields that are not copied as-is: project and location are
# re-resolved in the target, is_template is the legacy flag this replaces.
CONSOLE_NON_COPIED = {'id', 'project', 'location', 'is_template'}


def copied_fields(model, skip=('id', 'console')):
    """Concrete field names copied between a live row and its template mirror."""
    return [
        f.name for f in model._meta.concrete_fields
        if f.name not in skip and not f.primary_key
    ]


def console_fields():
    return copied_fields(Console, skip=CONSOLE_NON_COPIED)


def _truncate_for(model, field, value):
    max_length = model._meta.get_field(field).max_length
    return value[:max_length] if max_length else value


def unique_template_name(owner, kind, base, alternate=None, taken=None):
    """A name for ``owner``'s ``kind`` template that is not in use yet.

    Tries ``base``, then ``alternate`` (e.g. "PM10 (Tour 2025)"), then
    numbered variants of whichever was tried last. ``taken`` lets a caller
    reserve names it has planned but not written yet -- the migration
    command's dry run.
    """
    used = set(
        ShowTemplate.objects.filter(owner=owner, kind=kind)
        .values_list('name', flat=True)
    )
    if taken:
        used |= taken
    limit = ShowTemplate._meta.get_field('name').max_length

    candidates = [base] + ([alternate] if alternate else [])
    for candidate in candidates:
        candidate = candidate[:limit]
        if candidate not in used:
            return candidate
    stem = candidates[-1]
    n = 2
    while True:
        suffix = f" ({n})"
        candidate = stem[:limit - len(suffix)] + suffix
        if candidate not in used:
            return candidate
        n += 1


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def _snapshot_console(template, console):
    data = {f: getattr(console, f) for f in console_fields()}
    tc = TemplateConsole.objects.create(
        template=template,
        location_name=console.location.name if console.location_id else '',
        **data,
    )
    for live_model, mirror, live_accessor, _, order in CONSOLE_CHILDREN:
        fields = copied_fields(live_model)
        mirror.objects.bulk_create([
            mirror(console=tc, **{f: getattr(row, f) for f in fields})
            for row in getattr(console, live_accessor).order_by(order)
        ])
    return tc


def save_console_template(console, owner, name, notes=''):
    """Snapshot ``console`` into a new ShowTemplate owned by ``owner``."""
    with transaction.atomic():
        template = ShowTemplate.objects.create(
            owner=owner,
            kind=ShowTemplate.KIND_CONSOLE,
            name=name,
            payload_version=CONSOLE_PAYLOAD_VERSION,
            source_project=console.project,
            notes=notes,
        )
        _snapshot_console(template, console)
    return template


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _suggest(name, used):
    limit = Console._meta.get_field('name').max_length
    n = 2
    while True:
        suffix = f" ({n})"
        candidate = name[:limit - len(suffix)] + suffix
        if candidate not in used:
            return candidate
        n += 1


def preview_load(template, project):
    """What loading ``template`` into ``project`` would create.

    Returns one entry per template console::

        {'id': <TemplateConsole id>, 'name': 'FOH', 'collides': True,
         'suggested': 'FOH (2)', 'location_name': 'FOH',
         'location_exists': True, 'counts': {...}}

    Suggestions avoid both the project's consoles and each other, so
    accepting every suggestion is always a valid rename map.
    """
    used = set(Console.objects.filter(project=project).values_list('name', flat=True))
    existing_locations = set(
        Location.objects.filter(project=project).values_list('name', flat=True)
    )
    plan = []
    for tc in template.consoles.all():
        collides = tc.name in used
        suggested = _suggest(tc.name, used) if collides else tc.name
        used.add(suggested)
        plan.append({
            'id': tc.id,
            'name': tc.name,
            'collides': collides,
            'suggested': suggested,
            'location_name': tc.location_name,
            'location_exists': (
                not tc.location_name or tc.location_name in existing_locations
            ),
            'counts': {
                related: getattr(tc, related).count()
                for _, _, _, related, _ in CONSOLE_CHILDREN
            },
        })
    return plan


class LoadConflict(Exception):
    """A rename map that would still collide, or is otherwise unusable.

    ``errors`` maps TemplateConsole id -> message.
    """

    def __init__(self, errors):
        super().__init__('; '.join(errors.values()))
        self.errors = errors


def _resolve_location(project, name):
    if not name:
        return None
    # Location has no unique (project, name), so a project may already hold
    # two with this name. get_or_create would raise MultipleObjectsReturned
    # there; take the first in display order instead.
    existing = (
        Location.objects.filter(project=project, name=name)
        .order_by('sort_order', 'id').first()
    )
    if existing:
        return existing
    return Location.objects.create(project=project, name=name)


def apply_load(template, project, renames=None):
    """Add the template's consoles to ``project``. Returns the new consoles.

    ``renames`` maps TemplateConsole id -> the console name to use. A console
    not in the map keeps its template name. Every final name must be free in
    the project and distinct from the others, or :class:`LoadConflict` is
    raised and nothing is written.

    One transaction, with the project row locked so two loads racing into
    the same project cannot both pass the collision check.
    """
    renames = {int(k): v for k, v in (renames or {}).items()}
    limit = Console._meta.get_field('name').max_length

    with transaction.atomic():
        Project.objects.select_for_update().filter(pk=project.pk).first()

        used = set(Console.objects.filter(project=project).values_list('name', flat=True))
        consoles = list(template.consoles.all())
        errors = {}
        final = {}
        for tc in consoles:
            name = (renames.get(tc.id, tc.name) or '').strip()
            if not name:
                errors[tc.id] = f"'{tc.name}' needs a name."
            elif len(name) > limit:
                errors[tc.id] = f"'{name}' is longer than {limit} characters."
            elif name in used:
                errors[tc.id] = f"A console called '{name}' already exists in this project."
            else:
                used.add(name)
                final[tc.id] = name
        if errors:
            raise LoadConflict(errors)

        created = []
        for tc in consoles:
            console = Console.objects.create(
                project=project,
                location=_resolve_location(project, tc.location_name),
                **{f: (final[tc.id] if f == 'name' else getattr(tc, f))
                   for f in console_fields()},
            )
            for live_model, mirror, live_accessor, related, _ in CONSOLE_CHILDREN:
                fields = copied_fields(live_model)
                live_model.objects.bulk_create([
                    live_model(console=console, **{f: getattr(row, f) for f in fields})
                    for row in getattr(tc, related).order_by('id')
                ])
            created.append(console)
    return created


def annotate_console_counts(queryset):
    """Add n_consoles / n_inputs / n_auxes / n_matrices /
    n_stereos to a ShowTemplate queryset.

    Correlated subqueries rather than Count() over joins: four one-to-many
    joins multiply (48 inputs x 24 auxes x 8 matrices x 3 stereos is 27,648
    rows for ONE template before DISTINCT collapses them).
    """
    from django.db.models import Count, IntegerField, OuterRef, Subquery
    from django.db.models.functions import Coalesce

    def count_of(model):
        sub = (
            model.objects.filter(console__template=OuterRef('pk'))
            .order_by().values('console__template')
            .annotate(n=Count('pk')).values('n')
        )
        return Coalesce(Subquery(sub, output_field=IntegerField()), 0)

    consoles = (
        TemplateConsole.objects.filter(template=OuterRef('pk'))
        .order_by().values('template').annotate(n=Count('pk')).values('n')
    )
    return queryset.annotate(
        n_consoles=Coalesce(Subquery(consoles, output_field=IntegerField()), 0),
        n_inputs=count_of(TemplateConsoleInput),
        n_auxes=count_of(TemplateConsoleAux),
        n_matrices=count_of(TemplateConsoleMatrix),
        n_stereos=count_of(TemplateConsoleStereo),
    )
