"""
CurrentProjectMiddleware - Handles project scoping for multi-tenancy
"""
from planner.models import Project, ProjectMember  # CORRECT - models are in planner


class CurrentProjectMiddleware:
    """
    Middleware to attach current_project to request for multi-tenant filtering.
    
    Behavior by user role:
    - Superusers: Can switch between any project using dropdown
    - Project Owners: Can switch between their owned projects using dropdown
    - Editors/Viewers: Can access projects they're invited to via session
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        request.current_project = None
        
        if request.user.is_authenticated:
            # Get user role information
            is_superuser = request.user.is_superuser
            is_owner = False
            is_invited = False
            
            if hasattr(request.user, 'userprofile'):
                # Check if user owns any projects
                is_owner = Project.objects.filter(owner=request.user).exists()
                
                # Check if user is invited to any projects
                is_invited = ProjectMember.objects.filter(user=request.user).exists()
            
            # SUPERUSERS and PROJECT OWNERS: Can switch projects via dropdown
            if is_superuser or is_owner:
                # Try to get project from session (dropdown selection)
                project_id = request.session.get('current_project_id')
                
                if project_id:
                    try:
                        project = Project.objects.get(id=project_id)
                        
                        # Verify access
                        if is_superuser:
                            # Superusers can access any project
                            request.current_project = project
                        else:
                            # Owners can only access their own projects
                            if project.owner == request.user:
                                request.current_project = project
                    except Project.DoesNotExist:
                        pass
                
                # If no valid project selected, auto-select first owned project
                if not request.current_project:
                    if is_superuser:
                        # Superusers see all projects
                        first_project = Project.objects.first()
                    else:
                        # Owners see their own projects
                        first_project = Project.objects.filter(owner=request.user).first()
                    
                    if first_project:
                        request.current_project = first_project
                        request.session['current_project_id'] = first_project.id
            
            # EDITORS and VIEWERS: Can access projects they're invited to
            elif is_invited and not is_owner:
                # First, check if there's a project_id in session that they have access to
                project_id = request.session.get('current_project_id')
                
                if project_id:
                    # Verify they're actually a member of this project
                    membership = ProjectMember.objects.filter(
                        user=request.user,
                        project_id=project_id
                    ).select_related('project').first()
                    
                    if membership:
                        request.current_project = membership.project
                
                # If no valid project in session, fall back to first invited project
                if not request.current_project:
                    membership = ProjectMember.objects.filter(
                        user=request.user
                    ).select_related('project').first()
                    
                    if membership:
                        request.current_project = membership.project
                        request.session['current_project_id'] = membership.project.id
        
        response = self.get_response(request)
        return response