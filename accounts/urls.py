from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.ShowStackLoginView.as_view(), name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Password reset (Django built-in flow, ShowStack-branded templates).
    # Uses SMTP backend configured in settings; DEBUG prints to console.
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    
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