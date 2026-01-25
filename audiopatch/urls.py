"""
URL configuration for audiopatch project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.http import HttpResponse
from django.contrib import admin
from django.urls import path
from django.urls import include
from django.shortcuts import redirect  
from django.views.generic import RedirectView
from planner import views
from planner.admin_site import showstack_admin_site
from planner import views as planner_views



urlpatterns = [
    # Admin site
    path('admin/', showstack_admin_site.urls),

    path('', include('marketing.urls')),

    path('', include('accounts.urls')),
    
    # Dashboard at root level (accessible at /dashboard/)
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Include all planner URLs under /audiopatch/ prefix
    path('audiopatch/', include('planner.urls')),

     # API endpoints at root level (no prefix)
    path('api/mic-tracker-checksum/', planner_views.mic_tracker_checksum, name='mic_tracker_checksum'),


    

    


    # Console Template Library
    path('console-template-library/', 
         lambda request: __import__('planner.admin', fromlist=['ConsoleAdmin']).ConsoleAdmin(
             __import__('planner.models', fromlist=['Console']).Console, 
             admin.site
         ).console_template_library_view(request),
         name='console_template_library'),
    
    # Root redirect to mic tracker
    path('', lambda request: redirect('/audiopatch/mic-tracker/')),

    path('m/', include('planner.mobile_urls')),

    
    ]

