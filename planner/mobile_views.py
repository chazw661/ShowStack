# planner/mobile_views.py
"""
Mobile views for ShowStack.
These views serve the mobile-optimized interface at /m/
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.http import require_http_methods
from .models import Project, ProjectMember, SoundvisionPrediction, ShowDay, MicSession, MicAssignment, CommBeltPack

from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json



def mobile_login(request):
    """
    Mobile-optimized login page.
    Sets longer session expiry for mobile devices.
    """
    if request.user.is_authenticated:
        return redirect('mobile:dashboard')
    
    error_message = None
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # Extended session for mobile
            # 30 days if "remember me", else 7 days
            if remember_me:
                request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
            else:
                request.session.set_expiry(60 * 60 * 24 * 7)   # 7 days
            
            # Redirect to next URL if provided, otherwise dashboard
            next_url = request.GET.get('next', 'mobile:dashboard')
            return redirect(next_url)
        else:
            error_message = "Invalid username or password"
    
    return render(request, 'mobile/login.html', {'error_message': error_message})


@require_http_methods(["GET", "POST"])
def mobile_logout(request):
    """Log out the user and redirect to mobile login."""
    logout(request)
    return redirect('mobile:login')


@login_required(login_url='mobile:login')
def mobile_dashboard(request):
    """
    Mobile dashboard showing user's projects.
    Displays:
    - Projects user owns
    - Projects shared with user (with role indication)
    """
    # Get projects user owns
    owned_projects = Project.objects.filter(
        owner=request.user
    ).order_by('-updated_at')
    
    # Get projects shared with user
    shared_memberships = ProjectMember.objects.filter(
        user=request.user
    ).select_related('project').order_by('-project__updated_at')
    
    # Build shared projects list with role info
    shared_projects = []
    for membership in shared_memberships:
        project = membership.project
        project.user_role = membership.role
        shared_projects.append(project)
    
    context = {
        'owned_projects': owned_projects,
        'shared_projects': shared_projects,
        'total_count': owned_projects.count() + len(shared_projects),
    }
    return render(request, 'mobile/dashboard.html', context)


@login_required(login_url='mobile:login')
def project_overview(request, project_id):
    """
    Mobile project overview - hub for all project modules.
    Shows quick stats and navigation to module views.
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check user has access to this project
    is_owner = project.owner == request.user
    membership = ProjectMember.objects.filter(
        project=project, 
        user=request.user
    ).first()
    
    if not is_owner and not membership:
        # User doesn't have access - redirect to dashboard
        return redirect('mobile:dashboard')
    
    # Determine user's role
    if is_owner:
        role = 'owner'
        can_edit = True
    else:
        role = membership.role if membership else None
        can_edit = role in ['owner', 'editor']
    
    # Gather module counts for quick reference
    # Using safe attribute access for flexibility
    module_stats = {
        'console_count': _safe_count(project, 'consoles'),
        'device_count': _safe_count(project, 'devices'),
        'amplifier_count': _safe_count(project, 'amplifiers'),
        'processor_count': _safe_count(project, 'processors'),
        'cable_count': _safe_count(project, 'pacables'),
        'mic_count': _safe_count(project, 'micassignments'),
        'comm_count': _safe_count(project, 'beltpacks'),
        'prediction_count': _safe_count(project, 'predictions'),
        'power_count': _safe_count(project, 'powerdistributors'),
    }
    
    # Define available modules for the navigation grid
    modules = [
        {
            'id': 'predictions',
            'name': 'Predictions',
            'icon': '📊',
            'count': module_stats['prediction_count'],
            'count_label': 'arrays',
            'url': None,  # Will be enabled in Phase 2
            'enabled': False,
        },
        {
            'id': 'mics',
            'name': 'Mic Tracker',
            'icon': '🎤',
            'count': module_stats['mic_count'],
            'count_label': 'mics',
            'url': None,  # Will be enabled in Phase 3
            'enabled': False,
        },
        {
            'id': 'comm',
            'name': 'COMM',
            'icon': '🎧',
            'count': module_stats['comm_count'],
            'count_label': 'packs',
            'url': None,  # Will be enabled in Phase 4
            'enabled': False,
        },
        {
            'id': 'rf',
            'name': 'RF',
            'icon': '📻',
            'count': 0,
            'count_label': '',
            'url': None,  # Will be enabled in Phase 6
            'enabled': False,
            'coming_soon': True,
        },
    ]
    
    context = {
        'project': project,
        'is_owner': is_owner,
        'role': role,
        'can_edit': can_edit,
        'modules': modules,
        **module_stats,
    }
    return render(request, 'mobile/project_overview.html', context)


def _safe_count(project, related_name):
    """
    Safely get count of related objects.
    Returns 0 if the related manager doesn't exist.
    """
    try:
        manager = getattr(project, related_name, None)
        if manager is not None and hasattr(manager, 'count'):
            return manager.count()
    except Exception:
        pass
    return 0



@login_required
def predictions_list(request, project_id):
    """
    List all Soundvision predictions for a project.
    Mobile-optimized view for system techs.
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check user has access
    if not user_can_access_project(request.user, project):
        return redirect('mobile:dashboard')
    
    predictions = SoundvisionPrediction.objects.filter(
        project=project
    ).prefetch_related('speaker_arrays__cabinets').order_by('-created_at')
    
    # Add computed stats to each prediction
    prediction_data = []
    for pred in predictions:
        array_count = pred.speaker_arrays.count()
        cabinet_count = sum(arr.cabinets.count() for arr in pred.speaker_arrays.all())
        prediction_data.append({
            'prediction': pred,
            'array_count': array_count,
            'cabinet_count': cabinet_count,
        })
    
    context = {
        'project': project,
        'prediction_data': prediction_data,
    }
    return render(request, 'mobile/predictions_list.html', context)


@login_required
def prediction_detail(request, project_id, prediction_id):
    """
    Show detailed view of a single prediction with all arrays.
    Optimized for walking the room during load-in.
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check user has access
    if not user_can_access_project(request.user, project):
        return redirect('mobile:dashboard')
    
    prediction = get_object_or_404(
        SoundvisionPrediction, 
        id=prediction_id, 
        project=project
    )
    
    # Get arrays with their cabinets, ordered logically
    arrays = prediction.speaker_arrays.prefetch_related(
        'cabinets'
    ).order_by('array_base_name', 'source_name')
    
    # Build array data with cabinet summaries
    array_data = []
    for array in arrays:
        cabinets = list(array.cabinets.all().order_by('position_number'))
        
        # Build cabinet summary (e.g., "8× K2 + 4× KS28")
        model_counts = {}
        for cab in cabinets:
            model = cab.speaker_model or 'Unknown'
            model_counts[model] = model_counts.get(model, 0) + 1
        
        summary_parts = [f"{count}× {model}" for model, count in model_counts.items()]
        cabinet_summary = " + ".join(summary_parts) if summary_parts else "No cabinets"
        
        # Check if this array has Panflex (KARA arrays)
        has_panflex = any(cab.panflex_setting for cab in cabinets)
        
        array_data.append({
            'array': array,
            'cabinets': cabinets,
            'cabinet_summary': cabinet_summary,
            'has_panflex': has_panflex,
        })
    
    context = {
        'project': project,
        'prediction': prediction,
        'array_data': array_data,
    }
    return render(request, 'mobile/prediction_detail.html', context)


def user_can_access_project(user, project):
    """Helper to check if user can access a project."""
    if project.owner == user:
        return True
    return ProjectMember.objects.filter(project=project, user=user).exists()





# ============================================
# PHASE 3: Mic Tracker Views
# ============================================

@login_required
def mic_tracker_days(request, project_id):
    """
    List all show days for mic tracking.
    """
    project = get_object_or_404(Project, id=project_id)
    
    if not user_can_access_project(request.user, project):
        return redirect('mobile:dashboard')
    
    days = ShowDay.objects.filter(project=project).order_by('date')
    
    # Add session count to each day
    day_data = []
    for day in days:
        session_count = day.sessions.count()
        mic_count = MicAssignment.objects.filter(session__day=day).count()
        day_data.append({
            'day': day,
            'session_count': session_count,
            'mic_count': mic_count,
        })
    
    context = {
        'project': project,
        'day_data': day_data,
    }
    return render(request, 'mobile/mic_tracker_days.html', context)


@login_required
def mic_tracker_sessions(request, project_id, day_id):
    """
    List all sessions for a specific show day.
    """
    project = get_object_or_404(Project, id=project_id)
    
    if not user_can_access_project(request.user, project):
        return redirect('mobile:dashboard')
    
    day = get_object_or_404(ShowDay, id=day_id, project=project)
    sessions = day.sessions.all().order_by('order', 'start_time')
    
    # Add assignment counts
    session_data = []
    for session in sessions:
        assignments = session.mic_assignments.all()
        total = assignments.count()
        assigned = assignments.exclude(presenter__isnull=True).count()
        session_data.append({
            'session': session,
            'total_mics': total,
            'assigned_mics': assigned,
        })
    
    context = {
        'project': project,
        'day': day,
        'session_data': session_data,
    }
    return render(request, 'mobile/mic_tracker_sessions.html', context)


@login_required
def mic_tracker_assignments(request, project_id, session_id):
    """
    Show all mic assignments for a session.
    Quick lookup: who has which mic?
    """
    project = get_object_or_404(Project, id=project_id)
    
    if not user_can_access_project(request.user, project):
        return redirect('mobile:dashboard')
    
    session = get_object_or_404(MicSession, id=session_id, day__project=project)
    assignments = session.mic_assignments.all().order_by('rf_number')
    
    context = {
        'project': project,
        'session': session,
        'day': session.day,
        'assignments': assignments,
    }
    return render(request, 'mobile/mic_tracker_assignments.html', context)






# ============================================
# PHASE 4: COMM Views
# ============================================

@login_required
def comm_list(request, project_id):
    """
    List all belt pack assignments for a project.
    Quick lookup: who has which pack, what channels.
    """
    project = get_object_or_404(Project, id=project_id)
    
    if not user_can_access_project(request.user, project):
        return redirect('mobile:dashboard')
    
    # Get belt packs grouped by system type
    wireless_packs = CommBeltPack.objects.filter(
        project=project,
        system_type='WIRELESS'
    ).select_related('position', 'name', 'channel_a', 'channel_b', 'channel_c', 'channel_d').order_by('bp_number')
    
    hardwired_packs = CommBeltPack.objects.filter(
        project=project,
        system_type='HARDWIRED'
    ).select_related('position', 'name', 'channel_a', 'channel_b', 'channel_c', 'channel_d').order_by('bp_number')
    
    context = {
        'project': project,
        'wireless_packs': wireless_packs,
        'hardwired_packs': hardwired_packs,
        'total_packs': wireless_packs.count() + hardwired_packs.count(),
        'checked_out': CommBeltPack.objects.filter(project=project, checked_out=True).count(),
    }
    return render(request, 'mobile/comm_list.html', context)


def comm_list(request, project_id):
    """
    List all belt pack assignments for a project.
    Quick lookup: who has which pack, what channels.
    """
    project = get_object_or_404(Project, id=project_id)
    
    if not user_can_access_project(request.user, project):
        return redirect('mobile:dashboard')
    
    # DEBUG - print to terminal
    print(f"DEBUG: Project ID = {project.id}, Name = {project.name}")
    print(f"DEBUG: Total packs in project: {CommBeltPack.objects.filter(project=project).count()}")
    
    # Get belt packs grouped by system type
    wireless_packs = CommBeltPack.objects.filter(
        project=project,
        system_type='WIRELESS'
    ).select_related('position', 'name').order_by('bp_number')
    
    hardwired_packs = CommBeltPack.objects.filter(
        project=project,
        system_type='HARDWIRED'
    ).select_related('position', 'name').order_by('bp_number')
    
    print(f"DEBUG: Wireless count = {wireless_packs.count()}")
    print(f"DEBUG: Hardwired count = {hardwired_packs.count()}")
    
    context = {
        'project': project,
        'wireless_packs': wireless_packs,
        'hardwired_packs': hardwired_packs,
        'total_packs': wireless_packs.count() + hardwired_packs.count(),
        'checked_out': CommBeltPack.objects.filter(project=project, checked_out=True).count(),
    }
    return render(request, 'mobile/comm_list.html', context)



# ============================================
# PHASE 5: Mobile Editing API
# ============================================

@login_required
@require_POST
def toggle_checkout(request, bp_id):
    """Toggle belt pack checked_out status."""
    try:
        bp = CommBeltPack.objects.get(id=bp_id)
        
        # Verify user has access to this project
        if not user_can_access_project(request.user, bp.project):
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        bp.checked_out = not bp.checked_out
        bp.save()
        
        return JsonResponse({
            'success': True,
            'checked_out': bp.checked_out,
            'bp_number': bp.bp_number
        })
    except CommBeltPack.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Belt pack not found'}, status=404)


@login_required
@require_POST
def toggle_micd(request, assignment_id):
    """Toggle mic assignment MIC'D status."""
    try:
        assignment = MicAssignment.objects.get(id=assignment_id)
        
        # Verify user has access
        if not user_can_access_project(request.user, assignment.session.day.project):
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        assignment.is_micd = not assignment.is_micd
        assignment.save()
        
        return JsonResponse({
            'success': True,
            'is_micd': assignment.is_micd,
            'rf_number': assignment.rf_number
        })
    except MicAssignment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Assignment not found'}, status=404)