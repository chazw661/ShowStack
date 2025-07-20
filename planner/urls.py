from django.urls import path
from . import views

urlpatterns = [
    path("consoles/", views.console_list, name="console_list"),
    path("consoles/<int:console_id>/", views.console_detail, name="console_detail"),
]
