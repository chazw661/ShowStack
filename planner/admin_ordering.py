# planner/admin_ordering.py
# Updated to move Amplifier Assignments to position 3

from django.contrib import admin

# Store the original get_app_list
original_get_app_list = admin.site.get_app_list

def ordered_get_app_list(request, app_label=None):
    app_list = original_get_app_list(request, app_label)
    
    # Define the correct order with proper groupings
    order_map = {
        # Main Equipment (1-3)
        'console': 1,
        'device': 2,
        'amp': 3,  # Amplifier Assignments - MOVED HERE
        
        # Show Management (4-7)
        'showday': 4,
        'micsession': 5,
        'micassignment': 6,
        'micshowinfo': 7,
        
        # Communications (8-12)
        'commbeltpack': 8,
        'location': 9,  # Comm Locations
        'commposition': 10,
        'commcrewname': 11,
        'commchannel': 12,
        
        # System Processors (13)
        'systemprocessor': 13,
        
        # PA Cable System (14-15)
        'pacableschedule': 14,  # PA Cable Entries
        'pafanout': 15,  # PA Fan Outs
        
        # PA Zones (16) - standalone
        'pazone': 16,
        
        # Soundvision (17-19)
        'soundvisionprediction': 17,
        'speakerarray': 18,
        'speakercabinet': 19,
        
        # Power Distribution (20-23)
        'powerdistributionplan': 20,
        'amplifierassignment': 21,  # Child of Power Distribution (├─ Amplifiers in Power Plan)
        'amplifierprofile': 22,  # Child of Power Distribution (├─ Amplifier Profiles)
        'ampmodel': 23,  # Child of Power Distribution (└─ Amp Model Templates - LAST CHILD)
        
        # Audio Checklist (24)
        'audiochecklist': 24,
        
        # Any other models (25+)
        'ampchannel': 25,
    }
    
    for app in app_list:
        if app['app_label'] == 'planner':
            app['models'].sort(key=lambda x: order_map.get(x['object_name'].lower(), 999))
    
    return app_list

# Apply the monkey patch
admin.site.get_app_list = ordered_get_app_list