from django.urls import path
from . import views
from django.contrib import admin
from planner.views import SystemDashboardView
from django.urls import path, include

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
   # NEW: Shared Presenter Management URLs
    path('api/mic/add-shared-presenter/', views.add_shared_presenter, name='add_shared_presenter'),
    path('api/mic/remove-shared-presenter/', views.remove_shared_presenter, name='remove_shared_presenter'),
    path('api/mic/dmic-and-rotate/', views.dmic_and_rotate, name='dmic_and_rotate'),
    path('api/mic/reset-rotation/', views.reset_presenter_rotation, name='reset_presenter_rotation'),
    
    path('api/mic/update/', views.update_mic_assignment, name='update_mic_assignment'),
    path('api/mic/bulk-update/', views.bulk_update_mics, name='bulk_update_mics'),
    path('api/session/duplicate/', views.duplicate_session, name='duplicate_session'),
    path('api/day/toggle/', views.toggle_day_collapse, name='toggle_day_collapse'),
    path('mic-tracker/', views.mic_tracker_view, name='mic_tracker'),
    path('mic-tracker/export/', views.export_mic_tracker, name='export_mic_tracker'),
    path('api/mic/get-assignment/<int:assignment_id>/', views.get_assignment_details, name='get_assignment_details'),
    
  # Power Distribution URLs
     path('power-distribution/', views.power_distribution_calculator, name='power_distribution_calculator'),
     path('power-distribution/<int:plan_id>/', views.power_distribution_calculator, name='power_distribution_calculator_detail'),

     # Power Distribution API endpoints (keep these as they are)
     path('api/power/plan/<int:plan_id>/update/', views.update_plan_settings, name='update_plan_settings'),
     path('api/power/plan/<int:plan_id>/add-amp/', views.add_amplifier_assignment, name='add_amplifier_assignment'),
     path('api/power/assignment/<int:assignment_id>/update/', views.update_amplifier_assignment, name='update_amplifier_assignment'),
     path('api/power/assignment/<int:assignment_id>/delete/', views.delete_amplifier_assignment, name='delete_amplifier_assignment'),
     path('checklist/', views.audio_checklist, name='audio_checklist'),
     path('predictions/', views.predictions_list, name='predictions_list'),
     path('predictions/<int:pk>/', views.prediction_detail, name='prediction_detail'),
     path('predictions/upload/', views.upload_prediction, name='upload_prediction'),
     path('predictions/<int:pk>/export/', views.export_prediction_summary, name='export_prediction'),

     #-----Console PDF Export-----
     path('console/<int:console_id>/export-pdf/', views.console_pdf_export, name='console_pdf_export'),

     #-------Device PDF-----
     # Device PDF exports
    path('device/<int:device_id>/pdf/', views.device_pdf_export, name='device_pdf_export'),
    path('devices/all/pdf/', views.all_devices_pdf_export, name='all_devices_pdf_export'),
    path('devices/all/pdf/', views.all_devices_pdf_export, name='all_devices_pdf_export'),
    # Amplifier PDF export
    path('amps/all/pdf/', views.all_amps_pdf_export, name='all_amps_pdf_export'),
    path('pa-cables/all/pdf/', views.all_pa_cables_pdf_export, name='all_pa_cables_pdf_export'),
    path('comm-beltpacks/all/pdf/', views.all_comm_beltpacks_pdf_export, name='all_comm_beltpacks_pdf_export'),
    path('comm-crew-names/import-csv/', views.import_comm_crew_names_csv, name='import_comm_crew_names_csv'),
    

   
]