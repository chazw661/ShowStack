from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from .forms import RegistrationForm
from planner.models import Project, ProjectMember
from django.shortcuts import get_object_or_404
from django.core.mail import send_mail
from django.conf import settings
from planner.models import Invitation
from .invitation_forms import InviteUserForm
from django.contrib.auth.models import Group

def register(request):
    """
    Public registration view - creates free accounts.
    Free users can accept invitations but cannot create projects.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request, 
                f'Welcome to ShowStack, {user.first_name}! Your free account has been created. '
                'You can now accept project invitations from other users.'
            )
            return redirect('login')
    else:
        form = RegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})


class ShowStackLoginView(LoginView):
    """
    Custom login view with ShowStack branding.
    """
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('dashboard')
    
    def form_invalid(self, form):
        messages.error(self.request, 'Invalid username or password.')
        return super().form_invalid(form)


@login_required
def user_logout(request):
    """
    Logout view with confirmation message.
    """
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('login')


@login_required
def dashboard(request):
    user = request.user
    
    # Get projects owned by user
    owned_projects = Project.objects.filter(owner=user).order_by('-start_date')
    
    # Get projects where user is a member
    member_projects = ProjectMember.objects.filter(
        user=user
    ).select_related('project').order_by('-project__start_date')

    # Get project IDs where user is already a member or owner
    member_project_ids = ProjectMember.objects.filter(user=user).values_list('project_id', flat=True)
    owned_project_ids = owned_projects.values_list('id', flat=True)
    excluded_project_ids = list(member_project_ids) + list(owned_project_ids)
    
    # Get pending invitations, excluding projects user already has access to
    pending_invitations = Invitation.objects.filter(
        email__iexact=user.email,
        status='pending'
    ).exclude(
        project_id__in=excluded_project_ids
    ).select_related('project', 'invited_by').order_by('-invited_at')

        # Check if user can create projects
    # Superusers, paid, and beta accounts can create projects
    can_create_projects = False
    if user.is_superuser:
        can_create_projects = True
    elif hasattr(user, 'userprofile'):
        account_type = user.userprofile.account_type
        can_create_projects = account_type in ['paid', 'beta']
    
    context = {
        'owned_projects': owned_projects,
        'member_projects': member_projects,
        'pending_invitations': pending_invitations,
        'can_create_projects': can_create_projects,
        'account_type': user.userprofile.account_type if hasattr(user, 'userprofile') else 'free',
    }
    
    return render(request, 'accounts/dashboard.html', context)



#-----Invitation----


@login_required
def invite_user(request, project_id):
    """
    Allow project owners to invite users via email.
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check if user is the project owner
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can invite users.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = InviteUserForm(
            request.POST,
            project=project,
            invited_by=request.user
        )
        if form.is_valid():
            invitation = form.save()
            
            # Send invitation email
            send_invitation_email(invitation, request)
            
            messages.success(
                request,
                f'Invitation sent to {invitation.email} as {invitation.get_role_display()}!'
            )
            return redirect('project_invitations', project_id=project.id)
    else:
        form = InviteUserForm(project=project, invited_by=request.user)
    
    context = {
        'form': form,
        'project': project,
    }
    return render(request, 'accounts/invite_user.html', context)


@login_required
def project_invitations(request, project_id):
    """
    View all invitations for a project (owner only).
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check if user is the project owner
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can view invitations.')
        return redirect('dashboard')
    
    invitations = Invitation.objects.filter(project=project).order_by('-invited_at')
    
    context = {
        'project': project,
        'invitations': invitations,
    }
    return render(request, 'accounts/project_invitations.html', context)


def accept_invitation(request, token):
    """
    Accept an invitation via unique token link.
    Users can accept before or after creating an account.
    """
    invitation = get_object_or_404(Invitation, token=token)
    
    # Check if invitation is valid
    if not invitation.is_valid():
        if invitation.status == 'accepted':
            messages.info(request, 'This invitation has already been accepted.')
        elif invitation.status == 'expired':
            messages.error(request, 'This invitation has expired.')
        else:
            messages.error(request, 'This invitation is no longer valid.')
        return redirect('login')
    
    # If user is not logged in, show them the invitation details and prompt to login/register
    if not request.user.is_authenticated:
        context = {
            'invitation': invitation,
            'token': token,
        }
        return render(request, 'accounts/invitation_preview.html', context)
    
    # User is logged in - check if their email matches
    if request.user.email.lower() != invitation.email.lower():
        messages.error(
            request,
            f'This invitation was sent to {invitation.email}. '
            f'You are logged in as {request.user.email}. '
            f'Please log in with the correct account.'
        )
        return redirect('logout')
    
    # Accept the invitation
    if invitation.accept(request.user):

    # Auto-assign user to appropriate permission group
        if invitation.role == 'editor':
            editor_group, _ = Group.objects.get_or_create(name='Editor')
            request.user.groups.add(editor_group)
        elif invitation.role == 'viewer':
            viewer_group, _ = Group.objects.get_or_create(name='Viewer')
            request.user.groups.add(viewer_group)
        
        # Make user staff so they can access admin
        if not request.user.is_staff:
            request.user.is_staff = True
            request.user.save()    
        messages.success(
            request,
            f'Welcome to {invitation.project.name}! You have been added as {invitation.get_role_display()}.'
        )
        return redirect('dashboard')
    else:
        messages.error(request, 'Unable to accept invitation. Please contact the project owner.')
        return redirect('dashboard')


def send_invitation_email(invitation, request):
    """
    Send invitation email with acceptance link using Resend API.
    """
    import resend
    import os
    
    accept_url = request.build_absolute_uri(
        f'/invitations/accept/{invitation.token}/'
    )
    
    subject = f'Invitation to join {invitation.project.name} on ShowStack'
    
    message = f"""
<h2>You've been invited to collaborate!</h2>

<p><strong>{invitation.invited_by.get_full_name() or invitation.invited_by.username}</strong> has invited you to collaborate on their ShowStack project:</p>

<ul>
    <li><strong>Project:</strong> {invitation.project.name}</li>
    <li><strong>Role:</strong> {invitation.get_role_display()}</li>
    <li><strong>Start Date:</strong> {{ invitation.project.start_date or 'Not set' }}</li>
    <li><strong>Venue:</strong> {invitation.project.venue or 'Not set'}</li>
</ul>

<p><a href="{accept_url}" style="display: inline-block; padding: 12px 24px; background-color: #4a9eff; color: white; text-decoration: none; border-radius: 6px; margin: 20px 0;">Accept Invitation</a></p>

<p><small>This invitation will expire in 7 days.</small></p>

<p><small>If you don't have a ShowStack account yet, you'll be prompted to create one.</small></p>

<hr>
<p><small>ShowStack - Professional Audio Production Management</small></p>
"""
    
    # Send email using Resend API
    resend.api_key = os.environ.get('RESEND_API_KEY')
    
    try:
        params = {
           "from": "ShowStack <noreply@showstack.io>",
            "to": [invitation.email],
            "subject": subject,
            "html": message,
        }
        email = resend.Emails.send(params)
        print(f"✅ Email sent successfully to {invitation.email}")
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        raise





    #------Free User View-----


@login_required
def project_detail(request, project_id):
    """
    Project detail view for non-admin users.
    Shows project info with permission-based access.
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check if user has access to this project
    is_owner = project.owner == request.user
    
    # Check if user is a member
    try:
        membership = ProjectMember.objects.get(project=project, user=request.user)
        is_member = True
        user_role = membership.role
    except ProjectMember.DoesNotExist:
        is_member = False
        user_role = None
    
    # Deny access if user is neither owner nor member
    if not is_owner and not is_member:
        messages.error(request, 'You do not have access to this project.')
        return redirect('dashboard')
    
    # Determine user's access level
    if is_owner:
        access_level = 'owner'
        can_edit = True
        can_invite = True
    elif user_role == 'editor':
        access_level = 'editor'
        can_edit = True
        can_invite = False
    else:  # viewer
        access_level = 'viewer'
        can_edit = False
        can_invite = False
    
    # Get project members
    members = ProjectMember.objects.filter(project=project).select_related('user')
    
    context = {
        'project': project,
        'is_owner': is_owner,
        'is_member': is_member,
        'access_level': access_level,
        'user_role': user_role,
        'can_edit': can_edit,
        'can_invite': can_invite,
        'members': members,
    }
    
    return render(request, 'accounts/project_detail.html', context)



#----Dashboard Page----

@login_required
def set_project(request, project_id):
    """Set the current project in session and redirect to admin"""
    from planner.models import Project, ProjectMember
    from django.contrib import messages
    
    try:
        project = Project.objects.get(id=project_id)
        
        is_owner = project.owner == request.user
        is_member = ProjectMember.objects.filter(
            project=project,
            user=request.user
        ).exists()
        
        if not is_owner and not is_member and not request.user.is_superuser:
            messages.error(request, "You don't have access to this project.")
            return redirect('dashboard')
        
        # Set the project in session
        request.session['current_project_id'] = project_id
        request.session.modified = True  # <-- ADD THIS LINE
        messages.success(request, f'Now viewing: {project.name}')
        
        return redirect('/admin/')
        
    except Project.DoesNotExist:
        messages.error(request, "Project not found.")
        return redirect('dashboard')
    
@login_required
def delete_project(request, project_id):
    """Delete a project (owner only)"""
    from planner.models import Project
    from django.contrib import messages
    
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
        project_name = project.name
        project.delete()
        messages.success(request, f'Successfully deleted project: {project_name}')
    except Project.DoesNotExist:
        messages.error(request, "Project not found or you don't have permission to delete it.")
    
    return redirect('dashboard')


@login_required
def leave_project(request, project_id):
    """Leave a shared project (remove membership)"""
    from planner.models import ProjectMember
    from django.contrib import messages
    
    try:
        membership = ProjectMember.objects.get(project_id=project_id, user=request.user)
        project_name = membership.project.name
        membership.delete()
        messages.success(request, f'You have left: {project_name}')
    except ProjectMember.DoesNotExist:
        messages.error(request, "Project membership not found.")
    
    return redirect('dashboard')


from planner.models import ProjectAccessRequest
from django.utils import timezone

def project_request_access(request, invite_token):
    """
    Public link — crew member lands here, logs in if needed, submits access request.
    """
    from planner.models import Project
    project = get_object_or_404(Project, invite_token=invite_token)

    # Must be logged in
    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/projects/request/{invite_token}/')

    # Already a member or owner?
    if project.owner == request.user:
        messages.info(request, "You own this project.")
        return redirect('/audiopatch/')

    if ProjectMember.objects.filter(project=project, user=request.user).exists():
        messages.info(request, f"You already have access to {project.name}.")
        return redirect('/audiopatch/')

    # Already submitted a request?
    existing = ProjectAccessRequest.objects.filter(project=project, requester=request.user).first()

    if request.method == 'POST':
        if existing and existing.status == 'pending':
            messages.info(request, "Your request is already pending approval.")
        elif not existing or existing.status == 'denied':
            msg = request.POST.get('message', '')
            if existing:
                existing.status = 'pending'
                existing.message = msg
                existing.reviewed_by = None
                existing.reviewed_at = None
                existing.assigned_role = None
                existing.save()
            else:
                ProjectAccessRequest.objects.create(
                    project=project,
                    requester=request.user,
                    message=msg,
                )
            # Notify project owner
            send_access_request_email(project, request.user, request)
            messages.success(request, f"Access request sent to {project.owner.get_full_name() or project.owner.username}. You'll get an email when it's approved.")
        return redirect(f'/projects/request/{invite_token}/')

    return render(request, 'accounts/request_access.html', {
        'project': project,
        'existing': existing,
    })


@login_required
def project_access_requests(request, project_id):
    """
    Project owner sees all pending access requests and can approve/deny.
    """
    from planner.models import Project
    project = get_object_or_404(Project, id=project_id)

    if project.owner != request.user:
        messages.error(request, "Only the project owner can manage access requests.")
        return redirect('/audiopatch/')

    if request.method == 'POST':
        req_id = request.POST.get('request_id')
        action = request.POST.get('action')  # 'approve' or 'deny'
        role = request.POST.get('role', 'viewer')

        access_req = get_object_or_404(ProjectAccessRequest, id=req_id, project=project)

        if action == 'approve':
            # Create ProjectMember
            ProjectMember.objects.get_or_create(
                project=project,
                user=access_req.requester,
                defaults={'role': role, 'invited_by': request.user}
            )
            # Add to Django group
            from django.contrib.auth.models import Group
            group_name = 'Editor' if role == 'editor' else 'Viewer'
            try:
                group = Group.objects.get(name=group_name)
                access_req.requester.groups.add(group)
            except Group.DoesNotExist:
                pass

            access_req.status = 'approved'
            access_req.assigned_role = role
            access_req.reviewed_by = request.user
            access_req.reviewed_at = timezone.now()
            access_req.save()
            send_access_approved_email(access_req, request)
            messages.success(request, f"{access_req.requester.username} approved as {role}.")

        elif action == 'deny':
            access_req.status = 'denied'
            access_req.reviewed_by = request.user
            access_req.reviewed_at = timezone.now()
            access_req.save()
            messages.info(request, f"{access_req.requester.username}'s request denied.")

        return redirect(f'/projects/{project_id}/requests/')

    pending = ProjectAccessRequest.objects.filter(project=project, status='pending')
    reviewed = ProjectAccessRequest.objects.filter(project=project).exclude(status='pending')

    return render(request, 'accounts/access_requests.html', {
        'project': project,
        'pending': pending,
        'reviewed': reviewed,
    })


def send_access_request_email(project, requester, request):
    import resend, os
    resend.api_key = os.environ.get('RESEND_API_KEY')
    approve_url = request.build_absolute_uri(f'/projects/{project.id}/requests/')
    html = f"""
    <h2>New Access Request — {project.name}</h2>
    <p><strong>{requester.get_full_name() or requester.username}</strong> ({requester.email}) 
    is requesting access to your ShowStack project.</p>
    <p><a href="{approve_url}" style="display:inline-block;padding:12px 24px;background:#4a9eff;color:white;text-decoration:none;border-radius:6px;">
    Review Request</a></p>
    <p><small>ShowStack — Professional Audio Production Management</small></p>
    """
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [project.owner.email],
            "subject": f"Access Request: {requester.get_full_name() or requester.username} wants to join {project.name}",
            "html": html,
        })
    except Exception as e:
        print(f"❌ Access request email error: {e}")


def send_access_approved_email(access_req, request):
    import resend, os
    resend.api_key = os.environ.get('RESEND_API_KEY')
    login_url = request.build_absolute_uri('/login/')
    html = f"""
    <h2>You've been granted access!</h2>
    <p>Your request to join <strong>{access_req.project.name}</strong> has been approved.</p>
    <p><strong>Your role:</strong> {access_req.get_assigned_role_display()}</p>
    <p><a href="{login_url}" style="display:inline-block;padding:12px 24px;background:#4a9eff;color:white;text-decoration:none;border-radius:6px;">
    Open ShowStack</a></p>
    <p><small>ShowStack — Professional Audio Production Management</small></p>
    """
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [access_req.requester.email],
            "subject": f"Access Approved: {access_req.project.name}",
            "html": html,
        })
    except Exception as e:
        print(f"❌ Approval email error: {e}")