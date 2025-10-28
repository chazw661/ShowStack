from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.ShowStackLoginView.as_view(), name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Invitation URLs
    path('projects/<int:project_id>/invite/', views.invite_user, name='invite_user'),
    path('projects/<int:project_id>/invitations/', views.project_invitations, name='project_invitations'),
    path('invitations/accept/<uuid:token>/', views.accept_invitation, name='accept_invitation'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
]