from django.urls import path
from . import views

urlpatterns = [

    path("consoles/<int:console_id>/", views.console_detail, name="console_detail"),
]



# Add to your urls.py

from django.urls import path
from . import views

urlpatterns = [
    path("consoles/<int:console_id>/", views.console_detail, name="console_detail"),
    
    # P1 Processor URLs
    path('p1/<int:p1_processor_id>/export/', views.p1_processor_export, name='p1_processor_export'),
    path('p1/<int:p1_processor_id>/summary/', views.p1_processor_summary, name='p1_processor_summary'),
]
