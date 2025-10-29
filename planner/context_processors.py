"""
Context processors for ShowStack admin interface
"""
from planner.models import Project, ProjectMember 


def user_projects(request):
    """
    Provides project context for admin interface.
    
    Returns:
    - user_projects: List of projects user can access
    - current_project: Currently selected project
    - show_project_dropdown: Whether to show dropdown (owners/superusers only)
    - user_role: User's role (superuser/owner/editor/viewer)
    """
    context = {
        'user_projects': [],
        'current_project': None,
        'show_project_dropdown': False,
        'user_role': None,
    }
    
    if not request.user.is_authenticated:
        return context
    
    # Determine user role and project access
    if request.user.is_superuser:
        # Superusers see all projects with dropdown
        context['user_projects'] = Project.objects.all().order_by('-created_at')
        context['show_project_dropdown'] = True
        context['user_role'] = 'superuser'
    
    elif hasattr(request.user, 'userprofile'):
        # Check if user owns projects
        owned_projects = Project.objects.filter(owner=request.user).order_by('-created_at')
        
        # Check if user is invited to projects
        invited_projects = Project.objects.filter(
            projectmember__user=request.user
        ).distinct().order_by('-created_at')
        
        if owned_projects.exists():
            # User owns projects - show dropdown with owned projects
            context['user_projects'] = owned_projects
            context['show_project_dropdown'] = True
            context['user_role'] = 'owner'
        
        elif invited_projects.exists():
            # User is invited but doesn't own - no dropdown, auto-scoped
            context['user_projects'] = invited_projects
            context['show_project_dropdown'] = False
            
            # Determine if editor or viewer
            membership = ProjectMember.objects.filter(user=request.user).first()
            if membership:
                context['user_role'] = membership.role  # 'editor' or 'viewer'
            else:
                context['user_role'] = 'viewer'
    
    # Set current project from request
    if hasattr(request, 'current_project'):
        context['current_project'] = request.current_project
    
    return context