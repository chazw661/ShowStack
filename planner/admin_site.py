"""
Custom AdminSite for ShowStack Audio Patch Application
Provides role-based admin interface visibility
"""
from django.contrib import admin
from django.contrib.auth.models import Group, User


class ShowStackAdminSite(admin.AdminSite):
    """
    Custom admin site that controls visibility of sections based on user role.
    
    - Superusers: See everything (Themes, Groups, Users, User Profiles, all equipment)
    - Project Owners & Editors: See only equipment sections
    - Viewers: See only equipment sections (read-only enforced at model level)
    """
    
    site_header = "ShowStack Administration"
    site_title = "ShowStack Admin"
    index_title = "Equipment Management"
    
    def get_app_list(self, request, app_label=None):
        """
        Customize the app list based on user role AND apply custom ordering.
        """
        app_list = super().get_app_list(request, app_label)
        
        # Superusers see everything
        if request.user.is_superuser:
            # Apply ordering for superusers
            return self._apply_ordering(app_list)
        
        # Non-superusers: Filter out Auth and Admin sections
        filtered_apps = []
        for app in app_list:
            # Skip 'Authentication and Authorization' app for non-superusers
            if app['app_label'] == 'auth':
                continue
            
            # Skip 'Admin' app for non-superusers (contains themes, etc.)
            if app['app_label'] == 'admin':
                continue
                
            # For accounts app, filter out User and Group models
            if app['app_label'] == 'accounts':
                filtered_models = []
                for model in app['models']:
                    # Skip User and Group models for non-superusers
                    if model['object_name'] in ['User', 'Group']:
                        continue
                    filtered_models.append(model)
                
                if filtered_models:
                    app['models'] = filtered_models
                    filtered_apps.append(app)
            else:
                # Include all other apps (planner equipment modules)
                filtered_apps.append(app)
        
        return self._apply_ordering(filtered_apps)

    def _apply_ordering(self, app_list):
        """
        Apply custom ordering to the app list based on order_map.
        Keeps Authentication & Authorization separate, orders everything else in PLANNER.
        """
        # Define the correct order with proper groupings
        order_map = {
            # User/Project Management (1-4)
            'projectmember': 1,  # Project Members
            'invitation': 2,  # Invitations
            'project': 3,  # Projects
            
            # Main Equipment (4-7)
            'location': 4,  # Equip Locations
            'console': 5,
            'device': 6,
            'amp': 7,
            
            # System Processors (8)
            'systemprocessor': 8,
            
            # PA Cable System (9-10)
            'pacableschedule': 9,  # PA Cable Entries - PARENT
            'pafanout': 10,  # └─ PA Fan Outs - CHILD
            
            # Communications (11-14)
            'commbeltpack': 11,
           
            
            # Show Mic Tracker (15-19)
            'showday': 15,  # Show Mic Tracker - PARENT
            'micsession': 16,
            'micassignment': 17,
            'presenter': 18,
            'micshowinfo': 19,
            
            # PA Zones (20) - standalone
            'pazone': 20,
            
            # Soundvision (21-23)
            'soundvisionprediction': 21,
            'speakerarray': 22,
            'speakercabinet': 23,
            
            # Amplifiers (24-26)
            'amplifierprofile': 24,
            'powerdistributionplan': 25,
            'amplifierassignment': 26,
            
            # Standalone Models (27-28)
            'ampmodel': 27,
            'audiochecklist': 28,
            
            # P1 & Galaxy Processors (29-34)
            'p1processor': 29,
            'p1input': 30,
            'p1output': 31,
            'galaxyprocessor': 32,
            'galaxyinput': 33,
            'galaxyoutput': 34,
        }
        
        # Separate auth models from other models
        auth_models = []
        other_models = []
        
        for app in app_list:
            for model in app.get('models', []):
                model_name = model.get('object_name', '').lower()
                
                # Keep User, Group, and User Profiles in auth section
                if model_name in ['user', 'group', 'userprofile']:
                    # Order within auth section: user=0, group=1, userprofile=2
                    auth_order = {'user': 0, 'group': 1, 'userprofile': 2}.get(model_name, 999)
                    auth_models.append((auth_order, model))
                else:
                    # Skip models that are accessible via parent page buttons
                    if model_name in ('commposition', 'commcrewname', 'commchannel'):
                        continue
                    order = order_map.get(model_name, 999)
                    other_models.append((order, model))
        
        # Sort auth models by their order
        auth_models.sort(key=lambda x: x[0])
        
        # Sort other models by order number
        other_models.sort(key=lambda x: x[0])
        
        # Build result with two apps
        result = []
        
        # Add Authentication & Authorization app if there are auth models
        if auth_models:
            result.append({
                'name': 'Authentication and Authorization',
                'app_label': 'auth',
                'app_url': '/admin/auth/',
                'has_module_perms': True,
                'models': [model for order, model in auth_models]
            })
        
        # Add PLANNER app with all other models in order
        if other_models:
            result.append({
                'name': 'PLANNER',
                'app_label': 'planner',
                'app_url': '/admin/planner/',
                'has_module_perms': True,
                'models': [model for order, model in other_models]
            })
        
        return result
    
    def has_permission(self, request):
        """
        Check if user has permission to access admin.
        
        - Superusers: Always have access
        - Paid/Beta staff users: Always have access (can create projects)
        - Free staff users: Have access if they are members of projects
        - Others: No access
        """
        if not request.user.is_active:
            return False
        
        # Superusers always have access
        if request.user.is_superuser:
            return True
        
        # Staff users with proper account access
        if request.user.is_staff:
            if not hasattr(request.user, 'userprofile'):
                return False
            
            # Paid and beta users can always access (they can create projects)
            account_type = request.user.userprofile.account_type
            if account_type in ['paid', 'beta']:
                return True
            
            # Free users need to be members of at least one project
            from planner.models import Project, ProjectMember
            owns_projects = Project.objects.filter(owner=request.user).exists()
            member_of_projects = ProjectMember.objects.filter(user=request.user).exists()
            
            return owns_projects or member_of_projects
        
        return False

# Create the custom admin site instance
showstack_admin_site = ShowStackAdminSite(name='showstack_admin')