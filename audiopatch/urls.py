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

urlpatterns = [
    path('', RedirectView.as_view(url='/audiopatch/mic-tracker/', permanent=False)),
    path('admin/', admin.site.urls),
    path('audiopatch/', include('planner.urls')),
    path('mic-tracker/', lambda request: redirect('/audiopatch/mic-tracker/', permanent=True)),
    path('test/', lambda request: HttpResponse("It works!")),
]

