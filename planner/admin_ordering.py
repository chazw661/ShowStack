# planner/admin_ordering.py
# Updated to move Amplifier Assignments to position 3

from django.contrib import admin

# Store the original get_app_list
original_get_app_list = admin.site.get_app_list

def ordered_get_app_list(request, app_label=None):
    app_list = original_get_app_list(request, app_label)
    
    # Define the correct order with proper groupings
    order_map = {
        # Main Equipment (1-4)
        'console': 1,
        'device': 2,
        'amp': 3,  # Amplifier Assignments - PARENT
        'location': 4,  # └─ Locations - CHILD of Amplifier Assignments
        
        # System Processors (5)
        'systemprocessor': 5,
        
        # PA Cable System (6-7)
        'pacableschedule': 6,  # PA Cable Entries - PARENT
        'pafanout': 7,  # └─ PA Fan Outs - CHILD
        
        # Communications (8-11)
        'commbeltpack': 8,
        'commposition': 9,
        'commcrewname': 10,
        'commchannel': 11,
        
        # Show Mic Tracker (12-16)
        'showday': 12,  # Show Mic Tracker - PARENT
        'micsession': 13,
        'micassignment': 14,
        'presenter': 15,  # ← NEW: Added here
        'micshowinfo': 16,  # Changed from 15 to 16
        
        # PA Zones (17) - standalone
        'pazone': 17,  # Changed from 16
        
        # Soundvision (18-20)
        'soundvisionprediction': 18,  # Changed from 17
        'speakerarray': 19,  # Changed from 18
        'speakercabinet': 20,  # Changed from 19
        
        # Power Distribution (21-24)
        'powerdistributionplan': 21,  # Changed from 20
        'amplifierassignment': 22,  # Changed from 21
        'amplifierprofile': 23,  # Changed from 22
        'ampmodel': 24,  # Changed from 23
        
        # Audio Checklist (25)
        'audiochecklist': 25,  # Changed from 24
        
        # Any other models (26+)
        'ampchannel': 26,  # Changed from 25
    }
    
    for app in app_list:
        if app['app_label'] == 'planner':
            app['models'].sort(key=lambda x: order_map.get(x['object_name'].lower(), 999))
    
    return app_list

# Apply the monkey patch
admin.site.get_app_list = ordered_get_app_list