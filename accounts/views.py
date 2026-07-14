import logging

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
from django.contrib.auth.models import Group, User
from django.db import transaction
from planner.crew import claim_pending_crew_memberships

logger = logging.getLogger(__name__)

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
            # D-11: form.save() + auto-claim are atomic. If claim raises, the
            # User row rolls back so the user can re-register cleanly.
            with transaction.atomic():
                user = form.save()
                # D-07: inline call (no Django signals). Rebinds pending CrewMember
                # rows and materializes ProjectMember rows for every project the
                # crew has been bulk-added to (D-09 via CrewProjectAdd).
                new_pms = claim_pending_crew_memberships(user)

            # D-10/D-11: email sends happen OUTSIDE the atomic block — a Resend
            # hiccup must not roll back the user account. Log + swallow per row.
            for pm in new_pms:
                try:
                    send_crew_added_email(pm, request)
                except Exception:
                    logger.exception(
                        "Crew-added email failed on register for %s",
                        getattr(pm.user, 'email', '<unknown>'),
                    )

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
        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url:
            return next_url
        return reverse_lazy('dashboard')

    def get_redirect_url(self):
        # Honor ?next= even when already logged in
        return self.request.GET.get('next') or super().get_redirect_url()
    
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
    
    # Phase 6: build owner_crews annotated for the additive 'Add your crew' panel.
    owner_crews_qs = (
        Crew.objects.filter(owner=request.user)
        .prefetch_related('crewmember_set__user')
        .order_by('name')
    )
    existing_member_ids = set(
        ProjectMember.objects.filter(project=project)
        .values_list('user_id', flat=True)
    )
    owner_crews = []
    for crew_obj in owner_crews_qs:
        members_payload = []
        eligible_count = 0
        pending_count = 0
        for cm in crew_obj.crewmember_set.all():
            if cm.user_id is None:
                members_payload.append({
                    'label': cm.email,
                    'is_already_member': False,
                    'is_pending': True,
                })
                # Pending-email rows do not create a ProjectMember now, but the
                # "Add this crew" action still records a CrewProjectAdd row so the
                # auto-claim hook (Plan 05) materializes their access on signup.
                # They must count toward being able to submit (issue #52).
                pending_count += 1
            else:
                is_member = cm.user_id in existing_member_ids
                members_payload.append({
                    'label': cm.user.get_full_name() or cm.user.username,
                    'is_already_member': is_member,
                    'is_pending': False,
                })
                if not is_member:
                    eligible_count += 1
        owner_crews.append({
            'id': crew_obj.id,
            'name': crew_obj.name,
            'eligible_count': eligible_count,
            'pending_count': pending_count,
            # issue #52: submittable when there are registered members to add
            # OR pending members whose future access needs a CrewProjectAdd row.
            'can_submit': (eligible_count + pending_count) > 0,
            'member_display': members_payload,
        })

    context = {
        'form': form,
        'project': project,
        'owner_crews': owner_crews,
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
        return redirect('/audiopatch/mic-tracker/')

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


# ==================== PHASE 6: TRUSTED CREW ROSTERS — CRUD ====================
from planner.models import Crew, CrewMember, CrewProjectAdd


@login_required
def crew_index(request):
    """List the logged-in user's crews (SPEC-06-R01).

    Empty state per D-12: page handles no-crews case with a 'Create your first crew' CTA.
    """
    crews = Crew.objects.filter(owner=request.user).order_by('name')
    return render(request, 'accounts/crew_index.html', {'crews': crews})


@login_required
def crew_create(request):
    """POST-only: create a new crew owned by the logged-in user (SPEC-06-R01)."""
    if request.method != 'POST':
        return redirect('crew_index')
    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, 'Crew name is required.')
        return redirect('crew_index')
    if Crew.objects.filter(owner=request.user, name=name).exists():
        messages.error(request, f'You already have a crew named "{name}".')
        return redirect('crew_index')
    crew = Crew.objects.create(owner=request.user, name=name)
    messages.success(request, f'Crew "{crew.name}" created.')
    return redirect('crew_detail', crew_id=crew.id)


@login_required
def crew_detail(request, crew_id):
    """Roster page for a single crew (SPEC-06-R01, R02, R06)."""
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can view this roster.')
        return redirect('crew_index')
    # Issue #58: Auto-convert pending crew members who have already registered
    # This fixes the "stuck pending" bug where users who registered still show as pending
    pending_cms = crew.crewmember_set.filter(user__isnull=True, email__isnull=False)
    for pending_cm in pending_cms:
        user_match = User.objects.filter(email__iexact=pending_cm.email).first()
        if user_match:
            active_entry = crew.crewmember_set.filter(user=user_match).first()
            if active_entry:
                # User already in crew - delete the duplicate pending entry
                logger.info(f"Issue #58: Deleting duplicate pending entry for {user_match.email} in crew {crew.name}")
                pending_cm.delete()
            else:
                # User has registered but isn't in crew - convert pending to active
                pending_cm.user = user_match
                pending_cm.email = None
                pending_cm.save(update_fields=['user', 'email'])
                logger.info(f"Issue #58: Auto-converted pending crew member {user_match.email} in crew {crew.name}")
    
    members = crew.crewmember_set.select_related('user').all()
    # Projects this owner can bulk-add the crew to (issue #52: let the owner
    # add the crew to a project straight from the roster page).
    owned_projects = Project.objects.filter(owner=request.user).order_by('-start_date')
    return render(request, 'accounts/crew_detail.html', {
        'crew': crew,
        'members': members,
        'role_choices': CrewMember.ROLES,
        'owned_projects': owned_projects,
        'has_members': members.exists(),
    })


@login_required
def crew_delete(request, crew_id):
    """POST-only: delete a crew and cascade to CrewMember + CrewProjectAdd.

    Per SPEC R7, this does NOT cascade to ProjectMember rows — Django ORM
    cascade only follows the declared FK paths (Crew -> CrewMember,
    Crew -> CrewProjectAdd). ProjectMember rows have no FK to Crew.
    """
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can delete this crew.')
        return redirect('crew_index')
    if request.method != 'POST':
        return redirect('crew_detail', crew_id=crew.id)
    crew_name = crew.name
    crew.delete()
    messages.success(request, f'Crew "{crew_name}" deleted. Existing project memberships were not affected.')
    return redirect('crew_index')


@login_required
def crew_member_add(request, crew_id):
    """POST-only: add a user (by username/email) OR a pending email to a crew (SPEC-06-R01, R02, R06).

    Form fields:
      - user_or_email (text): looked up case-insensitively against User.email then User.username.
        If neither match AND value contains '@', stored as a pending-email row (D-01).
        Otherwise renders an error.
      - default_role (choice): 'editor' or 'viewer' (D-02).

    D-08: email match is case-insensitive (__iexact) with whitespace strip.
    """
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can manage this roster.')
        return redirect('crew_index')
    if request.method != 'POST':
        return redirect('crew_detail', crew_id=crew.id)

    raw = (request.POST.get('user_or_email') or '').strip()
    default_role = request.POST.get('default_role') or 'editor'
    if default_role not in dict(CrewMember.ROLES):
        default_role = 'editor'
    if not raw:
        messages.error(request, 'Username or email is required.')
        return redirect('crew_detail', crew_id=crew.id)

    user_obj = (
        User.objects.filter(email__iexact=raw).first()
        or User.objects.filter(username__iexact=raw).first()
    )

    try:
        if user_obj is not None:
            if CrewMember.objects.filter(crew=crew, user=user_obj).exists():
                messages.error(request, f'{user_obj.username} is already in "{crew.name}".')
                return redirect('crew_detail', crew_id=crew.id)
            
            # Issue #58: Check if there's a pending CrewMember with the same email (D-03)
            # If found, convert it from pending email to actual user instead of creating a duplicate
            pending_cm = CrewMember.objects.filter(
                crew=crew,
                email__iexact=user_obj.email,
                user__isnull=True
            ).first()
            
            if pending_cm is not None:
                # D-01: UPDATE IN PLACE — convert pending email to user (preserves added_at)
                pending_cm.user = user_obj
                pending_cm.email = None
                pending_cm.default_role = default_role
                pending_cm.save(update_fields=['user', 'email', 'default_role'])
                cm = pending_cm
                messages.success(request, f'Converted {user_obj.email} to {user_obj.username} in "{crew.name}".')
            else:
                # Normal path: create new CrewMember for user
                cm = CrewMember.objects.create(crew=crew, user=user_obj, default_role=default_role)
                messages.success(request, f'Added {user_obj.username} to "{crew.name}".')
            
            # issue #49: notify at roster-add time (D-10 log + swallow).
            try:
                send_crew_roster_added_email(cm, request)
            except Exception:
                logger.exception("Crew-roster-added email failed for %s", user_obj.email)
        elif '@' in raw:
            if CrewMember.objects.filter(crew=crew, email__iexact=raw).exists():
                messages.error(request, f'{raw} is already pending in "{crew.name}".')
                return redirect('crew_detail', crew_id=crew.id)
            cm = CrewMember.objects.create(crew=crew, email=raw, default_role=default_role)
            messages.success(request, f'Added pending member {raw} to "{crew.name}" — will claim on signup.')
            # issue #49: nudge pending members to sign up now (D-10 log + swallow).
            try:
                send_crew_roster_signup_invite_email(cm, request)
            except Exception:
                logger.exception("Crew-roster-signup-invite email failed for %s", raw)
        else:
            messages.error(request, f'No user found matching "{raw}". To pre-invite, enter a full email address.')
    except Exception as e:
        # D-15 DB constraints (XOR check, partial uniques) surface as IntegrityError here.
        messages.error(request, f'Could not add member: {e}')
    return redirect('crew_detail', crew_id=crew.id)


@login_required
def crew_member_remove(request, crew_id, member_id):
    """POST-only: delete a single CrewMember row (SPEC-06-R07 no-cascade).

    SPEC R7 is enforced by the data model: CrewMember has no FK from
    ProjectMember, so deleting a CrewMember row never touches a
    ProjectMember row, regardless of whether the underlying user has
    previously been bulk-added to any of the crew's projects.
    """
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can manage this roster.')
        return redirect('crew_index')
    member = get_object_or_404(CrewMember, id=member_id, crew=crew)
    if request.method != 'POST':
        return redirect('crew_detail', crew_id=crew.id)
    label = member.user.username if member.user_id else f'{member.email} (pending)'
    member.delete()
    messages.success(
        request,
        f'Removed {label} from "{crew.name}". Their existing project memberships are unaffected — '
        'manage each project separately to remove project access.'
    )
    return redirect('crew_detail', crew_id=crew.id)


# ==================== PHASE 6: BULK-ADD CREW TO PROJECT ====================

def send_crew_roster_added_email(crew_member, request):
    """Notify an existing ShowStack user they were added to a crew roster (issue #49).

    Fires from crew_member_add when the resolved User FK is set. Access is
    NOT yet active — crew rosters are private; the second email lands when
    the owner bulk-adds the crew to a project. This one just lets them
    know they're on the roster so a future project add isn't a surprise.

    D-10: log + swallow. A Resend hiccup must not undo the CrewMember row.
    """
    import resend
    import os

    recipient = (crew_member.user.email or '').strip() if crew_member.user_id else ''
    if not recipient:
        return

    resend.api_key = os.environ.get('RESEND_API_KEY')
    owner = crew_member.crew.owner
    owner_label = owner.get_full_name() or owner.username

    subject = f"{owner_label} added you to the '{crew_member.crew.name}' crew"
    html = f"""
<h2>You're on a ShowStack crew</h2>
<p><strong>{owner_label}</strong> added you to their crew:</p>
<ul>
    <li><strong>Crew:</strong> {crew_member.crew.name}</li>
    <li><strong>Your default role:</strong> {crew_member.get_default_role_display()}</li>
</ul>
<p>No action required. When {owner_label} adds this crew to a project, your
access will activate automatically and you'll get another email with a link
to open the project.</p>
<hr>
<p><small>ShowStack — Professional Audio Production Management</small></p>
"""
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [recipient],
            "subject": subject,
            "html": html,
        })
        print(f"Crew-roster-added email sent to {recipient}")
    except Exception as e:
        # D-10: log + swallow — do NOT re-raise.
        print(f"Crew-roster-added email error: {e}")


def send_crew_roster_signup_invite_email(crew_member, request):
    """Notify a pending (no-account) email they were added to a crew roster (issue #49).

    Fires from crew_member_add for email-only rows (user=NULL). Nudges the
    recipient to sign up now so a later bulk-add auto-activates their
    ProjectMember via the auto-claim hook in marketing/views.register.

    D-10: log + swallow.
    """
    import resend
    import os
    from django.urls import reverse

    resend.api_key = os.environ.get('RESEND_API_KEY')
    signup_url = request.build_absolute_uri(reverse('register'))
    owner = crew_member.crew.owner
    owner_label = owner.get_full_name() or owner.username

    subject = f"{owner_label} added you to the '{crew_member.crew.name}' crew on ShowStack"
    html = f"""
<h2>You've been added to a ShowStack crew</h2>
<p><strong>{owner_label}</strong> added you to their crew:</p>
<ul>
    <li><strong>Crew:</strong> {crew_member.crew.name}</li>
    <li><strong>Your default role:</strong> {crew_member.get_default_role_display()}</li>
</ul>
<p>You don't have a ShowStack account yet. Sign up with <strong>{crew_member.email}</strong>
so when {owner_label} adds this crew to a project, your access activates
automatically:</p>
<p><a href="{signup_url}" style="display:inline-block;padding:12px 24px;background:#4a9eff;color:white;text-decoration:none;border-radius:6px;margin:20px 0;">
Sign up for ShowStack</a></p>
<p><small>Use the email address above when registering so your access connects automatically.</small></p>
<hr>
<p><small>ShowStack — Professional Audio Production Management</small></p>
"""
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [crew_member.email],
            "subject": subject,
            "html": html,
        })
        print(f"Crew-roster-signup-invite email sent to {crew_member.email}")
    except Exception as e:
        # D-10: log + swallow — do NOT re-raise.
        print(f"Crew-roster-signup-invite email error: {e}")


def send_crew_added_email(project_member, request):
    """Inform a user they have been added to a project via crew bulk-add (SPEC-06-R04).

    NO accept_url token per SPEC R4 — access is already active. The 'Open project'
    button reverses to set_project (the canonical land-inside-project URL used
    elsewhere in the codebase).

    D-10: log + swallow exceptions. The bulk-add contract is 'ProjectMember rows
    exist' — one bad email must not undo a successful crew-add. Resend dashboard
    surfaces per-recipient delivery failures. Mirrors send_access_approved_email
    (NOT send_invitation_email which re-raises).
    """
    import resend
    import os
    from django.urls import reverse

    resend.api_key = os.environ.get('RESEND_API_KEY')
    project_url = request.build_absolute_uri(
        reverse('set_project', args=[project_member.project.id])
    )
    owner = project_member.project.owner
    owner_label = owner.get_full_name() or owner.username

    subject = (
        f"{owner_label} added you to "
        f"{project_member.project.name} on ShowStack"
    )
    html = f"""
<h2>You've been added to a ShowStack project</h2>
<p><strong>{owner_label}</strong> added you to their crew on:</p>
<ul>
    <li><strong>Project:</strong> {project_member.project.name}</li>
    <li><strong>Your role:</strong> {project_member.get_role_display()}</li>
</ul>
<p><a href="{project_url}" style="display:inline-block;padding:12px 24px;background:#4a9eff;color:white;text-decoration:none;border-radius:6px;margin:20px 0;">
Open project</a></p>
<p><small>No action required — your access is already active.</small></p>
<hr>
<p><small>ShowStack — Professional Audio Production Management</small></p>
"""
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [project_member.user.email],
            "subject": subject,
            "html": html,
        })
        print(f"Crew-added email sent to {project_member.user.email}")
    except Exception as e:
        # D-10: log + swallow — do NOT re-raise.
        print(f"Crew-added email error: {e}")


def send_crew_invite_to_signup_email(crew_member, project, request):
    """Email a pending (unregistered) crew member at bulk-add time.

    Pending CrewMembers (user=NULL) have an email but no ShowStack account.
    When the project owner bulk-adds the crew to a project, fire this email
    so the recipient knows they were added and can sign up. After they
    register, the auto-claim hook in marketing/views.register materializes
    the ProjectMember row automatically.

    D-10: log + swallow — mirrors send_crew_added_email.
    """
    import resend
    import os
    from django.urls import reverse

    resend.api_key = os.environ.get('RESEND_API_KEY')
    signup_url = request.build_absolute_uri(reverse('register'))
    owner = project.owner
    owner_label = owner.get_full_name() or owner.username

    subject = (
        f"{owner_label} added you to "
        f"{project.name} on ShowStack"
    )
    html = f"""
<h2>You've been added to a ShowStack project</h2>
<p><strong>{owner_label}</strong> added you to their crew on:</p>
<ul>
    <li><strong>Project:</strong> {project.name}</li>
    <li><strong>Your role:</strong> {crew_member.get_default_role_display()}</li>
</ul>
<p>You don't have a ShowStack account yet. Sign up with <strong>{crew_member.email}</strong> and your project access will activate automatically:</p>
<p><a href="{signup_url}" style="display:inline-block;padding:12px 24px;background:#4a9eff;color:white;text-decoration:none;border-radius:6px;margin:20px 0;">
Sign up for ShowStack</a></p>
<p><small>Use the email address above when registering so your access connects automatically.</small></p>
<hr>
<p><small>ShowStack — Professional Audio Production Management</small></p>
"""
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [crew_member.email],
            "subject": subject,
            "html": html,
        })
        print(f"Crew-invite-to-signup email sent to {crew_member.email}")
    except Exception as e:
        # D-10: log + swallow — do NOT re-raise.
        print(f"Crew-invite-to-signup email error: {e}")


@login_required
def bulk_add_crew(request, project_id, crew_id):
    """Bulk-add an entire crew to a project (SPEC-06-R03, R04, R05, R08; D-06, D-09, D-10).

    POST-only. Creates ProjectMember rows for every CrewMember with a User FK
    that is not already a member of the project. Sends one confirmation email
    per new row. Records a CrewProjectAdd row so the Plan 05 auto-claim hook
    can materialize ProjectMember rows for future registrations matching
    pending-email CrewMember rows.

    Per Pitfall 2: uses .save() (via ProjectMember.objects.create) rather than
    bulk_create so auto_now_add fires for invited_at.
    """
    # issue #52: the crew_detail "Add to a Project" form posts to the placeholder
    # project id 0 and carries the real id in project_select (for the no-JS case).
    if project_id == 0:
        project_id = request.POST.get('project_select') or 0
    project = get_object_or_404(Project, id=project_id)
    # Mirror accounts/views.py:128-131 — project owner gate.
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can add a crew.')
        return redirect('dashboard')

    crew = get_object_or_404(Crew, id=crew_id, owner=request.user)

    if request.method != 'POST':
        return redirect('invite_user', project_id=project.id)

    # Resolve crew members with a User FK. Pending-email rows (user=NULL) are
    # skipped here; they materialize via the auto-claim hook in register()
    # (Plan 05) once the email-holder signs up.
    resolved = list(
        crew.crewmember_set.filter(user__isnull=False).select_related('user')
    )

    # SPEC R8: single upfront dedupe query.
    existing_user_ids = set(
        ProjectMember.objects.filter(
            project=project,
            user_id__in=[m.user_id for m in resolved],
        ).values_list('user_id', flat=True)
    )

    to_add = [m for m in resolved if m.user_id not in existing_user_ids]
    already = len(resolved) - len(to_add)

    # Pitfall 2: .save() loop (via .create) so auto_now_add fires for invited_at.
    # Crews are 1-10 members per SPEC Constraint — sync is fine.
    new_rows = []
    for m in to_add:
        pm = ProjectMember.objects.create(
            project=project,
            user=m.user,
            role=m.default_role,
            invited_by=request.user,
        )
        new_rows.append(pm)

    # D-09: record bulk-add so the auto-claim hook (Plan 05) knows which
    # projects to materialize for newly-registered crew members.
    CrewProjectAdd.objects.get_or_create(crew=crew, project=project)

    # D-10: log + swallow email failures (per-recipient, defensive).
    for pm in new_rows:
        try:
            send_crew_added_email(pm, request)
        except Exception:
            logger.exception(
                "Crew-added email failed for %s",
                getattr(pm.user, 'email', '<unknown>'),
            )

    # Pending crew members (user=NULL) — fire signup invite so they know
    # they were added and can sign up to materialize their access. After
    # registration, the auto-claim hook in marketing/views.register creates
    # their ProjectMember row automatically.
    pending = list(crew.crewmember_set.filter(user__isnull=True))
    for cm in pending:
        try:
            send_crew_invite_to_signup_email(cm, project, request)
        except Exception:
            logger.exception(
                "Crew-invite-to-signup email failed for %s",
                cm.email,
            )

    pending_count = len(pending)
    pending_clause = (
        f" {pending_count} pending member(s) emailed a signup invite."
        if pending_count else ""
    )
    messages.success(
        request,
        f"Added {len(to_add)} members from {crew.name} to {project.name}; "
        f"{already} were already on this project."
        f"{pending_clause}"
    )
    # issue #52: when the owner adds the crew from the crew roster page, return
    # them there instead of the project invite page.
    if request.POST.get('return_to') == 'crew_detail':
        return redirect('crew_detail', crew_id=crew.id)
    return redirect('invite_user', project_id=project.id)