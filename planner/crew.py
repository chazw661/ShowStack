"""Auto-claim helper: rebind pending CrewMember rows on user registration.

When a new user registers, this helper:
  1. Finds CrewMember rows with user__isnull=True whose email matches the new
     user's email case-insensitively (D-08: __iexact + explicit .strip()).
  2. UPDATES each match in place — sets email=None, user=<new user>, save with
     update_fields=['user', 'email']. Preserves default_role + added_at
     (D-01 — single-table polymorphic rebind, no row delete+recreate).
  3. For every CrewProjectAdd of the matched crew, creates a ProjectMember
     row for the new user via get_or_create (idempotent). Skips rows that
     already exist (e.g. the user was previously added directly).
  4. Returns the list of newly-created ProjectMember rows so the caller can
     send confirmation emails (SPEC R4 / R6).

Called from accounts/views.py:register() per D-07 — inside a transaction.atomic
block per D-11. NO Django signals (D-07) — register() is the single, visible,
testable entry point.

Phase 6 — SPEC-06-R06.
"""
import logging

from django.db import transaction

from planner.models import CrewMember, CrewProjectAdd, ProjectMember

logger = logging.getLogger(__name__)


def claim_pending_crew_memberships(user):
    """Rebind pending CrewMember rows and materialize ProjectMember rows for the new user.

    Args:
        user: A freshly-saved auth User instance.

    Returns:
        list[ProjectMember]: Newly-created ProjectMember rows. The caller is
        expected to send a confirmation email per row (D-10: log + swallow
        send failures).

    D-08: Case-insensitive via __iexact. Explicit .strip() on the user-side
    value before passing to filter() — NO gmail dot normalization, NO
    +alias collapsing (too surprising for users who legitimately use plus
    addressing).

    D-11: Caller wraps form.save() + this call in a single transaction.atomic.
    This helper opens its own inner transaction defensively so partial state
    cannot leak if the caller forgets the outer wrap.
    """
    normalized = (user.email or '').strip()
    if not normalized:
        return []

    pending = list(
        CrewMember.objects.filter(
            user__isnull=True,
            email__iexact=normalized,
        ).select_related('crew')
    )
    if not pending:
        return []

    new_memberships = []

    with transaction.atomic():
        for cm in pending:
            # Step 1 (D-01): UPDATE IN PLACE — preserves default_role + added_at.
            cm.user = user
            cm.email = None
            cm.save(update_fields=['user', 'email'])

            # Step 2 (D-09): materialize ProjectMember rows for every project
            # this crew has been bulk-added to.
            for cpa in CrewProjectAdd.objects.filter(crew=cm.crew).select_related('project'):
                pm, created = ProjectMember.objects.get_or_create(
                    project=cpa.project,
                    user=user,
                    defaults={
                        'role': cm.default_role,
                        'invited_by': cm.crew.owner,
                    },
                )
                if created:
                    new_memberships.append(pm)

    return new_memberships
