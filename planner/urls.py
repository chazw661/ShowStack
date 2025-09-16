from django.urls import path
from . import views
from django.contrib import admin

urlpatterns = [

    path("consoles/<int:console_id>/", views.console_detail, name="console_detail"),
]



# Add to your urls.py

from django.urls import path
from . import views
from planner.views import SystemDashboardView

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

        #Comm Dashboard View
     path('admin/', admin.site.urls),
     path('dashboard/', SystemDashboardView.as_view(), name='system-dashboard'),  


]
