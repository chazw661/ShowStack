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
    """
    User dashboard - shows all projects the user owns or is a member of.
    This is the main landing page after login.
    """
    user = request.user
    
    # Get projects owned by user
    owned_projects = Project.objects.filter(owner=user).order_by('-show_date')
    
    # Get projects where user is a member
    member_projects = ProjectMember.objects.filter(
        user=user
    ).select_related('project').order_by('-project__show_date')
    
    # Check if user can create projects
    can_create_projects = False
    if hasattr(user, 'userprofile'):
        can_create_projects = user.userprofile.can_create_projects
    
    context = {
        'owned_projects': owned_projects,
        'member_projects': member_projects,
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
    Send invitation email with acceptance link.
    For now, this will print to console (EMAIL_BACKEND = console).
    """
    accept_url = request.build_absolute_uri(
        f'/invitations/accept/{invitation.token}/'
    )
    
    subject = f'Invitation to join {invitation.project.name} on ShowStack'
    
    message = f"""
Hi there!

{invitation.invited_by.get_full_name() or invitation.invited_by.username} has invited you to collaborate on their ShowStack project:

Project: {invitation.project.name}
Role: {invitation.get_role_display()}
Show Date: {invitation.project.show_date}
Venue: {invitation.project.venue}

Click the link below to accept this invitation:
{accept_url}

This invitation will expire in 7 days.

If you don't have a ShowStack account yet, you'll be prompted to create one.

---
ShowStack - Professional Audio Production Management
"""
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@showstack.com',
        [invitation.email],
        fail_silently=False,
    )





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