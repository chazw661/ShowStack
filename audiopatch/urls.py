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
    # In-place sync: current slot state for the sessions on the caller's page.
    path('api/mic-tracker-sync/', planner_views.mic_tracker_sync, name='mic_tracker_sync'),


    

    


    # Console Template Library now lives on ConsoleAdmin.get_urls(), behind
    # admin_view(). This old path is kept only so bookmarks still land there.
    path('console-template-library/',
         RedirectView.as_view(pattern_name='admin:console_template_library')),
    
    # Root redirect to mic tracker
    path('', lambda request: redirect('/audiopatch/mic-tracker/')),

    path('m/', include('planner.mobile_urls')),

    
    ]

from django.conf import settings
from django.conf.urls.static import static
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

