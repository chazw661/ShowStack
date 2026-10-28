"""Tenant-scoping helpers shared by views and exports.

Why a module instead of a fix per view: the leaks this closes were all the
same two shapes, repeated across ~60 endpoints.

1. **No check at all.** An endpoint takes a raw ``assignment_id`` or
   ``config_id`` from the client and acts on it.

2. **A check that fails open.** The shape was::

       if request.current_project and obj.project != request.current_project:
           return deny()

   An anonymous request -- or any request whose session carries no project --
   has no ``current_project``, so the comparison never runs and the object is
   served. That is how ``device_pdf_export`` handed out any tenant's I/O patch.

Both collapse into one rule: **never make the filter itself conditional.**
:func:`current_project_or_none` and :func:`scope_queryset` exist to make
following that rule shorter than breaking it.

The authority on what a user may reach stays where it already was: ownership
of a :class:`~planner.models.Project`, or a
:class:`~planner.models.ProjectMember` row for it.
``CurrentProjectMiddleware`` validates the session's project against that;
these helpers apply the same rule to object ids arriving in a URL or body.

Superusers are not special-cased. They are scoped to the project selected in
the switcher, exactly as ``BaseEquipmentAdmin.get_queryset`` already scopes
them -- they change projects with the dropdown rather than seeing a merged
view. Where superusers genuinely do see everything is listed in
SECURITY_AUDIT.md.
"""


def can_access_project(user, project):
    """True if ``user`` owns ``project`` or holds a ProjectMember row for it."""
    from planner.models import ProjectMember

    if project is None or not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if project.owner_id == user.id:
        return True
    return ProjectMember.objects.filter(user=user, project=project).exists()


def can_edit_project(user, project):
    """True if ``user`` may change ``project``: superuser, its owner, or an
    'editor' member. Viewers may not. The per-project role only: the global
    'Viewer' group says nothing about this project."""
    from planner.models import ProjectMember

    if project is None or not user or not user.is_authenticated:
        return False
    if user.is_superuser or project.owner_id == user.id:
        return True
    return ProjectMember.objects.filter(user=user, project=project, role='editor').exists()


def can_edit_current_project(request):
    return can_edit_project(request.user, getattr(request, 'current_project', None))


def edit_rights_required(view):
    """JSON 403 unless the user may edit the current project, checked before
    the view reads anything: a viewer's request is refused whatever it holds.
    For the fetch() endpoints; edit_rights_required_page is the page one."""
    from functools import wraps
    from django.http import JsonResponse

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_edit_current_project(request):
            return JsonResponse({'error': 'Read-only access.'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def edit_rights_required_page(view):
    """As edit_rights_required, for a page or form: the 403 page."""
    from functools import wraps
    from django.core.exceptions import PermissionDenied

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_edit_current_project(request):
            raise PermissionDenied('Read-only access.')
        return view(request, *args, **kwargs)
    return wrapped


def current_project_or_none(request):
    """The request's current project if the user may access it, else ``None``.

    For the JSON endpoints that wrap their whole body in
    ``try: ... except Model.DoesNotExist: 404 / except Exception: 500``.
    Raising from inside one of those is useless -- the generic handler
    swallows it into a 500 -- so the caller folds this value straight into the
    lookup instead::

        pl = CommConfigPartyline.objects.get(
            id=data['partyline_id'], config__project=_scoped_project(request),
        )

    ``project=None`` becomes ``project__isnull=True`` in SQL, which matches no
    row (every one of these models has a non-null project), so a missing or
    inaccessible project yields ``DoesNotExist`` -> the endpoint's existing
    404. Fail-closed by construction, and no restructuring of the handlers.

    Passing the result into the filter is the whole point. Branching on it --
    ``if project: filter(...)`` with no ``else`` -- is the bug this replaces.
    """
    project = getattr(request, 'current_project', None)
    if project is None or not can_access_project(request.user, project):
        return None
    return project


def scope_queryset(request, queryset, lookup_path='project'):
    """Narrow ``queryset`` to the current project, or to nothing.

    The "or to nothing" half is the point: every call site this replaces had
    an ``else`` branch that returned the queryset unfiltered.

    ``lookup_path`` is the ORM path from the queryset's model to its Project,
    so child models reach theirs through their parent --
    ``scope_queryset(request, qs, 'session__day__project')``.
    """
    project = current_project_or_none(request)
    if project is None:
        return queryset.none()
    return queryset.filter(**{lookup_path: project})


def owned_templates(request, queryset):
    """Narrow a ShowTemplate ``queryset`` to what ``request.user`` owns.

    Templates live outside projects, so the current-project rule above does
    not apply: the boundary is the owner. Anonymous -> nothing, superuser ->
    everything (support copies a template between tenants), anyone else ->
    their own. Every list, load, rename and delete of a template goes through
    here, so there is one place where "whose template is this" is decided.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    return queryset.filter(owner=user)
