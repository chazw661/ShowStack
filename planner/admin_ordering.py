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
        # User/Project Management (1-2)
        'userprofile': 1,  # User Profiles - TOP
        'project': 2,  # Projects
        
        # Main Equipment (3-6)
        'location': 3,  # Equip Locations
        'console': 4,
        'device': 5,
        'amp': 6,  # Amplifier Assignments
        
        # System Processors (7)
        'systemprocessor': 7,
        
        # PA Cable System (8-9)
        'pacableschedule': 8,  # PA Cable Entries - PARENT
        'pafanout': 9,  # └─ PA Fan Outs - CHILD
        
        # Communications (10-13)
        'commbeltpack': 10,
        'commposition': 11,
        'commcrewname': 12,
        'commchannel': 13,
        
        # Show Mic Tracker (14-18)
        'showday': 14,  # Show Mic Tracker - PARENT
        'micsession': 15,
        'micassignment': 16,
        'presenter': 17,
        'micshowinfo': 18,
        
        # PA Zones (19) - standalone
        'pazone': 19,
        
        # Soundvision (20-22)
        'soundvisionprediction': 20,
        'speakerarray': 21,
        'speakercabinet': 22,
        
        # Power Distribution (23-26)
        'powerdistributionplan': 23,
        'amplifierassignment': 24,
        'amplifierprofile': 25,
        'ampmodel': 26,
        
        # Audio Checklist (27)
        'audiochecklist': 27,
        
        # Any other models (28+)
        'ampchannel': 28,
    }
    
    for app in app_list:
        if app['app_label'] == 'planner':
            app['models'].sort(key=lambda x: order_map.get(x['object_name'].lower(), 999))
    
    return app_list

# Apply the monkey patch
admin.site.get_app_list = ordered_get_app_list