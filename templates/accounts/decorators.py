# accounts/decorators.py
"""
Permission decorators for ShowStack project access control.

Roles:
- owner: Project creator, full CRUD access
- editor: Can view and edit existing equipment (no create/delete)
- viewer: Read-only access to all equipment
"""

from functools import wraps
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from planner.models import Project, ProjectMember


def project_access_required(allowed_roles=None):
    """
    Decorator to check if user has access to a project with specified role(s).
    
    Usage:
        @project_access_required(allowed_roles=['owner', 'editor', 'viewer'])
        def my_view(request, project_id, **kwargs):
            project = kwargs['project']
            access_level = kwargs['access_level']
            can_edit = kwargs['can_edit']
            can_create = kwargs['can_create']
            can_delete = kwargs['can_delete']
            # ... view logic
    
    Args:
        allowed_roles: List of roles allowed to access this view.
                      Defaults to ['owner', 'editor', 'viewer'] (all roles).
    
    Adds to kwargs:
        - project: The Project instance
        - access_level: User's role ('owner', 'editor', or 'viewer')
        - can_edit: Boolean, True if user can edit (owner or editor)
        - can_create: Boolean, True if user can create (owner only)
        - can_delete: Boolean, True if user can delete (owner only)
        - can_invite: Boolean, True if user can invite (owner only)
        - is_readonly: Boolean, True if viewer (for templates)
    """
    if allowed_roles is None:
        allowed_roles = ['owner', 'editor', 'viewer']
    
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, project_id, *args, **kwargs):
            # Get the project
            project = get_object_or_404(Project, id=project_id)
            
            # Check if user is the owner
            is_owner = project.owner == request.user
            
            # Check if user is a member
            user_role = None
            if not is_owner:
                try:
                    membership = ProjectMember.objects.get(
                        project=project, 
                        user=request.user
                    )
                    user_role = membership.role
                except ProjectMember.DoesNotExist:
                    user_role = None
            
            # Determine access level
            if is_owner:
                access_level = 'owner'
            elif user_role:
                access_level = user_role
            else:
                # User has no access to this project
                messages.error(
                    request, 
                    'You do not have access to this project.'
                )
                return redirect('dashboard')
            
            # Check if user's role is in the allowed list
            if access_level not in allowed_roles:
                messages.error(
                    request, 
                    f'You need {" or ".join(allowed_roles)} access for this action.'
                )
                return redirect('project_detail', project_id=project.id)
            
            # Add permission flags to kwargs
            kwargs['project'] = project
            kwargs['access_level'] = access_level
            kwargs['can_edit'] = access_level in ['owner', 'editor']
            kwargs['can_create'] = access_level == 'owner'
            kwargs['can_delete'] = access_level == 'owner'
            kwargs['can_invite'] = access_level == 'owner'
            kwargs['is_readonly'] = access_level == 'viewer'
            
            return view_func(request, project_id, *args, **kwargs)
        return wrapper
    return decorator


def owner_required(view_func):
    """
    Shortcut decorator for views that require owner access only.
    
    Usage:
        @owner_required
        def delete_equipment(request, project_id, **kwargs):
            # Only owners can access this view
            pass
    """
    return project_access_required(allowed_roles=['owner'])(view_func)


def editor_or_owner_required(view_func):
    """
    Shortcut decorator for views that require editor or owner access.
    
    Usage:
        @editor_or_owner_required
        def edit_equipment(request, project_id, **kwargs):
            # Owners and editors can access, viewers cannot
            pass
    """
    return project_access_required(allowed_roles=['owner', 'editor'])(view_func)