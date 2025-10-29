# planner/admin_ordering.py
# Updated to move Location to position 3 as standalone item

from django.contrib import admin

# Store the original get_app_list
original_get_app_list = admin.site.get_app_list

def ordered_get_app_list(request, app_label=None):
    app_list = original_get_app_list(request, app_label)
    
    # Define the correct order with proper groupings
    # Define the correct order with proper groupings
    order_map = {
    # Authentication & Authorization (0)
    'user': 0,
    'group': 0.5,
    
    # User/Project Management (1-4)
    'userprofile': 1,  # User Profiles - TOP
    'projectmember': 2,  # Project Members - moved up
    'invitation': 3,  # Invitations - moved up
    'project': 4,  # Projects
    
    # Main Equipment (5-8)
    'location': 5,  # Equip Locations
    'console': 6,
    'device': 7,
    'amp': 8,
    
    # System Processors (9)
    'systemprocessor': 9,
    
    # PA Cable System (10-11)
    'pacableschedule': 10,  # PA Cable Entries - PARENT
    'pafanout': 11,  # └─ PA Fan Outs - CHILD
    
    # Communications (12-15)
    'commbeltpack': 12,
    'commposition': 13,
    'commcrewname': 14,
    'commchannel': 15,
    
    # Show Mic Tracker (16-20)
    'showday': 16,  # Show Mic Tracker - PARENT
    'micsession': 17,
    'micassignment': 18,
    'presenter': 19,
    'micshowinfo': 20,
    
    # PA Zones (21) - standalone
    'pazone': 21,
    
    # Soundvision (22-24)
    'soundvisionprediction': 22,
    'speakerarray': 23,
    'speakercabinet': 24,
    
    # Amplifiers (25-27)
    'amplifierprofile': 25,
    'powerdistributionplan': 26,
    'amplifierassignment': 27,
    
    # Standalone Models (28-29)
    'ampmodel': 28,
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
            app['models'].sort(key=lambda x: order_map.get(x['object_name'].lower(), 999))
    
    return app_list

# Apply the monkey patch
admin.site.get_app_list = ordered_get_app_list