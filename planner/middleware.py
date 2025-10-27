from .models import Project


class CurrentProjectMiddleware:
    """
    Middleware to track which project the user is currently working on.
    Stores project_id in session.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            project_id = request.session.get('current_project_id')
            
            if project_id:
                # User has a project selected - use it
                try:
                    request.current_project = Project.objects.get(id=project_id)
                except Project.DoesNotExist:
                    # Selected project was deleted - clear session
                    request.session.pop('current_project_id', None)
                    request.current_project = None
            else:
                # No project in session - auto-select ONLY on first visit
                # Don't override user's manual selection!
                request.current_project = None
        
        response = self.get_response(request)
        return response