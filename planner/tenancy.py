"""Tenant-scoping helpers shared by views, exports and admin classes.

Why a module instead of a decorator per view: the leaks this closes were all
the same two shapes, repeated across ~60 endpoints.

1. **No check at all.** An endpoint takes a raw ``assignment_id`` or
   ``config_id`` from the client and acts on it. Fixed with
   :func:`scoped_or_404`, which refuses to resolve an object outside the
   caller's accessible projects.

2. **A check that fails open.** The shape was::

       if request.current_project and obj.project != request.current_project:
           return deny()

   An anonymous request — or any request where the session carries no project —
   has no ``current_project``, so the comparison never runs and the object is
   served. :func:`current_project_or_deny` makes "no project" a refusal rather
   than a pass.

The authority on what a user may reach stays where it already was: ownership of
a :class:`~planner.models.Project`, or a
:class:`~planner.models.ProjectMember` row for it. ``CurrentProjectMiddleware``
already validates the session's project against that; these helpers apply the
same rule to object ids arriving in a URL or request body.

Superusers are not special-cased here. They are scoped to the project they have
selected in the switcher, exactly as ``BaseEquipmentAdmin.get_queryset``
already scopes them — they change projects with the dropdown rather than seeing
a merged view. The places where superusers genuinely do see everything are
listed in SECURITY_AUDIT.md.
"""

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404


def accessible_projects(user):
    """Projects ``user`` owns or is a member of.

    Returns an unevaluated queryset. Superusers get every project — this is the
    "can reach at all" question, not the "is currently looking at" question;
    callers that need the narrower one use :func:`current_project_or_deny`.
    """
    from planner.models import Project

    if not user or not user.is_authenticated:
        return Project.objects.none()
    if user.is_superuser:
        return Project.objects.all()
    return Project.objects.filter(
        Q(owner=user) | Q(projectmember__user=user)
    ).distinct()


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


def current_project_or_deny(request):
    """The request's current project, or ``PermissionDenied``.

    Use this wherever the old code wrote ``getattr(request, 'current_project',
    None)`` and then only checked the project *if it was set*. Having no
    project must mean "you see nothing", never "you skip the check".
    """
    project = getattr(request, 'current_project', None)
    if project is None:
        raise PermissionDenied('No project selected.')
    if not can_access_project(request.user, project):
        raise PermissionDenied('Project not accessible.')
    return project


def current_project_or_none(request):
    """The request's current project if the user may access it, else ``None``.

    For the JSON endpoints that wrap their whole body in
    ``try: ... except Model.DoesNotExist: 404 / except Exception: 500``. Raising
    from inside one of those is useless — the generic handler swallows it into a
    500 — so instead the caller folds this value straight into the lookup::

        pl = CommConfigPartyline.objects.get(
            id=data['partyline_id'], config__project=_project(request),
        )

    ``project=None`` becomes ``project__isnull=True`` in SQL, which matches no
    row (every one of these models has a non-null project), so a missing or
    inaccessible project yields ``DoesNotExist`` → the endpoint's existing 404.
    Fail-closed by construction, and no restructuring of the handlers.

    The rule this encodes: **never make the filter itself conditional.** The
    original bugs were all ``if project: filter(...)`` with no ``else``.
    """
    project = getattr(request, 'current_project', None)
    if project is None or not can_access_project(request.user, project):
        return None
    return project


def scoped_or_404(request, model, lookup_path='project', **lookup):
    """``get_object_or_404`` that cannot escape the current project.

    ``lookup_path`` is the ORM path from ``model`` to its Project, so child
    models reach theirs through their parent::

        scoped_or_404(request, MicAssignment, 'session__day__project', id=pk)
        scoped_or_404(request, CommConfigPartyline, 'config__project', id=pk)

    Raises :class:`~django.http.Http404` for an id outside the current project —
    deliberately the same response as a genuinely missing row, so the endpoint
    does not confirm that someone else's id exists.
    """
    project = current_project_or_deny(request)
    try:
        return model.objects.get(**{lookup_path: project}, **lookup)
    except model.DoesNotExist:
        raise Http404(f'No {model.__name__} matches the given query.')
    except (ValueError, TypeError):
        # A non-numeric id from a hand-rolled request body.
        raise Http404(f'No {model.__name__} matches the given query.')


def scope_queryset(request, queryset, lookup_path='project'):
    """Narrow ``queryset`` to the current project, or to nothing.

    The "or to nothing" half is the point: every call site this replaces had an
    ``else`` branch that returned the unfiltered queryset.
    """
    project = getattr(request, 'current_project', None)
    if project is None or not can_access_project(request.user, project):
        return queryset.none()
    return queryset.filter(**{lookup_path: project})


def project_scoped_fk_queryset(request, queryset, lookup_path='project'):
    """``scope_queryset`` for a dropdown.

    Separate name because the intent at an admin ``formfield_for_foreignkey``
    call site is "what may this user select", and a reader should not have to
    work out that an empty queryset is deliberate.
    """
    return scope_queryset(request, queryset, lookup_path)
