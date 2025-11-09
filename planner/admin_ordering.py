# planner/admin_ordering.py
# Updated to hide child models for viewers
from django.contrib import admin
from planner.models import ProjectMember, Project
from planner.admin_site import showstack_admin_site

# TEST - print on import
print("=" * 50)
print("ADMIN_ORDERING.PY LOADED")
print("=" * 50)

# Store the original get_app_list
# Store the original get_app_list from showstack_admin_site
original_get_app_list = showstack_admin_site.get_app_list




def ordered_get_app_list(request, app_label=None):
    print("*** FUNCTION CALLED ***")
    app_list = original_get_app_list(request, app_label)
    app_list = [app for app in app_list if app['app_label'] != 'admin_interface']
    
    # Check if user is a viewer (no editor/owner roles)
    is_viewer = False
    if not request.user.is_superuser:
        viewer_memberships = ProjectMember.objects.filter(
            user=request.user,
            role='viewer'
        )
        
        if viewer_memberships.exists():
            editor_owner_memberships = ProjectMember.objects.filter(
                user=request.user,
                role='editor'
            ).exists()
            
            owns_projects = Project.objects.filter(owner=request.user).exists()
            
            # If ONLY viewer (no editor roles or owned projects), set read-only
            if not editor_owner_memberships and not owns_projects:
                is_viewer = True
    
    # DEBUG
    print(f"User: {request.user.username}, is_viewer: {is_viewer}")
    
    # Define child models that should be hidden from viewers
    child_models = {
        'pafanout',           # Child of PA Cable Entries
        'commposition',       # Child of Comm Belt Packs
        'commcrewname',       # Child of Comm Belt Packs
        'commchannel',        # Child of Comm Belt Packs
        'micsession',         # Child of Show Mic Tracker
        'micassignment',      # Child of Show Mic Tracker
        'presenter',          # Child of Show Mic Tracker
        'micshowinfo',        # Child of Show Mic Tracker
        'speakerarray',       # Child of Soundvision Predictions
        'speakercabinet',     # Child of Soundvision Predictions
        'amplifierassignment',# Child of Power Distribution Plans
        'ampmodel',           # Child of Amplifier Assignments 
        'amplifierprofile',   # Child of Amplifier Profiles
        'p1input',            # Child of P1 Processor
        'p1output',           # Child of P1 Processor
        'galaxyinput',        # Child of Galaxy Processor
        'galaxyoutput',       # Child of Galaxy Processor
    }
    
    # Define the correct order with proper groupings
    order_map = {
        # Authentication & Authorization (0)
        'user': 0,
        'group': 0.5,
        
        # User/Project Management (1-4)
        'userprofile': 1,
        'projectmember': 2,
        'invitation': 3,
        'project': 4,
        
        # Main Equipment (5-8)
        'location': 5,
        'console': 6,
        'device': 7,
        'amp': 8,
        'ampmodel': 8.5,
        
        # System Processors (9)
        'systemprocessor': 9,
        
        # PA Cable System (10-11)
        'pacableschedule': 10,
        'pafanout': 11,
        
        # Communications (12-15)
        'commbeltpack': 12,
        'commposition': 13,
        'commcrewname': 14,
        'commchannel': 15,
        
        # Show Mic Tracker (16-20)
        'showday': 16,
        'micsession': 17,
        'micassignment': 18,
        'presenter': 19,
        'micshowinfo': 20,
        
        # PA Zones (21)
        'pazone': 21,
        
        # Soundvision (22-24)
        'soundvisionprediction': 22,
        'speakerarray': 23,
        'speakercabinet': 24,
        
        # Amplifiers (25-27)
        'powerdistributionplan': 25,
        'amplifierassignment': 25.5,
        'amplifierprofile': 25.6,

    
        
        # Standalone Models (28-29)
        'audiochecklist': 29,
        
        # P1 & Galaxy Processors (30-35)
        'p1processor': 30,
        'p1input': 31,
        'p1output': 32,
        'galaxyprocessor': 33,
        'galaxyinput': 34,
        'galaxyoutput': 35,
    }
    
    for app in app_list:
        if app['app_label'] == 'planner':
            # DEBUG - print model names before filtering
            if is_viewer:
                print(f"Models before filtering: {[m['object_name'] for m in app['models']]}")
            
            # Filter out child models for viewers
            if is_viewer:
                filtered_models = []
                for model in app['models']:
                    model_name = model['object_name'].lower()
                    if model_name not in child_models:
                        filtered_models.append(model)
                    else:
                        print(f"Filtering out: {model_name}")  # DEBUG
                
                app['models'] = filtered_models
                print(f"Models after filtering: {[m['object_name'] for m in app['models']]}")  # DEBUG

            # Sort remaining models
        
                print(f"DEBUG - Models before sort: {[(m['object_name'], order_map.get(m['object_name'].lower(), 999)) for m in app['models']]}")
            app['models'].sort(key=lambda x: order_map.get(x['object_name'].lower(), 999))    
                            
            
        
            return app_list

# Apply the monkey patch
showstack_admin_site.get_app_list = ordered_get_app_list