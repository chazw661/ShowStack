from django.urls import path
from . import views

app_name = 'marketing'

urlpatterns = [
    # Main pages
    path('', views.home, name='home'),
    path('features/', views.features, name='features'),
    path('pricing/', views.pricing, name='pricing'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
    
    # Auth
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Legal
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    
    # API
    path('api/waitlist/', views.waitlist_ajax, name='waitlist_ajax'),
]
