from django.urls import path

from . import views

app_name = 'help'

urlpatterns = [
    path('', views.help_index, name='index'),
    path('<slug:slug>/', views.help_topic, name='topic'),
]
