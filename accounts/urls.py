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
    path('set-project/<int:project_id>/', views.set_project, name='set_project'),
    path('delete-project/<int:project_id>/', views.delete_project, name='delete_project'),
    path('leave-project/<int:project_id>/', views.leave_project, name='leave_project'),

    path('projects/request/<uuid:invite_token>/', views.project_request_access, name='request_access'),
    path('projects/<int:project_id>/requests/', views.project_access_requests, name='access_requests'),

    # Phase 6: Trusted Crew Rosters (D-03 amended — canonical URL prefix is /crew/)
    path('crew/', views.crew_index, name='crew_index'),
    path('crew/new/', views.crew_create, name='crew_create'),
    path('crew/<int:crew_id>/', views.crew_detail, name='crew_detail'),
    path('crew/<int:crew_id>/delete/', views.crew_delete, name='crew_delete'),
    path('crew/<int:crew_id>/members/add/', views.crew_member_add, name='crew_member_add'),
    path('crew/<int:crew_id>/members/<int:member_id>/remove/', views.crew_member_remove, name='crew_member_remove'),

    # Phase 6 (Plan 04): bulk-add an entire crew to a project
    path('projects/<int:project_id>/invite/add-crew/<int:crew_id>/', views.bulk_add_crew, name='bulk_add_crew'),
]