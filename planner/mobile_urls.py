# planner/mobile_urls.py
"""
Mobile URL routing for ShowStack.
All mobile views are namespaced under /m/
"""

from django.urls import path
from . import mobile_views

app_name = 'mobile'

urlpatterns = [
    # Authentication
    path('login/', mobile_views.mobile_login, name='login'),
    path('logout/', mobile_views.mobile_logout, name='logout'),
    
    # Dashboard
    path('', mobile_views.mobile_dashboard, name='dashboard'),
    
    # Project views
    path('project/<int:project_id>/', mobile_views.project_overview, name='project_overview'),

    # ADD THESE TO YOUR EXISTING mobile_urls.py
# Add to the urlpatterns list:

# Soundvision Predictions (Phase 2)
    path('project/<int:project_id>/predictions/', mobile_views.predictions_list, name='predictions_list'),
    path('project/<int:project_id>/predictions/<int:prediction_id>/', mobile_views.prediction_detail, name='prediction_detail'),
    
    # Mic Tracker (Phase 3)
    path('project/<int:project_id>/mic-tracker/', mobile_views.mic_tracker_days, name='mic_tracker_days'),
    path('project/<int:project_id>/mic-tracker/day/<int:day_id>/', mobile_views.mic_tracker_sessions, name='mic_tracker_sessions'),
    path('project/<int:project_id>/mic-tracker/session/<int:session_id>/', mobile_views.mic_tracker_assignments, name='mic_tracker_assignments'),
    # COMM (Phase 4)
    path('project/<int:project_id>/comm/', mobile_views.comm_list, name='comm_list'),  

    # Mobile Editing API (Phase 5)
    path('api/comm/toggle-checkout/<int:bp_id>/', mobile_views.toggle_checkout, name='toggle_checkout'),
    path('api/mic/toggle-micd/<int:assignment_id>/', mobile_views.toggle_micd, name='toggle_micd'), 

    
    # Future phases will add:
  
    # path('project/<int:project_id>/comm/', mobile_views.comm_list, name='comm_list'),
    # path('project/<int:project_id>/rf/', mobile_views.rf_frequencies, name='rf_frequencies'),
]
