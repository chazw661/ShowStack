# planner/admin_ordering.py
# Complete file with CommCrewName positioned correctly under Communications

from django.contrib import admin

# Store the original get_app_list
original_get_app_list = admin.site.get_app_list

def ordered_get_app_list(request, app_label=None):
    app_list = original_get_app_list(request, app_label)
    
    # Define the correct order with proper groupings
    order_map = {
        # Main Equipment (1-2)
        'console': 1,
        'device': 2,
        
        # Show Management (3-6)
        'showday': 3,
        'micsession': 4,
        'micassignment': 5,
        'micshowinfo': 6,
        
        # Communications (7-11) - Now includes CommCrewName
        'commbeltpack': 7,
        'location': 8,  # Comm Locations
        'commposition': 9,
        'commcrewname': 10,  # Moved here from bottom
        'commchannel': 11,
        
        # System Processors (12)
        'systemprocessor': 12,
        
        # PA Cable System (13-14)
        'pacableschedule': 13,  # PA Cable Entries
        'pafanout': 14,  # PA Fan Outs (if exists)
        
        # PA Zones (15) - standalone
        'pazone': 15,
        
        # Soundvision (16-18)
        'soundvisionprediction': 16,
        'speakerarray': 17,
        'speakercabinet': 18,
        
        # Power Distribution (19-23)
        'powerdistributionplan': 19,
        'amplifierassignment': 20,  # Child of Power Distribution
        'amplifierprofile': 21,  # Child of Power Distribution
        'ampmodel': 22,  # Amp Model Templates - child
        'amp': 23,  # Individual amps if exists
        
        # Audio Checklist (24)
        'audiochecklist': 24,
        
        # Any other models that might exist (25+)
        'ampchannel': 25,
        # Add any other models here if they exist
    }
    
    for app in app_list:
        if app['app_label'] == 'planner':
            app['models'].sort(key=lambda x: order_map.get(x['object_name'].lower(), 999))
    
    return app_list

# Apply the monkey patch
admin.site.get_app_list = ordered_get_app_list