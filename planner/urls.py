from django.urls import path
from . import views
from django.contrib import admin
from planner.views import SystemDashboardView

app_name = 'planner'  

urlpatterns = [
    path("consoles/<int:console_id>/", views.console_detail, name="console_detail"),
    
    # P1 Processor URLs
    path('p1/<int:p1_processor_id>/export/', views.p1_processor_export, name='p1_processor_export'),
    path('p1/<int:p1_processor_id>/summary/', views.p1_processor_summary, name='p1_processor_summary'),
    path('galaxy/<int:galaxy_processor_id>/export/', views.galaxy_processor_export, name='galaxy_processor_export'),
    path('galaxy/<int:galaxy_processor_id>/summary/', views.galaxy_processor_summary, name='galaxy_processor_summary'),
    
    # COMM URLs
    path('admin/planner/commbeltpack/get_next_bp_number/', 
         views.get_next_bp_number, 
         name='get_next_bp_number'),
    
    path('admin/planner/commbeltpack/export/', 
         views.export_comm_assignments, 
         name='export_comm_assignments'),
    
    path('admin/planner/comm/matrix/', 
         views.comm_channel_matrix, 
         name='comm_channel_matrix'),
    
    path('admin/planner/commposition/import/', 
         views.import_comm_positions, 
         name='import_comm_positions'),
    
    path('admin/planner/commcrewname/import/', 
         views.import_comm_names, 
         name='import_comm_names'),

    # Dashboard
    path('admin/', admin.site.urls),
    path('dashboard/', SystemDashboardView.as_view(), name='system-dashboard'),
    
    # ADD THESE MIC TRACKER URLs
    path('mic-tracker/', views.mic_tracker_view, name='mic_tracker_view'),
    path('api/mic/update/', views.update_mic_assignment, name='update_mic_assignment'),
    path('api/mic/bulk-update/', views.bulk_update_mics, name='bulk_update_mics'),
    path('api/session/duplicate/', views.duplicate_session, name='duplicate_session'),
    path('api/day/toggle/', views.toggle_day_collapse, name='toggle_day_collapse'),
    path('mic-tracker/export/', views.export_mic_tracker, name='export_mic_tracker'),
    path('api/mic/get-assignment/<int:assignment_id>/', views.get_assignment_details, name='get_assignment_details'),
    path('mic-tracker/', views.mic_tracker_view, name='mic_tracker'),
   
]