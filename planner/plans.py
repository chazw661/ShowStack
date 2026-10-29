"""Plan tier: what an account may do, as opposed to what it may do on a
project (that is the role; see planner.tenancy).

The tier is ``UserProfile.account_type`` (super_user / beta / paid / free).
The only thing it decides is whether the account may create a project: a
free account never creates one, but invited onto someone else's project it
has that role's full rights. A free account that already owns a project
(from before this rule) keeps an owner's full rights on it; it just can't
create another. Keep the two questions apart --
never read a role from the tier, nor a tier from the Editor/Viewer groups.
"""

# 'super_user' is a label on the profile, not Django's is_superuser (which
# may always create).
CREATOR_ACCOUNT_TYPES = ('super_user', 'paid', 'beta')


def account_type(user):
    profile = getattr(user, 'userprofile', None)
    return profile.account_type if profile is not None else 'free'


def can_create_projects(user):
    """True if ``user`` may create (and so own) a project, by any path: the
    add form, duplicating a project, or anything added later."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return account_type(user) in CREATOR_ACCOUNT_TYPES
