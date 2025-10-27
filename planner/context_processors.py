from .models import Project


def user_projects(request):
    """Add user's projects to every template context"""
    if request.user.is_authenticated:
        projects = Project.objects.filter(owner=request.user) | \
                  Project.objects.filter(projectmember__user=request.user)
        return {
            'user_projects': projects.distinct().order_by('-updated_at')
        }
    return {}