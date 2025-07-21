from django.urls import path
from . import views

urlpatterns = [

    path("consoles/<int:console_id>/", views.console_detail, name="console_detail"),
]
