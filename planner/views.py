from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction, IntegrityError
from django.db.models import Max, F
from django.utils import timezone
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from datetime import datetime, date
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
import json
from decimal import Decimal
from django.db.models import Sum, Q
from django.contrib import messages
from django.core.files.storage import default_storage
from django.utils.text import slugify
from collections import defaultdict
from .models import SoundvisionPrediction, ShowDay
from .soundvision_parser import import_soundvision_prediction
from .models import SoundvisionPrediction, ShowDay, SpeakerArray
import csv
from django.db.models import Count, Q
from planner.utils.pdf_exports.console_pdf import export_console_pdf
from planner.models import Console
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from planner.models import Presenter
import csv
from django.shortcuts import redirect
from .models import Project
from .models import CommConfig, CommConfigPartyline, CommConfigRole, CommConfigKeyset, CommConfigRoleset, CommConfigSession, CommConfigPortAssignment, CommConfigDanteChannel, CommCrewName, AudioChecklistTemplate, AudioChecklistTemplateTask, CommConfigNetworkPort
from .models import Amp, AmpDivider, Location, AmpLocation
import hashlib
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable, KeepTogether, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from .models import AudioChecklist, AudioChecklistTask, Project, ProjectMember
from .models import ShowDay, MicSession, MicAssignment, MicShowInfo
import json as _json
from django.http import JsonResponse

from django.views.decorators.csrf import csrf_exempt  # not needed if using CSRF token in headers






# Model imports - all together
from .models import (
    Console, ConsoleInput,
    GalaxyProcessor, GalaxyInput, GalaxyOutput,
    P1Processor, P1Input, P1Output,
    CommBeltPack, CommChannel, CommPosition, CommCrewName,
    Device, Device, DeviceInput, DeviceOutput,
    SystemProcessor, Amp, AmpChannel, Location, AmpLocation, PACableSchedule, PAZone,
    ShowDay, MicSession, MicAssignment, MicShowInfo, MicGroup, PresenterSlot, PowerDistributionPlan, AmplifierProfile,
    AmplifierAssignment,
    MultitrackSession, MultitrackTrack,
    MultitrackTemplate, MultitrackTemplateSlot,
    SignalFlowDiagram,
    ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput,
)
from .forms import MultitrackSessionForm, ConsoleCsvUploadForm
from .models import ConsoleImport
from planner.utils.console_csv_import import (
    parse_upload,
    is_default_row,
    SECTION_TARGET_MAP,
    OUT_OF_SCOPE_SECTIONS,
)

def console_detail(request, console_id):
    console = get_object_or_404(Console, pk=console_id)

    InputFormSet = modelformset_factory(
        ConsoleInput,
        fields=[
            "output", "dante_number", "input_ch", "source", "group",
            "dca", "mute", "direct_out", "omni_in", "omni_out"
        ],
        extra=10,
        can_delete=True
    )

    if request.method == "POST":
        formset = InputFormSet(request.POST, queryset=ConsoleInput.objects.filter(console=console))
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.console = console
                instance.save()
            for obj in formset.deleted_objects:
                obj.delete()
    else:
        formset = InputFormSet(queryset=ConsoleInput.objects.filter(console=console))

        consoles = Console.objects.filter(project=project).order_by('name')

    return render(request, "planner/console_detail.html", {
        "formset": formset,
        "console": console,
        "consoles": consoles
    })
    




    




#-----Source Hardware Options (inline add for Console Input dropdown)----


@login_required
@require_POST
def add_source_hardware_option(request):
    from .models import SourceHardwareOption, Project, ProjectMember

    user = request.user
    if not user.is_superuser:
        owns_project = Project.objects.filter(owner=user).exists()
        is_editor = ProjectMember.objects.filter(user=user, role='editor').exists()
        if not (owns_project or is_editor):
            return JsonResponse({'error': 'Permission denied.'}, status=403)

    label = (request.POST.get('label') or '').strip()
    if not label:
        return JsonResponse({'error': 'Label is required.'}, status=400)
    if len(label) > 50:
        return JsonResponse({'error': 'Label must be 50 characters or fewer.'}, status=400)

    option, created = SourceHardwareOption.objects.get_or_create(
        label=label,
        defaults={'sort_order': 9999},
    )
    return JsonResponse({'id': option.id, 'label': option.label, 'created': created})


#-----Mic Tracer----



@staff_member_required
def p1_processor_export(request, p1_processor_id):
    """Export P1 configuration as JSON or CSV"""
    p1 = get_object_or_404(P1Processor, pk=p1_processor_id)
    format_type = request.GET.get('format', 'json')
    
    if format_type == 'csv':
        # Export as CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="p1_config_{p1.id}.csv"'
        
        writer = csv.writer(response)
        
        # Write inputs
        writer.writerow(['P1 INPUTS'])
        writer.writerow(['Type', 'Channel', 'Label'])

        for inp in p1.inputs.all():
            writer.writerow([
                inp.get_input_type_display(),
                inp.channel_number,
                inp.label,
            ])
        
        writer.writerow([])  # Empty row
        
        # Write outputs
        writer.writerow(['P1 OUTPUTS'])
        writer.writerow(['Type', 'Channel', 'Label', 'Assigned Bus'])
        
        for out in p1.outputs.all():
            writer.writerow([
                out.get_output_type_display(),
                out.channel_number,
                out.label,
                f"Bus {out.assigned_bus}" if out.assigned_bus else ''
            ])
        
        return response
    
    else:
        # Export as JSON
        export_data = {
            'processor': {
                'name': p1.system_processor.name,
                'location': p1.system_processor.location.name,
                'ip_address': str(p1.system_processor.ip_address),
                'notes': p1.notes
            },
            'inputs': [],
            'outputs': []
        }
        
        # Export inputs
        for inp in p1.inputs.all():
            export_data['inputs'].append({
                'type': inp.input_type,
                'type_display': inp.get_input_type_display(),
                'channel': inp.channel_number,
                'label': inp.label,
            })
        
        # Export outputs
        for out in p1.outputs.all():
            output_data = {
                'type': out.output_type,
                'type_display': out.get_output_type_display(),
                'channel': out.channel_number,
                'label': out.label,
                'assigned_bus': out.assigned_bus
            }
            export_data['outputs'].append(output_data)
        
        response = JsonResponse(export_data, json_dumps_params={'indent': 2})
        response['Content-Disposition'] = f'attachment; filename="p1_config_{p1.id}.json"'

        return response

def console_pdf_export(request, console_id):
    """Export a console configuration as PDF"""
    console = get_object_or_404(Console, id=console_id)
    return export_console_pdf(console)

        
        


@staff_member_required
def p1_processor_summary(request, p1_processor_id):
    """Display a summary view of P1 configuration"""
    p1 = get_object_or_404(P1Processor, pk=p1_processor_id)
    
    context = {
        'p1': p1,
        'analog_inputs': p1.inputs.filter(input_type='ANALOG'),
        'aes_inputs': p1.inputs.filter(input_type='AES'),
        'avb_inputs': p1.inputs.filter(input_type='AVB'),
        'analog_outputs': p1.outputs.filter(output_type='ANALOG'),
        'aes_outputs': p1.outputs.filter(output_type='AES'),
        'avb_outputs': p1.outputs.filter(output_type='AVB'),
    }
    
    return render(request, 'planner/p1_processor_summary.html', context)



#-------Galaxy Processor View----

@staff_member_required
def galaxy_processor_export(request, galaxy_processor_id):
    """Export GALAXY configuration as JSON or CSV"""
    galaxy = get_object_or_404(GalaxyProcessor, pk=galaxy_processor_id)
    format_type = request.GET.get('format', 'json')
    
    if format_type == 'csv':
        # Export as CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="galaxy_config_{galaxy.id}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Meyer GALAXY Processor Configuration'])
        writer.writerow([f'Processor: {galaxy.system_processor.name}'])
        writer.writerow([f'Location: {galaxy.system_processor.location.name}'])
        writer.writerow([f'IP Address: {galaxy.system_processor.ip_address}'])
        writer.writerow([])
        
        # Write inputs
        writer.writerow(['GALAXY INPUTS'])
        writer.writerow(['Type', 'Channel', 'Label'])

        for inp in galaxy.inputs.all():
            writer.writerow([
                inp.get_input_type_display(),
                inp.channel_number,
                inp.label,
            ])
        
        writer.writerow([])  # Empty row
        
        # Write outputs
        writer.writerow(['GALAXY OUTPUTS'])
        writer.writerow(['Type', 'Channel', 'Label', 'Assigned Bus', 'Destination'])
        
        for out in galaxy.outputs.all():
            writer.writerow([
                out.get_output_type_display(),
                out.channel_number,
                out.label,
                f"Bus {out.assigned_bus}" if out.assigned_bus else '',
                out.destination
            ])
        
        return response
    
    else:
        # Export as JSON
        export_data = {
            'processor_type': 'Meyer GALAXY',
            'processor': {
                'name': galaxy.system_processor.name,
                'location': galaxy.system_processor.location.name,
                'ip_address': str(galaxy.system_processor.ip_address),
                'notes': galaxy.notes
            },
            'inputs': [],
            'outputs': []
        }
        
        # Export inputs
        for inp in galaxy.inputs.all():
            export_data['inputs'].append({
                'type': inp.input_type,
                'type_display': inp.get_input_type_display(),
                'channel': inp.channel_number,
                'label': inp.label,
            })
        
        # Export outputs
        for out in galaxy.outputs.all():
            output_data = {
                'type': out.output_type,
                'type_display': out.get_output_type_display(),
                'channel': out.channel_number,
                'label': out.label,
                'assigned_bus': out.assigned_bus,
                'destination': out.destination
            }
            export_data['outputs'].append(output_data)
        
        response = JsonResponse(export_data, json_dumps_params={'indent': 2})
        response['Content-Disposition'] = f'attachment; filename="galaxy_config_{galaxy.id}.json"'
        return response


@staff_member_required
def galaxy_processor_summary(request, galaxy_processor_id):
    """Display a summary view of GALAXY configuration"""
    galaxy = get_object_or_404(GalaxyProcessor, pk=galaxy_processor_id)
    
    context = {
        'galaxy': galaxy,
        'analog_inputs': galaxy.inputs.filter(input_type='ANALOG'),
        'aes_inputs': galaxy.inputs.filter(input_type='AES'),
        'avb_inputs': galaxy.inputs.filter(input_type='AVB'),
        'analog_outputs': galaxy.outputs.filter(output_type='ANALOG'),
        'aes_outputs': galaxy.outputs.filter(output_type='AES'),
        'avb_outputs': galaxy.outputs.filter(output_type='AVB'),
    }
    
    return render(request, 'planner/galaxy_processor_summary.html', context)






            #-------COMMS Page--------


 # Add these to your planner/views.py file



from .models import CommBeltPack, CommChannel, CommPosition, CommCrewName

@staff_member_required
def get_next_bp_number(request):
    """Get the next available belt pack number for a specific system type"""
    system_type = request.GET.get('system_type', 'WIRELESS')
    max_bp = CommBeltPack.objects.filter(
        system_type=system_type
    ).aggregate(Max('bp_number'))['bp_number__max']
    next_bp = (max_bp or 0) + 1
    return JsonResponse({'next_bp_number': next_bp})


@staff_member_required
def export_comm_assignments(request):
    """Export belt pack assignments to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="comm_assignments.csv"'
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow([
        'BP #', 'Position', 'Name', 'Headset', 
        'CH A', 'CH B', 'CH C', 'CH D',
        'Audio PGM', 'Group', 'Checked Out', 'Notes'
    ])
    
    # Write data
    for bp in CommBeltPack.objects.all().order_by('bp_number'):
        writer.writerow([
            bp.bp_number,
            bp.position,
            bp.name,
            bp.get_headset_display() if bp.headset else '',
            str(bp.channel_a) if bp.channel_a else '',
            str(bp.channel_b) if bp.channel_b else '',
            str(bp.channel_c) if bp.channel_c else '',
            str(bp.channel_d) if bp.channel_d else '',
            'Yes' if bp.audio_pgm else 'No',
            bp.get_group_display() if bp.group else '',
            'Yes' if bp.checked_out else 'No',
            bp.notes
        ])
    
    return response


@staff_member_required
def comm_channel_matrix(request):
    """Display a matrix view of all belt pack channel assignments"""
    
    
    belt_packs = CommBeltPack.objects.all().order_by('bp_number')
    channels = CommChannel.objects.all().order_by('order')
    
    # Build matrix data
    matrix = []
    for bp in belt_packs:
        row = {
            'bp': bp,
            'channels': []
        }
        for channel in channels:
            assigned = False
            assignment_type = ''
            
            if bp.channel_a == channel:
                assigned = True
                assignment_type = 'A'
            elif bp.channel_b == channel:
                assigned = True
                assignment_type = 'B'
            elif bp.channel_c == channel:
                assigned = True
                assignment_type = 'C'
            elif bp.channel_d == channel:
                assigned = True
                assignment_type = 'D'
            
            row['channels'].append({
                'assigned': assigned,
                'type': assignment_type
            })
        matrix.append(row)
    
    context = {
        'channels': channels,
        'matrix': matrix,
        'title': 'Comm Channel Matrix'
    }
    
    return render(request, 'admin/planner/comm_matrix.html', context)


@staff_member_required
def import_comm_positions(request):
    """Import positions from a text list"""
    if request.method == 'POST':
        positions_text = request.POST.get('positions', '')
        lines = positions_text.strip().split('\n')
        
        created_count = 0
        for i, line in enumerate(lines, 1):
            position_name = line.strip()
            if position_name:
                _, created = CommPosition.objects.get_or_create(
                    name=position_name,
                    defaults={'order': i * 10}
                )
                if created:
                    created_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'Created {created_count} new positions'
        })
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@staff_member_required
def import_comm_names(request):
    """Import crew names from a text list"""
    if request.method == 'POST':
        names_text = request.POST.get('names', '')
        lines = names_text.strip().split('\n')
        
        created_count = 0
        for line in lines:
            crew_name = line.strip()
            if crew_name:
                _, created = CommCrewName.objects.get_or_create(name=crew_name)
                if created:
                    created_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'Created {created_count} new crew names'
        })
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})      


#-----Comm Dashboard View------

# planner/views.py (create this file if it doesn't exist)



class SystemDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        context = {
            # System Status Overview
            'console_count': Console.objects.count(),
            'device_count': Device.objects.count(),
            'total_inputs': sum(d.input_count for d in Device.objects.all()),
            'total_outputs': sum(d.output_count for d in Device.objects.all()),
            
            # Processor Status
            'p1_processors': SystemProcessor.objects.filter(device_type='P1').count(),
            'galaxy_processors': SystemProcessor.objects.filter(device_type='GALAXY').count(),
            
            # COMM System Status
            'wireless_beltpacks': CommBeltPack.objects.filter(system_type='WIRELESS').count(),
            'hardwired_beltpacks': CommBeltPack.objects.filter(system_type='HARDWIRED').count(),
            'checked_out': CommBeltPack.objects.filter(checked_out=True).count(),
            'positions_configured': CommPosition.objects.count() > 0,
            
            # Amp Status
            'total_amps': Amp.objects.count(),
            'total_amp_channels': sum(a.amp_model.channel_count for a in Amp.objects.select_related('amp_model')),
            
            # Cable Statistics
            'total_cable_runs': PACableSchedule.objects.count(),
            'total_cable_length': sum(c.total_cable_length for c in PACableSchedule.objects.all()),
            
            # Setup Warnings
            'needs_comm_setup': CommPosition.objects.count() == 0,
            'no_devices': Device.objects.count() == 0,
        }
        return render(request, 'planner/dashboard.html', context)
    


    #--------Mic Tracker Sheet---

   

@staff_member_required
def mic_tracker_view(request):
    """Main mic tracker view with spreadsheet-like interface"""
    
    # Get filter parameters
    day_id = request.GET.get('day')
    session_id = request.GET.get('session')
    date_filter = request.GET.get('date')
    
    # Get show info
    show_info, created = MicShowInfo.objects.get_or_create(
    project=request.current_project,
    defaults={
        'default_mics_per_session': 16,
        'default_session_duration': 60
    }
)
    
    # Build queryset
    if day_id:
        days = ShowDay.objects.filter(id=day_id, project=request.current_project)
    elif date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            days = ShowDay.objects.filter(date=filter_date, project=request.current_project)
        except ValueError:
            days = ShowDay.objects.filter(project=request.current_project)
    else:
        days = ShowDay.objects.filter(project=request.current_project)

    if request.current_project:
        request.session['current_project'] = request.current_project.id
        request.session.modified = True

        
    # Custom prefetch to order shared presenters by through table ID

    from django.db.models import Prefetch
    days = days.prefetch_related(
        Prefetch(
            'sessions__mic_assignments',
            queryset=MicAssignment.objects.select_related('group').prefetch_related(
                'presenter_slots__presenter',
            ).distinct()
        ),
    ).order_by('date')


    
    # Organize sessions by columns for display
    days_data = []
    for day in days:
        sessions = day.sessions.all()
        
        
        days_data.append({
            'day': day,
            'sessions': sessions
        })
    
    # CHECK PERMISSIONS - Add this section
    from planner.models import Project, ProjectMember
    
    is_viewer = False
    if not request.user.is_superuser:
        # Check if user is viewer for any projects with ShowDays
        # For simplicity, check if user has ANY viewer memberships
        viewer_memberships = ProjectMember.objects.filter(
            user=request.user,
            role='viewer'
        )
        
        # If user has viewer memberships but no editor/owner roles, they're read-only
        if viewer_memberships.exists():
            editor_owner_memberships = ProjectMember.objects.filter(
                user=request.user,
                role='editor'
            ).exists()
            
            owns_projects = Project.objects.filter(owner=request.user).exists()
            
            # If ONLY viewer (no editor roles or owned projects), set read-only
            if not editor_owner_memberships and not owns_projects:
                is_viewer = True
    
    # This is inside the mic_tracker_view function
    context = {
        'show_info': show_info,
        'days_data': days_data,
        'current_date': date.today(),
        'mic_types': MicAssignment.MIC_TYPES,
        'session_types': MicSession.SESSION_TYPES,
        'is_viewer': is_viewer,  # ADD THIS LINE
    }  # ← This closing brace needs to be indented with 4 spaces, not at column 0
    
    return render(request, 'planner/mic_tracker.html', context) 



@staff_member_required
@require_POST
def bulk_update_mics(request):
    """AJAX endpoint for bulk mic updates"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        action = data.get('action')
        
        session = get_object_or_404(MicSession, id=session_id)
        
        with transaction.atomic():
            if action == 'clear_all':
                session.mic_assignments.update(
                    is_micd=False,
                    is_d_mic=False,
                    presenter_name='',
                    mic_type='',
                    shared_presenters=None
                )
            elif action == 'check_all_micd':
                session.mic_assignments.update(is_micd=True)
            elif action == 'uncheck_all_micd':
                session.mic_assignments.update(is_micd=False)
            elif action == 'check_all_dmic':
                session.mic_assignments.update(is_d_mic=True)
            elif action == 'uncheck_all_dmic':
                session.mic_assignments.update(is_d_mic=False)
            else:
                return JsonResponse({'success': False, 'error': 'Invalid action'})
        
        session_stats = session.get_mic_usage_stats()
        day_stats = session.day.get_all_mics_status()
        
        return JsonResponse({
            'success': True,
            'session_stats': session_stats,
            'day_stats': day_stats
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Replace these functions in planner/views.py
# Search for each function name and replace the entire function

from planner.models import Presenter  # Add this to your imports at the top

@staff_member_required
def export_mic_tracker(request):
    """Export mic tracker data as CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="mic_tracker_{date.today()}.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    show_info, created = MicShowInfo.objects.get_or_create(
    project=request.current_project,
    defaults={
        'default_mics_per_session': 16,
        'default_session_duration': 60
    }
)
    writer.writerow(['Mic Assignment List'])
    writer.writerow(['Show Name:', show_info.show_name])
    writer.writerow(['Venue:', show_info.venue_name])
    writer.writerow(['Ballroom:', show_info.ballroom_name])
    writer.writerow(['Duration:', show_info.duration_display])
    writer.writerow([])
    
    # Write days and sessions
    for day in ShowDay.objects.all().order_by('date'):
        writer.writerow([f"Day: {day}"])
        
        for session in day.sessions.all().order_by('order'):
            writer.writerow([f"Session: {session.name}"])
            writer.writerow(['RF#', 'Type', 'Presenter', "MIC'D", 'D-MIC', 'Notes'])
            
            for assignment in session.mic_assignments.all().order_by('rf_number'):
                # Get presenter display
                presenter_name = assignment.presenter.name if assignment.presenter else ''
                
                # Add shared presenters
                shared_names = [p.name for p in assignment.shared_presenters.all()]
                if shared_names:
                    presenter_display = f"{presenter_name} +{len(shared_names)}"
                else:
                    presenter_display = presenter_name
                
                writer.writerow([
                    assignment.rf_number,
                    assignment.mic_type,
                    presenter_display,
                    'Yes' if assignment.is_micd else 'No',
                    'Yes' if assignment.is_d_mic else 'No',
                    assignment.notes or ''
                ])
            
            writer.writerow([])
    
    return response

@staff_member_required
@require_POST
def bulk_update_mics(request):
    """AJAX endpoint for bulk mic updates"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        action = data.get('action')
        
        session = get_object_or_404(MicSession, id=session_id)
        
        with transaction.atomic():
            if action == 'clear_all':
                for assignment in session.mic_assignments.all():
                    assignment.presenter = None
                    assignment.is_micd = False
                    assignment.is_d_mic = False
                    assignment.mic_type = ''
                    assignment.shared_presenters.clear()
                    assignment.save()
            elif action == 'check_all_micd':
                session.mic_assignments.update(is_micd=True)
            elif action == 'uncheck_all_micd':
                session.mic_assignments.update(is_micd=False)
            elif action == 'check_all_dmic':
                session.mic_assignments.update(is_d_mic=True)
            elif action == 'uncheck_all_dmic':
                session.mic_assignments.update(is_d_mic=False)
            else:
                return JsonResponse({'success': False, 'error': 'Invalid action'})
        
        session_stats = session.get_mic_usage_stats()
        day_stats = session.day.get_all_mics_status()
        
        return JsonResponse({
            'success': True,
            'session_stats': session_stats,
            'day_stats': day_stats
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
# Add this function to views.py (around line 628, after bulk_update_mics)

@staff_member_required
@require_POST
def duplicate_session(request):
    """AJAX endpoint to duplicate a session's mic assignments to another session"""
    try:
        data = json.loads(request.body)
        source_session_id = data.get('source_session_id')
        target_session_id = data.get('target_session_id')
        
        source_session = get_object_or_404(MicSession, id=source_session_id)
        target_session = get_object_or_404(MicSession, id=target_session_id)
        
        with transaction.atomic():
            # Clear target session first if requested
            if data.get('clear_target', False):
                target_session.mic_assignments.all().delete()
                target_session.num_mics = source_session.num_mics
                target_session.save()
                target_session.create_mic_assignments()
            
            # Copy assignments
            source_session.duplicate_to_session(target_session)
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully duplicated {source_session.name} to {target_session.name}'
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})  
    

# ── Add/replace these two functions in planner/views.py ──────────────────────
# Place them near your other mic tracker views.
#
# Required imports (add to top of views.py if not already present):
#   import csv
#   import os
#   from datetime import date
#   from io import BytesIO
#   from django.http import HttpResponse
#   from reportlab.lib.pagesizes import letter, landscape
#   from reportlab.lib import colors
#   from reportlab.lib.units import inch
#   from reportlab.platypus import (
#       SimpleDocTemplate, Table, TableStyle, Paragraph,
#       Spacer, Image, HRFlowable, KeepTogether
#   )
#   from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
#   from reportlab.lib.enums import TA_LEFT, TA_CENTER
#
# Install reportlab if needed:  pip install reportlab

def delete_session(request):
    """AJAX endpoint to delete a mic session"""
    try:
        data = json.loads(request.body)
        session_id = data.get("session_id")
        session = get_object_or_404(MicSession, id=session_id)
        session.delete()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

@staff_member_required
@staff_member_required
def export_mic_tracker(request):
    """Export mic tracker data as CSV — current project, all days/sessions."""
    project_id = request.session.get('current_project_id')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="mic_tracker_{date.today()}.csv"'
    writer = csv.writer(response)

    # Header block
    show_info = getattr(request.current_project, 'mic_show_info', None)
    writer.writerow(['Mic Assignment List'])
    writer.writerow(['Show Name:', getattr(show_info, 'show_name', '') or ''])
    writer.writerow(['Venue:',     getattr(show_info, 'venue_name', '') or ''])
    writer.writerow(['Ballroom:',  getattr(show_info, 'ballroom_name', '') or ''])
    writer.writerow(['Duration:',  getattr(show_info, 'duration_display', '') or ''])
    writer.writerow([])

    # Filter to current project only
    days = ShowDay.objects.filter(
        project_id=project_id
    ).order_by('date').prefetch_related(
        'sessions__mic_assignments__presenter_slots__presenter',
    )

    for day in days:
        writer.writerow([f'Day: {day}'])

        for session in day.sessions.order_by('order'):
            writer.writerow([f'Session: {session.name}'])
            writer.writerow([
                'RF#', 'Presenter(s)', 'Type',
                'Placement', 'Sensitivity', 'Output Level', 'Notes'
            ])

            for assignment in session.mic_assignments.order_by('rf_number'):
                # Collect all presenter slots
                slots = list(assignment.presenter_slots.order_by('order'))
                if not slots:
                    writer.writerow([
                        f'{assignment.rf_number:02d}', '', '', '', '', '', ''
                    ])
                    continue

                for i, slot in enumerate(slots):
                    presenter_name = slot.presenter.name if slot.presenter else '— Unassigned —'
                    writer.writerow([
                        f'{assignment.rf_number:02d}' if i == 0 else '',
                        presenter_name,
                        slot.mic_type or '',
                        slot.get_placement_display() if slot.placement else '',
                        slot.sensitivity or '',
                        slot.output_level or '',
                        slot.notes or '',
                    ])

            writer.writerow([])
        writer.writerow([])

    return response


def delete_session(request):
    """AJAX endpoint to delete a mic session"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        session = get_object_or_404(MicSession, id=session_id)
        session.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@staff_member_required
def export_mic_tracker_pdf(request):
    """Export mic tracker A2 cards as PDF — current project, all days/sessions."""

    project_id = request.session.get('current_project_id')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    # ── Styles ────────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    style_title = ParagraphStyle('title',
        fontSize=16, fontName='Helvetica-Bold', spaceAfter=4,
        textColor=colors.HexColor('#1a1a2e'))

    style_day = ParagraphStyle('day',
        fontSize=13, fontName='Helvetica-Bold', spaceAfter=2, spaceBefore=12,
        textColor=colors.HexColor('#0d3b6e'),
        borderPad=4)

    style_session = ParagraphStyle('session',
        fontSize=11, fontName='Helvetica-Bold', spaceAfter=4, spaceBefore=8,
        textColor=colors.HexColor('#1a5276'))

    style_rf = ParagraphStyle('rf',
        fontSize=20, fontName='Helvetica-Bold', alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'))

    style_label = ParagraphStyle('label',
        fontSize=7, fontName='Helvetica', textColor=colors.HexColor('#888888'),
        spaceAfter=1)

    style_value = ParagraphStyle('value',
        fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=2)

    style_presenter = ParagraphStyle('presenter',
        fontSize=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a2e'))

    style_notes = ParagraphStyle('notes',
        fontSize=8, fontName='Helvetica', textColor=colors.HexColor('#444444'),
        spaceAfter=2)

    CARD_BG    = colors.HexColor('#f4f7fb')
    LABEL_BG   = colors.HexColor('#dce6f0')
    BORDER     = colors.HexColor('#b0c4d8')
    DARK       = colors.HexColor('#1a1a2e')

    PHOTO_SIZE = 0.85 * inch
    PAGE_W     = letter[0] - inch  # usable width

    story = []

    # ── Title ────────────────────────────────────────────────────────────────
    show_info = getattr(request.current_project, 'mic_show_info', None)
    show_name = getattr(show_info, 'show_name', '') or str(request.current_project)
    story.append(Paragraph(f'🎤 Mic Tracker — {show_name}', style_title))
    meta = []
    if getattr(show_info, 'venue_name', ''):
        meta.append(f"Venue: {show_info.venue_name}")
    if getattr(show_info, 'duration_display', ''):
        meta.append(f"Dates: {show_info.duration_display}")
    if meta:
        story.append(Paragraph('  |  '.join(meta), styles['Normal']))
    story.append(Spacer(1, 0.15 * inch))

    # ── Data ─────────────────────────────────────────────────────────────────
    days = ShowDay.objects.filter(
        project_id=project_id
    ).order_by('date').prefetch_related(
        'sessions__mic_assignments__presenter_slots__presenter',
    )

    first_day = True
    for day in days:
        if not first_day:
            story.append(PageBreak())
        first_day = False
        story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#0d3b6e')))
        story.append(Paragraph(str(day), style_day))

        for session in day.sessions.order_by('order'):
            story.append(Paragraph(f'Session: {session.name}', style_session))

            for assignment in session.mic_assignments.order_by('rf_number'):
                slots = list(assignment.presenter_slots.order_by('order'))
                if not slots:
                    continue

                # Build one card per slot (each slot = one presenter on this mic)
                for slot in slots:
                    presenter_name = slot.presenter.name if slot.presenter else '— Unassigned —'

                    # ── Photo ────────────────────────────────────────────
                    photo_cell = Spacer(PHOTO_SIZE, PHOTO_SIZE)
                    if slot.photo and slot.photo.name:
                        try:
                            photo_path = slot.photo.path
                            if os.path.exists(photo_path):
                                photo_cell = Image(
                                    photo_path,
                                    width=PHOTO_SIZE,
                                    height=PHOTO_SIZE,
                                )
                                photo_cell.hAlign = 'CENTER'
                        except Exception:
                            pass

                    # ── Detail fields ────────────────────────────────────
                    def field_block(label, value):
                        return [
                            Paragraph(label, style_label),
                            Paragraph(value or '—', style_value),
                        ]

                    details = []
                    details += field_block('PRESENTER', presenter_name)
                    details += field_block('TYPE',      slot.mic_type or assignment.mic_type or '')
                    details += field_block('PLACEMENT', slot.get_placement_display() if slot.placement else '')
                    details += field_block('SENSITIVITY', slot.sensitivity or '')
                    details += field_block('OUTPUT LEVEL', slot.output_level or '')
                    if slot.notes:
                        details.append(Paragraph('NOTES', style_label))
                        details.append(Paragraph(slot.notes, style_notes))

                    # ── Card layout: [RF# | Photo | Details] ─────────────
                    rf_col_w    = 0.55 * inch
                    photo_col_w = PHOTO_SIZE + 0.1 * inch
                    detail_col_w = PAGE_W - rf_col_w - photo_col_w

                    card_data = [[
                        Paragraph(f'{assignment.rf_number:02d}', style_rf),
                        photo_cell,
                        details,
                    ]]

                    card = Table(
                        card_data,
                        colWidths=[rf_col_w, photo_col_w, detail_col_w],
                        rowHeights=[None],
                    )
                    card.setStyle(TableStyle([
                        ('BACKGROUND',  (0, 0), (-1, -1), CARD_BG),
                        ('BACKGROUND',  (0, 0), (0, 0),   LABEL_BG),
                        ('BOX',         (0, 0), (-1, -1), 1, BORDER),
                        ('LINEAFTER',   (0, 0), (0, 0),   1, BORDER),
                        ('LINEAFTER',   (1, 0), (1, 0),   1, BORDER),
                        ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
                        ('ALIGN',       (0, 0), (0, 0),   'CENTER'),
                        ('VALIGN',      (0, 0), (0, 0),   'MIDDLE'),
                        ('TOPPADDING',  (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('LEFTPADDING', (0, 0), (-1, -1), 6),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ]))

                    story.append(KeepTogether([card, Spacer(1, 0.06 * inch)]))

            story.append(Spacer(1, 0.1 * inch))

    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="mic_tracker_{date.today()}.pdf"'
    return response    



@require_POST
@staff_member_required
def toggle_day_collapse(request):
    """Toggle the collapsed state of a day"""
    try:
        day_id = request.POST.get('day_id')
        if not day_id:
            return JsonResponse({'success': False, 'error': 'No day_id provided'})
        
        day = ShowDay.objects.get(id=day_id)
        day.is_collapsed = not day.is_collapsed
        day.save()
        
        return JsonResponse({
            'success': True,
            'is_collapsed': day.is_collapsed
        })
    except ShowDay.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Day not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})      


def _presenter_photo_data_url(presenter):
    """Return a data: URL string for a Presenter's headshot, or '' if none.

    Used to auto-populate PresenterSlot.photo_data (an inline base64 data URL
    that the A2 photo zone renders as <img src=...>) when a presenter is
    assigned to a slot — Issue #10. Any read failure returns '' so the
    assignment itself still succeeds; the photo just won't auto-populate.
    """
    if not presenter or not presenter.photo:
        return ''
    try:
        import base64
        import mimetypes
        with presenter.photo.open('rb') as f:
            content = f.read()
        mime_type = mimetypes.guess_type(presenter.photo.name)[0] or 'image/jpeg'
        b64 = base64.b64encode(content).decode('utf-8')
        return f'data:{mime_type};base64,{b64}'
    except Exception:
        return ''


@csrf_exempt
@require_http_methods(["POST"])
def update_mic_assignment(request):
    """Update a mic assignment field"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        field = data.get('field')
        value = data.get('value')

        assignment = get_object_or_404(MicAssignment, id=assignment_id)
        current_project_id = request.session.get('current_project')
        if not current_project_id and hasattr(request, 'current_project') and request.current_project:
            current_project_id = request.current_project.id

        if field in ('is_micd', 'is_d_mic'):
            setattr(assignment, field, value if isinstance(value, bool) else value == 'true')
            assignment.save()
        elif field in ('presenter', 'presenter_name', 'presenter_id', 'mic_type',
                    'placement', 'sensitivity', 'output_level', 'notes'):
            slot = assignment.presenter_slots.filter(is_active=True).first()
            if not slot:
                slot = assignment.presenter_slots.order_by('order').first()
            if not slot:
                slot = PresenterSlot.objects.create(
                    assignment=assignment, order=0, is_active=True
                )
            presenter_changed = False
            if field in ('presenter', 'presenter_name'):
                if value:
                    presenter, _ = Presenter.objects.get_or_create(
                        name=value.strip(), project_id=current_project_id
                    )
                    slot.presenter = presenter
                else:
                    slot.presenter = None
                presenter_changed = True
            elif field == 'presenter_id':
                if value:
                    try:
                        slot.presenter = Presenter.objects.get(id=int(value))
                    except (ValueError, Presenter.DoesNotExist):
                        # Value is a name string, use get_or_create
                        presenter, _ = Presenter.objects.get_or_create(
                            name=value.strip(),
                            project_id=current_project_id
                        )
                        slot.presenter = presenter
                else:
                    slot.presenter = None
                presenter_changed = True
            else:
                setattr(slot, field, value)

            # Issue #10: when the presenter changes, sync the slot's headshot
            # to the Presenter's photo. Clearing the presenter also clears
            # photo_data so a stale face doesn't hang on after re-assignment.
            if presenter_changed:
                slot.photo_data = _presenter_photo_data_url(slot.presenter)

            slot.save()
        else:
            return JsonResponse({'success': False, 'error': f'Unknown field: {field}'}, status=400)

        session = assignment.session
        session_stats = {
            'micd': session.mic_assignments.filter(is_micd=True).count(),
            'total': session.mic_assignments.count(),
        }
        active_slot = assignment.presenter_slots.filter(is_active=True).first()
        presenter_display = active_slot.presenter.name if active_slot and active_slot.presenter else ''

        slot_count = assignment.presenter_slots.count()
        return JsonResponse({
            'success': True,
            'session_stats': session_stats,
            'presenter_display': presenter_display,
            'presenter_count': slot_count,
            'slot_photo_data': active_slot.photo_data if active_slot else '',
            'active_slot_id': active_slot.id if active_slot else None,
        })
        
    except Exception as e:
        import traceback
        print(f"ERROR in update_mic_assignment: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_POST
def add_shared_presenter(request):
    """Add a new shared presenter to a mic assignment"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        presenter_name = data.get('presenter_name', '').strip()
        
        if not assignment_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing assignment ID'
            })
        
        if not presenter_name:
            return JsonResponse({
                'success': False,
                'error': 'Presenter name cannot be empty'
            })
        
        assignment = MicAssignment.objects.get(id=assignment_id)
        
        # Get or create the presenter WITH PROJECT
        current_project_id = request.session.get('current_project')
        if not current_project_id:
            return JsonResponse({
                'success': False,
                'error': 'No project selected'
            })

        presenter, created = Presenter.objects.get_or_create(
            name=presenter_name,
            project_id=current_project_id
)
        
        # Check if presenter is already the main presenter
        if assignment.presenter and assignment.presenter.id == presenter.id:
            return JsonResponse({
                'success': False,
                'error': 'This is already the main presenter. Use the main presenter field instead.'
            })
        
        # Check if already in shared presenters
        if assignment.shared_presenters.filter(id=presenter.id).exists():
            return JsonResponse({
                'success': False,
                'error': 'This presenter is already in the shared list'
            })
        
        # Add the presenter
        assignment.shared_presenters.add(presenter)
        
        return JsonResponse({
            'success': True,
            'message': f'Added {presenter_name} to shared presenters',
            'shared_count': assignment.shared_presenters.count(),
            'shared_presenters': [p.name for p in assignment.shared_presenters.all()]
        })
        
    except MicAssignment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Assignment not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        })


@require_POST
def remove_shared_presenter(request):
    """Remove a shared presenter from a mic assignment"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        presenter_name = data.get('presenter_name', '').strip()
        
        if not assignment_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing assignment ID'
            })
        
        if not presenter_name:
            return JsonResponse({
                'success': False,
                'error': 'Missing presenter name'
            })
        
        assignment = MicAssignment.objects.get(id=assignment_id)
        
        # Check if there are any shared presenters
        if not assignment.shared_presenters.exists():
            return JsonResponse({
                'success': False,
                'error': 'No shared presenters to remove'
            })
        
        # Find the presenter by name
        try:
            presenter = assignment.shared_presenters.get(name__iexact=presenter_name)
        except Presenter.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Presenter "{presenter_name}" not found in shared list'
            })
        
        # Remove the presenter from the ManyToMany relationship
        assignment.shared_presenters.remove(presenter)
        
        # Adjust active_presenter_index if needed
        remaining_count = assignment.shared_presenters.count()
        if assignment.active_presenter_index > remaining_count:
            assignment.active_presenter_index = 0
            assignment.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Removed {presenter_name} from shared presenters',
            'shared_count': remaining_count,
            'shared_presenters': [p.name for p in assignment.shared_presenters.all()],
            'current_presenter': assignment.current_presenter
        })
        
    except MicAssignment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Assignment not found'
        })
    except Exception as e:
        import traceback
        print(f"ERROR in remove_shared_presenter: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        })


@require_POST
def dmic_and_rotate(request):
    """Handle D-MIC checkbox with automatic presenter rotation"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        
        if not assignment_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing assignment ID'
            })
        
        assignment = MicAssignment.objects.get(id=assignment_id)
        
        # Get current presenter name before any changes
        current_name = assignment.get_current_presenter_name()
        
        # Toggle D-MIC status
        assignment.is_d_mic = not assignment.is_d_mic
        
        # If turning ON D-MIC, turn off MIC'D and rotate to next presenter
        if assignment.is_d_mic:
            assignment.is_micd = False
            # Rotate if there are shared presenters
            if assignment.shared_presenters.exists():
                assignment.rotate_to_next_presenter()
                new_name = assignment.get_current_presenter_name()
                message = f'{current_name} D-MIC → {new_name} is now active'
            else:
                new_name = current_name
                message = f'{current_name} D-MIC'
        else:
            # Turning OFF D-MIC
            new_name = current_name
            message = f'{current_name} MIC'
        
        assignment.save()
        
        return JsonResponse({
            'success': True,
            'is_d_mic': assignment.is_d_mic,
            'is_micd': assignment.is_micd,
            'message': message,
            'current_presenter': new_name,
            'active_presenter_index': assignment.active_presenter_index,
            'previous_presenter': current_name
        })
        
    except MicAssignment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Assignment not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@require_POST
def reset_presenter_rotation(request):
    """Reset the presenter rotation back to the primary presenter"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        
        if not assignment_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing assignment ID'
            })
        
        assignment = MicAssignment.objects.get(id=assignment_id)
        assignment.reset_presenter_rotation()
        
        return JsonResponse({
            'success': True,
            'message': 'Reset to primary presenter',
            'current_presenter': assignment.presenter.name if assignment.presenter else ''
        })
        
    except MicAssignment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Assignment not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })   


@require_http_methods(["GET"])
def get_assignment_details(request, assignment_id):
    """Fetch assignment details including shared presenters"""
    try:
        assignment = get_object_or_404(MicAssignment, id=assignment_id)
        
        # Get shared presenters as a list of names
        shared_presenters = [p.name for p in assignment.shared_presenters.all()]
        
        return JsonResponse({
            'success': True,
            'assignment': {
                'id': assignment.id,
                'rf_number': assignment.rf_number,
                'presenter': assignment.presenter.name if assignment.presenter else '',
                'shared_presenters': shared_presenters,
                'mic_type': assignment.mic_type or '',
                'notes': assignment.notes or ''
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    
 


@require_POST
def dmic_and_rotate(request):
    """Handle D-MIC checkbox with automatic presenter rotation"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        
        if not assignment_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing assignment ID'
            })
        
        assignment = MicAssignment.objects.get(id=assignment_id)
        
        # Store previous presenter for notification
        previous_presenter = assignment.current_presenter
        
        # Toggle D-MIC status
        assignment.is_d_mic = not assignment.is_d_mic

        if assignment.is_d_mic:
            assignment.is_micd = False
        
        # If we're turning OFF d-mic and have shared presenters, rotate
        if not assignment.is_d_mic and assignment.has_shared_presenters:
            next_presenter = assignment.rotate_to_next_presenter()
            message = f'{previous_presenter} D-MIC → {next_presenter} is now active'
        else:
            next_presenter = previous_presenter
            message = f'{previous_presenter} {"D-MIC" if assignment.is_d_mic else "MIC"}'
        
        assignment.save()
        
        return JsonResponse({
            'success': True,
            'is_d_mic': assignment.is_d_mic,
            'is_micd': assignment.is_micd,  # NEW: Include MIC'D status
            'message': message,
            'current_presenter': next_presenter,
            'active_presenter_index': assignment.active_presenter_index,
            'previous_presenter': previous_presenter
        })
        
    except MicAssignment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Assignment not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    

@require_POST
def update_slot_field(request):
    try:
        data = json.loads(request.body)
        slot = get_object_or_404(PresenterSlot, id=data['slot_id'])
        field = data['field']
        value = data['value']
        if field in ('notes', 'mic_type', 'placement', 'sensitivity', 'output_level'):
            setattr(slot, field, value)
            slot.save()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Invalid field'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
def assign_slot_group(request):
    try:
        data = json.loads(request.body)
        slot = get_object_or_404(PresenterSlot, id=data['slot_id'])
        group_id = data.get('group_id')
        slot.group = MicGroup.objects.get(id=group_id) if group_id else None
        slot.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    

@require_POST
def assign_slot_a2_group(request):
    try:
        data = json.loads(request.body)
        slot = get_object_or_404(PresenterSlot, id=data['slot_id'])
        group_id = data.get('group_id')
        slot.a2_group = MicGroup.objects.get(id=group_id) if group_id else None
        slot.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
def toggle_slot_micd(request):
    try:
        data = json.loads(request.body)
        slot_id = data.get('slot_id')
        new_state = data.get('is_micd', False)
        slot = get_object_or_404(PresenterSlot, id=slot_id)
        # Turn off all sibling slots on this assignment
        PresenterSlot.objects.filter(assignment=slot.assignment).update(is_micd=False)
        if new_state:
            slot.is_micd = True
            slot.save()
        return JsonResponse({
            'success': True,
            'assignment_id': slot.assignment.id,
            'active_slot_id': slot_id if new_state else None,
            'is_micd': new_state
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})    



    #---Dropdown for presenters---
@staff_member_required
def get_presenters_list(request):
    q = request.GET.get('q', '')
    project = getattr(request, 'current_project', None)
    presenters = Presenter.objects.filter(name__icontains=q)
    if project:
        presenters = presenters.filter(project=project)
    presenters = presenters.order_by('name').values('id', 'name')
    return JsonResponse({'presenters': list(presenters)})

@staff_member_required
def create_presenter(request):
    if request.method != 'POST':
        return JsonResponse({'success': False})
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False})
    project = getattr(request, 'current_project', None)
    presenter, created = Presenter.objects.get_or_create(name=name, project=project)
    return JsonResponse({'success': True, 'presenter_id': presenter.id})





@staff_member_required
def upload_presenter_photo(request):
    if request.method == 'POST':
        presenter_id = request.POST.get('presenter_id')
        photo = request.FILES.get('photo')
        if not presenter_id or not photo:
            return JsonResponse({'success': False, 'error': 'Missing data'})
        try:
            presenter = Presenter.objects.get(id=presenter_id)
            presenter.photo.save(photo.name, photo, save=True)
            return JsonResponse({'success': True, 'photo_url': presenter.photo.url})
        except Presenter.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Presenter not found'})
    return JsonResponse({'success': False})

@staff_member_required
def upload_photo_by_assignment(request):
    if request.method == 'POST':
        assignment_id = request.POST.get('assignment_id')
        photo = request.FILES.get('photo')
        try:
            assignment = MicAssignment.objects.get(id=assignment_id)
            slot = assignment.presenter_slots.filter(is_active=True).first()
            if not slot:
                return JsonResponse({'success': False, 'error': 'No active slot'})
            import os
            filename = os.path.basename(photo.name)
            slot.photo.save(f'slot_photos/{filename}', photo, save=True)
            return JsonResponse({'success': True, 'photo_url': slot.photo.url})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
def upload_slot_photo(request):
    if request.method == 'POST':
        slot_id = request.POST.get('slot_id')
        photo = request.FILES.get('photo')
        if not slot_id or not photo:
            return JsonResponse({'success': False, 'error': 'Missing slot_id or photo'})
        try:
            import base64
            slot = PresenterSlot.objects.get(id=slot_id)
            photo_bytes = photo.read()
            mime_type = photo.content_type or 'image/jpeg'
            b64 = base64.b64encode(photo_bytes).decode('utf-8')
            slot.photo_data = f'data:{mime_type};base64,{b64}'
            slot.save()
            return JsonResponse({'success': True, 'photo_url': slot.photo_data})
        except PresenterSlot.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Slot not found'})
    return JsonResponse({'success': False})


@require_POST
@login_required
def upload_slot_photo_from_url(request):
    """Issue #39: fetch an image URL server-side and store it on the
    presenter slot, used when a user drags an HTML <img> from another
    site into the photo zone (where client-side fetch is blocked by CORS).

    Body (JSON): {slot_id, url}

    Hardening:
    - Auth + project allowlist matching mic_assignment_reorder.
    - URL must be http/https with a public-routable host (rejects
      private, loopback, link-local, reserved, multicast).
    - 10s connect/read timeout, 5 MB max response, image/* content-type.
    """
    import base64
    import ipaddress
    import socket
    import urllib.parse

    import requests

    MAX_BYTES = 5 * 1024 * 1024

    try:
        data = json.loads(request.body)
        slot_id = int(data['slot_id'])
        url = (data['url'] or '').strip()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Bad request'}, status=400)

    try:
        slot = PresenterSlot.objects.select_related(
            'assignment__session__day__project'
        ).get(id=slot_id)
    except PresenterSlot.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Slot not found'}, status=404)

    project = slot.assignment.session.day.project
    allowed = (
        request.user.is_superuser
        or project.owner_id == request.user.id
        or ProjectMember.objects.filter(
            user=request.user, project=project, role='editor'
        ).exists()
    )
    if not allowed:
        return JsonResponse({'success': False, 'error': 'Not allowed'}, status=403)

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return JsonResponse({'success': False, 'error': 'Only http(s) URLs accepted'}, status=400)

    # SSRF guard: every resolved address must be public.
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return JsonResponse({'success': False, 'error': 'Cannot resolve host'}, status=400)
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return JsonResponse({'success': False, 'error': 'Refused: internal host'}, status=400)

    try:
        resp = requests.get(url, timeout=10, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        return JsonResponse({'success': False, 'error': f'Fetch failed: {e}'}, status=400)

    content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    if not content_type.startswith('image/'):
        return JsonResponse({'success': False, 'error': 'URL did not return an image'}, status=400)

    buf = bytearray()
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            resp.close()
            return JsonResponse({'success': False, 'error': 'Image exceeds 5 MB limit'}, status=400)

    b64 = base64.b64encode(bytes(buf)).decode('utf-8')
    slot.photo_data = f'data:{content_type};base64,{b64}'
    slot.save(update_fields=['photo_data'])
    return JsonResponse({'success': True, 'photo_url': slot.photo_data})


@require_POST
def advance_presenter_slot(request):
    """Move to next presenter slot"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        assignment = get_object_or_404(MicAssignment, id=assignment_id)
        slots = list(assignment.presenter_slots.order_by('order'))
        if not slots:
            return JsonResponse({'success': False, 'error': 'No slots'})
        current = next((i for i, s in enumerate(slots) if s.is_active), 0)
        next_index = (current + 1) % len(slots)
        for i, slot in enumerate(slots):
            slot.is_active = (i == next_index)
            slot.save()
        active = slots[next_index]
        return JsonResponse({
            'success': True,
            'slot_id': active.id,
            'presenter_name': active.presenter.name if active.presenter else '',
            'presenter_id': active.presenter.id if active.presenter else None,
            'mic_type': active.mic_type,
            'placement': active.placement,
            'sensitivity': active.sensitivity,
            'output_level': active.output_level,
            'notes': active.notes,
            'slot_index': next_index,
            'slot_count': len(slots),
            'photo_url': active.photo_data or None,
            'a2_group_color': active.a2_group.color if active.a2_group else None,
            'a2_group_name': active.a2_group.name if active.a2_group else None,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
def previous_presenter_slot(request):
    """Move to previous presenter slot"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        assignment = get_object_or_404(MicAssignment, id=assignment_id)
        slots = list(assignment.presenter_slots.order_by('order'))
        if not slots:
            return JsonResponse({'success': False, 'error': 'No slots'})
        current = next((i for i, s in enumerate(slots) if s.is_active), 0)
        prev_index = (current - 1) % len(slots)
        for i, slot in enumerate(slots):
            slot.is_active = (i == prev_index)
            slot.save()
        active = slots[prev_index]
        return JsonResponse({
            'success': True,
            'slot_id': active.id,
            'presenter_name': active.presenter.name if active.presenter else '',
            'presenter_id': active.presenter.id if active.presenter else None,
            'mic_type': active.mic_type,
            'placement': active.placement,
            'sensitivity': active.sensitivity,
            'output_level': active.output_level,
            'notes': active.notes,
            'slot_index': prev_index,
            'slot_count': len(slots),
            'photo_url': active.photo_data or None,
            'a2_group_color': active.a2_group.color if active.a2_group else None,
            'a2_group_name': active.a2_group.name if active.a2_group else None,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@require_POST
def add_presenter_slot(request):
    """Add a new presenter slot to an assignment"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        assignment = get_object_or_404(MicAssignment, id=assignment_id)
        
        # Get next order number
        last_slot = assignment.presenter_slots.order_by('-order').first()
        next_order = (last_slot.order + 1) if last_slot else 0
        
        # Create new slot but keep current active slot unchanged
        slot = PresenterSlot.objects.create(
            assignment=assignment,
            order=next_order,
            is_active=False
        )
        
        slots = assignment.presenter_slots.order_by('order')
        return JsonResponse({
            'success': True,
            'slot_id': slot.id,
            'slot_index': next_order,
            'slot_count': slots.count(),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@require_POST
def remove_presenter_slot(request):
    """Remove a presenter slot from an assignment"""
    try:
        data = json.loads(request.body)
        assignment_id = data.get('assignment_id')
        slot_id = data.get('slot_id')
        
        assignment = get_object_or_404(MicAssignment, id=assignment_id)
        slots = list(assignment.presenter_slots.order_by('order'))
        
        if len(slots) <= 1:
            return JsonResponse({'success': False, 'error': 'Cannot remove the only slot'})
        
        slot = get_object_or_404(PresenterSlot, id=slot_id, assignment=assignment)
        was_active = slot.is_active
        slot.delete()
        
        # Re-order remaining slots
        remaining = list(assignment.presenter_slots.order_by('order'))
        for i, s in enumerate(remaining):
            s.order = i
            s.save()
        
        # If deleted slot was active, activate first slot
        if was_active and remaining:
            remaining[0].is_active = True
            remaining[0].save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})    




@staff_member_required
def manage_mic_groups(request, session_id):
    session = get_object_or_404(MicSession, id=session_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        action = data.get('action')
        if action == 'create':
            group = MicGroup.objects.create(
                session=session,
                name=data['name'],
                color=data['color']
            )
            return JsonResponse({'success': True, 'group_id': group.id, 'name': group.name, 'color': group.color})
        elif action == 'delete':
            MicGroup.objects.filter(id=data['group_id'], session=session).delete()
            return JsonResponse({'success': True})
    groups = list(session.mic_groups.values('id', 'name', 'color'))
    return JsonResponse({'success': True, 'groups': groups})

@staff_member_required  
def assign_mic_group(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        assignment = get_object_or_404(MicAssignment, id=data['assignment_id'])
        group_id = data.get('group_id')
        assignment.group = MicGroup.objects.get(id=group_id) if group_id else None
        assignment.save()
        return JsonResponse({'success': True})

@require_http_methods(["GET"])
def get_assignment_details(request, assignment_id):
    """Fetch assignment details including shared presenters"""
    try:
        assignment = get_object_or_404(MicAssignment, id=assignment_id)
        
        shared_presenters = assignment.shared_presenters
        if shared_presenters is None:
            shared_presenters = []
        elif isinstance(shared_presenters, str):
            try:
                shared_presenters = json.loads(shared_presenters)
            except:
                shared_presenters = []
        
        return JsonResponse({
            'success': True,
            'assignment': {
                'id': assignment.id,
                'rf_number': assignment.rf_number,
                'presenter': assignment.presenter_name or '',  # Changed from assignment.presenter
                'shared_presenters': shared_presenters,
                'mic_type': assignment.mic_type or '',
                'notes': assignment.notes or ''
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    



@staff_member_required
def comm_config_view(request, config_id=None):
            """
            COMM Config module — list view and editor view.
            Mirrors the mic_tracker_view pattern.
            """
            current_project = getattr(request, 'current_project', None)

            # List of configs for this project
            configs = CommConfig.objects.filter(
                project=current_project
            ).order_by('created_at') if current_project else CommConfig.objects.none()

            config = None
            partylines = []
            roles = []
            ports = []
            dante_channels = []
            helixnet_partylines = []
            sessions = []
            rolesets = []
            all_roles = []

            if config_id:
                config = CommConfig.objects.filter(id=config_id, project=current_project).first()
                if not config:
                    from django.shortcuts import redirect
                    return redirect("planner:comm_config")
                partylines = config.partylines.all().order_by('channel_number')
                helixnet_partylines = config.partylines.filter(helixnet_enabled=True).order_by('channel_number')
                roles = config.roles.all().order_by('device_type', 'label')
                ports = config.port_assignments.all().order_by('port_type', 'port_label')
                # Auto-create LAN rows if missing
                existing_ports = set(config.network_ports.values_list('port_number', flat=True))
                for port_num, traffic in [(1, 'admin'), (2, 'aes67'), (3, 'disabled'), (4, 'disabled')]:
                    if port_num not in existing_ports:
                        CommConfigNetworkPort.objects.create(config=config, port_number=port_num, traffic_type=traffic)
                # Auto-seed FreeSpeak ports if missing
                if config.device_type == 'freespeak' and not config.port_assignments.exists():
                    fsii_port_defaults = [
                        ('2W', '2W Port A', '2w_1'),
                        ('2W', '2W Port B', '2w_2'),
                        ('2W', '2W Port C', '2w_3'),
                        ('2W', '2W Port D', '2w_4'),
                        ('4W', '4W Port 1', '4w_1'),
                        ('4W', '4W Port 2', '4w_2'),
                        ('4W', '4W Port 3', '4w_3'),
                        ('4W', '4W Port 4', '4w_4'),
                        ('SA', 'SA', 'sa'),
                        ('PGM', 'PGM', 'pgm'),
                    ]
                    for port_type, label, gid in fsii_port_defaults:
                        CommConfigPortAssignment.objects.create(
                            config=config, port_type=port_type,
                            port_label=label, port_gid=gid,
                        )
                dante_channels = config.dante_channels.all().order_by('direction', 'channel_number')
                sessions = config.sessions.all().order_by('session_type')
                rolesets = config.rolesets.all().order_by('roleset_number')
                all_roles = config.roles.all().order_by('role_number')

            # Group roles by device_type for display
            from itertools import groupby
            roles_by_type = {}
            for role in roles:
                dt = role.get_device_type_display() if hasattr(role, 'get_device_type_display') else role.device_type
                if dt not in roles_by_type:
                    roles_by_type[dt] = []
                roles_by_type[dt].append(role)

            # Group ports by port_type
            ports_by_type = {}
            for port in ports:
                pt = port.get_port_type_display() if hasattr(port, 'get_port_type_display') else port.port_type
                if pt not in ports_by_type:
                    ports_by_type[pt] = []
                ports_by_type[pt].append(port)

            context = {
                
                'title': 'COMM Config',
                'has_permission': True,
                'configs': configs,
                'config': config,
                'config_id': config_id,
                'partylines': partylines,
                'helixnet_partylines': helixnet_partylines if config_id else [],
                'roles_by_type': roles_by_type,
                'ports': ports,
                'ports_by_type': ports_by_type,
                'network_ports': list(config.network_ports.order_by('port_number')) if config else [],

                'dante_channels': dante_channels if config_id else [],
                'sessions': sessions,
                'rolesets': rolesets if config_id else [],
                'all_roles': all_roles if config_id else [],
                'current_project': current_project,
                'crew_names': CommCrewName.objects.filter(project=current_project).order_by('name') if current_project else [],
                'opts': CommConfig._meta,  # needed for admin breadcrumbs
            }

            return render(request, 'planner/comm_config.html', context)                                     


@login_required
def power_distribution_calculator(request, plan_id=None):
    """Main power distribution calculator view"""
    
    if plan_id:
        plan = get_object_or_404(PowerDistributionPlan, id=plan_id)
    else:
        # Create new plan or get most recent
        show_day_id = request.GET.get('show_day')
        if show_day_id:
            show_day = get_object_or_404(ShowDay, id=show_day_id)
            plan, created = PowerDistributionPlan.objects.get_or_create(
                show_day=show_day,
                defaults={
                    'venue_name': show_day.name,
                    'created_by': request.user
                }
            )
        else:
            plan = PowerDistributionPlan.objects.first()
            if not plan:
                # Create a default plan
                show_day = ShowDay.objects.first()
                if show_day:
                    plan = PowerDistributionPlan.objects.create(
                        show_day=show_day,
                        venue_name=show_day.name,
                        created_by=request.user
                    )
                else:
                    messages.warning(request, "Please create a ShowDay first")
                    return redirect('admin:planner_showday_add')
    
    # Get all amplifier profiles
    amplifier_profiles = AmplifierProfile.objects.all()
    
    # Get assignments for this plan
    assignments = AmplifierAssignment.objects.filter(
        distribution_plan=plan
    ).select_related('amplifier').order_by('zone', 'position')
    
    # Calculate phase distribution
    phase_loads = calculate_phase_distribution(plan)
    
    # Calculate totals server-side to avoid template JS errors
    total_amps_count = sum(a.quantity for a in assignments)
    total_peak_power = 0
    for a in assignments:
        try:
            total_peak_power += a.get_power_details()['total']['peak_watts']
        except Exception:
            pass

    context = {
        'plan': plan,
        'amplifier_profiles': amplifier_profiles,
        'assignments': assignments,
        'phase_loads': phase_loads,
        'duty_cycles': AmplifierAssignment.DUTY_CYCLES,
        'service_types': PowerDistributionPlan.SERVICE_TYPES,
        'total_amps_count': total_amps_count,
        'total_peak_power_kw': round(total_peak_power / 1000, 1),
    }
    
    return render(request, 'planner/power_distribution_calculator.html', context)


def calculate_phase_distribution(plan):
    """Calculate the current distribution across phases"""
    assignments = plan.amplifier_assignments.all()
    
    # Initialize phase tracking
    phases = {
        'L1': {'assignments': [], 'total_current': 0},
        'L2': {'assignments': [], 'total_current': 0},
        'L3': {'assignments': [], 'total_current': 0},
    }
    
    # Auto-balance assignments marked as AUTO
    auto_assignments = []
    
    for assignment in assignments:
        if assignment.phase_assignment == 'AUTO':
            auto_assignments.append(assignment)
        elif assignment.phase_assignment in phases:
            phases[assignment.phase_assignment]['assignments'].append(assignment)
            phases[assignment.phase_assignment]['total_current'] += float(
                assignment.calculated_total_current or 0
            )
    
   
    # Balance auto assignments - distribute amps evenly across phases (round-robin per line)
    for assignment in auto_assignments:
        current_per_unit = float(assignment.calculated_current_per_unit or 0)
        quantity = assignment.quantity or 1
        
        # Track how many amps go to each phase for this assignment
        assignment._phase_distribution = {'L1': 0, 'L2': 0, 'L3': 0}
        
        # Simple round-robin distribution for THIS line only
        phase_order = ['L1', 'L2', 'L3']
        for i in range(quantity):
            phase = phase_order[i % 3]  # Round-robin: 0->L1, 1->L2, 2->L3, 3->L1, etc.
            phases[phase]['total_current'] += current_per_unit
            assignment._phase_distribution[phase] += 1
        
        # Set display phase to show distribution (e.g., "L1:2, L2:2, L3:2")
        dist_parts = [f"{p}:{c}" for p, c in assignment._phase_distribution.items() if c > 0]
        assignment._display_phase = ", ".join(dist_parts) if len(dist_parts) > 1 else dist_parts[0].split(':')[0]
        
        # Add to L1's assignments list for display
        phases['L1']['assignments'].append(assignment)

    # Calculate summary statistics
    total_current = sum(p['total_current'] for p in phases.values())
    max_current = max(p['total_current'] for p in phases.values())
    min_current = min(p['total_current'] for p in phases.values())
       
    # Calculate imbalance
    if max_current > 0:
        imbalance = ((max_current - min_current) / max_current) * 100
    else:
        imbalance = 0
    
    # Calculate usage percentages
    usable_amperage = plan.get_usable_amperage()
    
    for phase_name, phase_data in phases.items():
        phase_data['percentage'] = (
            (phase_data['total_current'] / usable_amperage * 100) 
            if usable_amperage > 0 else 0
        )
        phase_data['current_rounded'] = round(phase_data['total_current'], 1)
    
    return {
        'phases': phases,
        'imbalance': round(imbalance, 1),
        'total_current': round(total_current, 1),
        'usable_amperage': usable_amperage,
        'available_amperage': plan.available_amperage_per_leg,
    }


@login_required
@require_http_methods(["POST"])
def update_plan_settings(request, plan_id):
    """AJAX endpoint to update plan settings"""
    plan = get_object_or_404(PowerDistributionPlan, id=plan_id)
    
    try:
        data = json.loads(request.body)
        
        # Update plan fields
        if 'service_type' in data:
            plan.service_type = data['service_type']
        if 'available_amperage_per_leg' in data:
            plan.available_amperage_per_leg = int(data['available_amperage_per_leg'])
        if 'transient_headroom' in data:
            plan.transient_headroom = Decimal(str(data['transient_headroom']))
        if 'safety_margin' in data:
            plan.safety_margin = Decimal(str(data['safety_margin']))
        if 'venue_name' in data:
            plan.venue_name = data['venue_name']
        
        plan.save()
        
        # Recalculate all assignments with new settings
        for assignment in plan.amplifier_assignments.all():
            assignment.save()  # This triggers recalculation in the model's save method
        
        # Get updated phase distribution. The full phase_loads dict carries
        # AmplifierAssignment model instances inside phases[L].assignments,
        # which the default Django JSON encoder cannot serialize. Strip to
        # scalar fields the JS optimistic update actually reads — the page
        # reload that follows the AJAX call rehydrates the rest from the
        # server-rendered template (#9 fix).
        phase_loads = calculate_phase_distribution(plan)
        slim_phase_loads = {
            'phases': {
                name: {
                    'total_current': pdata.get('total_current', 0),
                    'current_rounded': pdata.get('current_rounded', 0),
                    'percentage': pdata.get('percentage', 0),
                }
                for name, pdata in phase_loads['phases'].items()
            },
            'imbalance': phase_loads.get('imbalance', 0),
            'total_current': phase_loads.get('total_current', 0),
            'usable_amperage': phase_loads.get('usable_amperage', 0),
            'available_amperage': phase_loads.get('available_amperage', 0),
        }

        return JsonResponse({
            'success': True,
            'phase_loads': slim_phase_loads,
            'usable_amperage': plan.get_usable_amperage()
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def add_amplifier_assignment(request, plan_id):
    """AJAX endpoint to add amplifier assignment"""
    plan = get_object_or_404(PowerDistributionPlan, id=plan_id)
    
    try:
        data = json.loads(request.body)
        
        amplifier = get_object_or_404(AmplifierProfile, id=data['amplifier_id'])
        
        assignment = AmplifierAssignment.objects.create(
            distribution_plan=plan,
            amplifier=amplifier,
            quantity=int(data.get('quantity', 1)),
            zone=data.get('zone', 'FOH'),
            position=data.get('position', ''),
            duty_cycle=data.get('duty_cycle', 'heavy_music'),
            phase_assignment='AUTO'  # Let it auto-balance
        )
        
        # Get updated phase distribution
        phase_loads = calculate_phase_distribution(plan)
        
        # Get power details for the new assignment
        power_details = assignment.get_power_details()
        
        # Convert everything to JSON-serializable types
        return JsonResponse({
            'success': True,
            'assignment': {
                'id': assignment.id,
                'amplifier': str(assignment.amplifier),
                'quantity': assignment.quantity,
                'zone': assignment.zone,
                'position': assignment.position,
                'duty_cycle': assignment.get_duty_cycle_display(),
                'phase': assignment.phase_assignment,
                'current_per_unit': float(assignment.calculated_current_per_unit),
                'total_current': float(assignment.calculated_total_current),
                'power_details': {
                    'continuous_watts': float(power_details.get('continuous_watts', 0)),
                    'peak_watts': float(power_details.get('peak_watts', 0)),
                    'current_amps': float(power_details.get('current_amps', 0)),
                } if power_details else {}
            },
            'phase_loads': {
                'L1': float(phase_loads.get('L1', 0)),
                'L2': float(phase_loads.get('L2', 0)),
                'L3': float(phase_loads.get('L3', 0)),
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_amplifier_assignment(request, assignment_id):
    """AJAX endpoint to update amplifier assignment"""
    assignment = get_object_or_404(AmplifierAssignment, id=assignment_id)
    
    try:
        data = json.loads(request.body)
        
        # Update assignment fields
        if 'quantity' in data:
            assignment.quantity = int(data['quantity'])
        if 'zone' in data:
            assignment.zone = data['zone']
        if 'position' in data:
            assignment.position = data['position']
        if 'duty_cycle' in data:
            assignment.duty_cycle = data['duty_cycle']
        if 'phase_assignment' in data:
            assignment.phase_assignment = data['phase_assignment']
        
        assignment.save()
        
        # Get updated phase distribution
        phase_loads = calculate_phase_distribution(assignment.distribution_plan)
        
        return JsonResponse({
            'success': True,
            'current_per_unit': float(assignment.calculated_current_per_unit),
            'total_current': float(assignment.calculated_total_current),
            'phase_loads': phase_loads
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_amplifier_assignment(request, assignment_id):
    """AJAX endpoint to delete amplifier assignment"""
    assignment = get_object_or_404(AmplifierAssignment, id=assignment_id)
    plan = assignment.distribution_plan
    
    try:
        assignment.delete()
        
        # Get updated phase distribution
        phase_loads = calculate_phase_distribution(plan)
        
        return JsonResponse({
            'success': True,
            'phase_loads': phase_loads
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    





@login_required
@require_http_methods(["GET"])
def get_amplifier_assignment(request, assignment_id):
    """Get details of a specific amplifier assignment for editing"""
    try:
        assignment = get_object_or_404(AmplifierAssignment, id=assignment_id)
        
        return JsonResponse({
            'success': True,
            'assignment': {
                'id': assignment.id,
                'amplifier': str(assignment.amplifier),
                'quantity': assignment.quantity,
                'zone': assignment.zone,
                'position': assignment.position,
                'duty_cycle': assignment.duty_cycle,
                'phase_assignment': assignment.phase_assignment,
                'current_per_unit': float(assignment.calculated_current_per_unit),
                'total_current': float(assignment.calculated_total_current),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_amplifier_assignment(request, assignment_id):
    """Update an existing amplifier assignment"""
    try:
        assignment = get_object_or_404(AmplifierAssignment, id=assignment_id)
        data = json.loads(request.body)
        
        # Update the fields
        assignment.quantity = int(data.get('quantity', assignment.quantity))
        assignment.zone = data.get('zone', assignment.zone)
        assignment.position = data.get('position', assignment.position)
        assignment.duty_cycle = data.get('duty_cycle', assignment.duty_cycle)
        assignment.phase_assignment = data.get('phase_assignment', assignment.phase_assignment)
        
        assignment.save()
        
        # Get updated phase distribution
        plan = assignment.distribution_plan
        phase_loads = calculate_phase_distribution(plan)
        
        return JsonResponse({
            'success': True,
            'assignment': {
                'id': assignment.id,
                'quantity': assignment.quantity,
                'zone': assignment.zone,
                'position': assignment.position,
                'duty_cycle': assignment.get_duty_cycle_display(),
                'phase_assignment': assignment.phase_assignment,
                'current_per_unit': float(assignment.calculated_current_per_unit),
                'total_current': float(assignment.calculated_total_current),
            },
            'phase_loads': {
                'L1': float(phase_loads.get('L1', 0)),
                'L2': float(phase_loads.get('L2', 0)),
                'L3': float(phase_loads.get('L3', 0)),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)    
    

# Add these two view functions to planner/views.py





@login_required
@require_http_methods(["GET"])
def get_amplifier_assignment(request, assignment_id):
    """Get details of a specific amplifier assignment for editing"""
    try:
        assignment = get_object_or_404(AmplifierAssignment, id=assignment_id)
        
        return JsonResponse({
            'success': True,
            'assignment': {
                'id': assignment.id,
                'amplifier': str(assignment.amplifier),
                'quantity': assignment.quantity,
                'zone': assignment.zone,
                'position': assignment.position,
                'duty_cycle': assignment.duty_cycle,
                'phase_assignment': assignment.phase_assignment,
                'current_per_unit': float(assignment.calculated_current_per_unit),
                'total_current': float(assignment.calculated_total_current),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_amplifier_assignment(request, assignment_id):
    """Update an existing amplifier assignment"""
    try:
        assignment = get_object_or_404(AmplifierAssignment, id=assignment_id)
        data = json.loads(request.body)
        
        # Update the fields
        assignment.quantity = int(data.get('quantity', assignment.quantity))
        assignment.zone = data.get('zone', assignment.zone)
        assignment.position = data.get('position', assignment.position)
        assignment.duty_cycle = data.get('duty_cycle', assignment.duty_cycle)
        assignment.phase_assignment = data.get('phase_assignment', assignment.phase_assignment)
        
        assignment.save()
        
        # Get updated phase distribution
        plan = assignment.distribution_plan
        phase_loads = calculate_phase_distribution(plan)
        
        return JsonResponse({
            'success': True,
            'assignment': {
                'id': assignment.id,
                'quantity': assignment.quantity,
                'zone': assignment.zone,
                'position': assignment.position,
                'duty_cycle': assignment.get_duty_cycle_display(),
                'phase_assignment': assignment.phase_assignment,
                'current_per_unit': float(assignment.calculated_current_per_unit),
                'total_current': float(assignment.calculated_total_current),
            },
            'phase_loads': {
                'L1': float(phase_loads.get('L1', 0)),
                'L2': float(phase_loads.get('L2', 0)),
                'L3': float(phase_loads.get('L3', 0)),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)    
    


    #-----Audio Checklist-----

@login_required
def audio_checklist(request):
    """
    Simple checklist view - no database required
    All data is stored in browser localStorage
    """
    return render(request, 'planner/audio_checklist.html', {
        'title': 'Audio Production Checklist',
    })


#-------Prediction Module---

# Add to planner/views.py



def predictions_list(request):
    """List all predictions with filtering"""
    show_day_filter = request.GET.get('show_day')
    
    predictions = SoundvisionPrediction.objects.all()
    
    if show_day_filter:
        predictions = predictions.filter(show_day_id=show_day_filter)
    
    show_days = ShowDay.objects.all().order_by('name')
    
    context = {
        'predictions': predictions,
        'show_days': show_days,
        'current_show_day': show_day_filter
    }
    
    return render(request, 'planner/predictions_list.html', context)

# Updated prediction_detail view for planner/views.py
# Replace lines ~1790-1817 with this code

def prediction_detail(request, pk):
    """Display detailed prediction with collapsible arrays grouped by Soundvision group and base name"""
    prediction = get_object_or_404(SoundvisionPrediction, pk=pk)
    
    # Group arrays by their Soundvision group context FIRST, then by base name
    # This keeps "KARA II 1" in "KARA Mains" separate from "KARA II 1" in "Delay"
    grouped_arrays = defaultdict(lambda: defaultdict(list))
    total_weight = Decimal('0')
    total_arrays = 0
    
    for array in prediction.speaker_arrays.all().order_by('group_context', 'array_base_name', 'position_x'):
        group_context = array.group_context or 'Ungrouped'
        grouped_arrays[group_context][array.array_base_name].append(array)
        if array.total_weight_lb:
            total_weight += array.total_weight_lb
        total_arrays += 1
    
    # Convert nested defaultdict to regular dict for template
    # Structure: { 'KARA Mains': {'KARA II 1': [array1, array2], 'KARA II 2': [...]}, 'Delay': {...} }
    grouped_arrays = {
        group: dict(sorted(arrays.items()))
        for group, arrays in sorted(grouped_arrays.items())
    }
    
    context = {
        'prediction': prediction,
        'grouped_arrays': grouped_arrays,
        'total_weight': total_weight,
        'total_arrays': total_arrays,
        'group_count': len(grouped_arrays),
        'slugify': slugify  # Pass slugify to template
    }
    
    return render(request, 'planner/prediction_detail.html', context)

@require_POST
def upload_prediction(request):
    """Handle PDF upload and parsing"""
    if 'pdf_file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    
    pdf_file = request.FILES['pdf_file']
    show_day_id = request.POST.get('show_day')
    
    if not show_day_id:
        return JsonResponse({'error': 'Show day is required'}, status=400)
    
    try:
        show_day = ShowDay.objects.get(pk=show_day_id)
        
        # Create prediction object
        prediction = SoundvisionPrediction.objects.create(
            show_day=show_day,
            file_name=pdf_file.name,
            pdf_file=pdf_file
        )
        
        # Parse the PDF
        import_soundvision_prediction(prediction, pdf_file)
        
        messages.success(request, f'Successfully imported {pdf_file.name}')
        
        return JsonResponse({
            'success': True,
            'prediction_id': prediction.id,
            'redirect': f'/planner/predictions/{prediction.id}/'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def export_prediction_summary(request, pk):
    """Export prediction summary as CSV"""
    
    prediction = get_object_or_404(SoundvisionPrediction, pk=pk)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="prediction_{prediction.show_day}_{prediction.id}.csv"'
    
    writer = csv.writer(response)
    
    # Headers
    writer.writerow(['Array Name', 'Position', 'Weight (lb)', 'Trim Height', 'Rigging', 
                    'Azimuth', 'Motors', 'Front Load (lb)', 'Rear Load (lb)', 
                    'Cabinet Count', 'MBar', 'Configuration'])
    
    # Data grouped by array name
    grouped = defaultdict(list)
    for array in prediction.speaker_arrays.all().order_by('array_base_name', 'position_x'):
        grouped[array.array_base_name].append(array)
    
    for base_name, arrays in sorted(grouped.items()):
        for array in arrays:
            # Position string
            position = f"({array.position_x}, {array.position_y}, {array.position_z})"
            
            # Cabinet configuration summary
            cabinet_angles = []
            for cab in array.cabinets.all():
                if cab.angle_to_next is not None:
                    cabinet_angles.append(f"{cab.angle_to_next}°")
            config = " ".join(cabinet_angles) if cabinet_angles else "No angles"
            
            writer.writerow([
                array.display_name,
                position,
                array.total_weight_lb or 0,
                array.trim_height_display,
                array.rigging_display,
                array.azimuth or 0,
                array.num_motors,
                array.front_motor_load_lb or '',
                array.rear_motor_load_lb or '',
                array.cabinets.count(),
                array.mbar_hole or '',
                config
            ])
    
    return response


#-----------Dashboard Button-------

# Dashboard View



@staff_member_required
def dashboard(request):
    """System Dashboard - Overview of all modules"""
    
    # Console Stats
    
  # Console Stats
    console_stats = {
        'total': Console.objects.count(),
        'with_inputs': Console.objects.filter(consoleinput__isnull=False).distinct().count(),
        'with_outputs': Console.objects.filter(
            Q(consoleauxoutput__isnull=False) | Q(consolematrixoutput__isnull=False)
        ).distinct().count(),
}

# Device Stats
    device_stats = {
        'total': Device.objects.count(),
        'with_inputs': Device.objects.filter(inputs__isnull=False).distinct().count(),
        'with_outputs': Device.objects.filter(outputs__isnull=False).distinct().count(),
}
    
    # Processor Stats
    processor_stats = {
        'total': SystemProcessor.objects.count(),
        'p1': SystemProcessor.objects.filter(device_type='P1').count(),
        'galaxy': SystemProcessor.objects.filter(device_type='GALAXY').count(),
    }

    # Amp Stats
    amp_stats = {
        'total': Amp.objects.count(),
        'locations': AmpLocation.objects.count(),
        'channels': 0,
    }
  
    # Power Distribution Stats
    power_stats = {
        'plans': PowerDistributionPlan.objects.count(),
        'amps_in_plans': PowerDistributionPlan.objects.aggregate(
            total=Count('amplifier_assignments')  # ← Must be 'amplifier_assignments' NOT 'amplifierinpowerplan'
        )['total'] or 0,
}

    
    # PA Cable Stats
    pa_cable_stats = {
        'cable_runs': PACableSchedule.objects.count(),
        'zones': PAZone.objects.count(),
        'total_cables': sum([
            run.count for run in PACableSchedule.objects.all()
        ]) if PACableSchedule.objects.exists() else 0,
    }
    
    # Mic Tracker Stats


# ... in your dashboard function ...

    mic_stats = {
        'total': MicAssignment.objects.count(),
        'micd': MicAssignment.objects.filter(is_micd=True).count(),
        'd_mic': MicAssignment.objects.filter(is_d_mic=True).count(),
        'available': MicAssignment.objects.filter(is_micd=False).count(),
        'shared': MicAssignment.objects.annotate(
            presenter_count=Count('shared_presenters')
        ).filter(presenter_count__gt=0).count(),
    }
    
    # Comm Stats
    comm_stats = {
        'total_packs': CommBeltPack.objects.count(),
        'wireless': CommBeltPack.objects.filter(system_type='Wireless').count(),
        'hardwired': CommBeltPack.objects.filter(system_type='Hardwired').count(),
        'checked_out': CommBeltPack.objects.filter(checked_out=True).count(),
    }
    
    # Power Distribution Stats
    power_stats = {
        'plans': PowerDistributionPlan.objects.count(),
        'amps_in_plans': PowerDistributionPlan.objects.aggregate(
            total=Count('amplifier_assignments')
        )['total'] or 0,
    }
    
   # Soundvision Stats
    soundvision_stats = {
        'predictions': SoundvisionPrediction.objects.count(),
        'arrays': SoundvisionPrediction.objects.aggregate(
            total=Count('speaker_arrays')  # ← CORRECT (with underscore)
        )['total'] or 0,
}
    
    # Recent Activity - Last 10 changes across key models
    recent_show_days = ShowDay.objects.order_by('-id')[:3]
    recent_sessions = MicSession.objects.select_related('show_day').order_by('-id')[:5]
    recent_cables = PACableSchedule.objects.order_by('-id')[:5]
    
    # Quick Status Checks
    status_checks = {
        'has_consoles': Console.objects.exists(),
        'has_devices': Device.objects.exists(),
        'has_amps': Amp.objects.exists(),
        'has_show_days': ShowDay.objects.exists(),
        'has_comm': CommBeltPack.objects.exists(),
    }
    
    context = {
        'console_stats': console_stats,
        'device_stats': device_stats,
        'processor_stats': processor_stats,
        'amp_stats': amp_stats,
        'pa_cable_stats': pa_cable_stats,
        'mic_stats': mic_stats,
        'comm_stats': comm_stats,
        'power_stats': power_stats,
        'soundvision_stats': soundvision_stats,
        'recent_show_days': recent_show_days,
        'recent_sessions': recent_sessions,
        'recent_cables': recent_cables,
        'status_checks': status_checks,
    }
    
    return render(request, 'planner/dashboard.html', context)




#---------IP Address Module----


@staff_member_required
def ip_address_report(request):
    """
    Interactive IP Address Management page.
    Displays all IP addresses across all modules with inline editing.
    """
    from .models import Console, Device, Amp, SystemProcessor, CommBeltPack
    
    # Get current project from session/middleware
    current_project = getattr(request, 'current_project', None)
    
    # If no project selected, show empty or redirect
    if not current_project:
        context = {
            'title': 'IP Address Management',
            'modules': [],
            'no_project': True,
        }
        return render(request, 'admin/planner/ip_address_report.html', context)
    
    # Get all records with IP addresses - FILTERED BY PROJECT
    consoles = Console.objects.filter(project=current_project).order_by('name')
    devices = Device.objects.filter(project=current_project).order_by('name')
    amps = Amp.objects.filter(project=current_project).order_by('location__name', 'name')
    processors = SystemProcessor.objects.filter(project=current_project).order_by('device_type', 'name')
    belt_packs = CommBeltPack.objects.filter(project=current_project, system_type='HARDWIRED').order_by('bp_number')
    
    # Organize data by module type
    context = {
        'title': 'IP Address Management',
        'modules': [
            {
                'name': 'Mixing Consoles',
                'model_name': 'console',
                'app_label': 'planner',
                'items': [
                    {
                        'id': console.id,
                        'name': console.name,
                        'primary_ip': console.primary_ip_address or '',
                        'secondary_ip': console.secondary_ip_address or '',
                        'has_dual_ip': True,
                        'admin_url': f'/admin/planner/console/{console.id}/change/'
                    }
                    for console in consoles
                ]
            },
            {
                'name': 'I/O Devices',
                'model_name': 'device',
                'app_label': 'planner',
                'items': [
                    {
                        'id': device.id,
                        'name': device.name,
                        'primary_ip': device.primary_ip_address or '',
                        'secondary_ip': device.secondary_ip_address or '',
                        'has_dual_ip': True,
                        'admin_url': f'/admin/planner/device/{device.id}/change/'
                    }
                    for device in devices
                ]
            },
            {
                'name': 'Amplifiers',
                'model_name': 'amp',
                'app_label': 'planner',
                'items': [
                    {
                        'id': amp.id,
                        'name': amp.name,
                        'location': amp.location.name if amp.location else 'No Location',
                        'ip_address': amp.ip_address or '',
                        'has_dual_ip': False,
                        'admin_url': f'/admin/planner/amp/{amp.id}/change/'
                    }
                    for amp in amps
                ]
            },
            {
                'name': 'System Processors',
                'model_name': 'systemprocessor',
                'app_label': 'planner',
                'items': [
                    {
                        'id': processor.id,
                        'name': processor.name,
                        'device_type': processor.get_device_type_display() if hasattr(processor, 'get_device_type_display') else processor.device_type,
                        'ip_address': processor.ip_address or '',
                        'has_dual_ip': False,
                        'admin_url': f'/admin/planner/systemprocessor/{processor.id}/change/'
                    }
                    for processor in processors
                ]
            },
            *[
                {
                    'name': f'COMM Config — {config.name}',
                    'model_name': 'commconfigrole',
                    'app_label': 'planner',
                    'items': [
                        {
                            'id': role.id,
                            'name': role.label,
                            'position': role.get_device_type_display(),
                            'ip_address': role.ip_address or '',
                            'has_dual_ip': False,
                            'admin_url': f'/audiopatch/comm-config/{config.id}/',
                        }
                        for role in config.roles.filter(
                            device_type__in=['FSII-BP', 'E-BP', 'HBP-2X', 'HMS-4X', 'HRM-4X', 'V12', 'V24', 'V32']
                        ).order_by('role_number')
                    ]
                }
                for config in CommConfig.objects.filter(
                    project=current_project, is_template=False
                ).order_by('name')
                if config.roles.filter(
                    device_type__in=['FSII-BP', 'E-BP', 'HBP-2X', 'HMS-4X', 'HRM-4X', 'V12', 'V24', 'V32']
                ).exists()
            ],
            {
                'name': 'COMM Belt Packs (Hardwired)',
                'model_name': 'commbeltpack',
                'app_label': 'planner',
                'items': [
                    {
                        'id': bp.id,
                        'name': f"BP{bp.bp_number}",
                        'position': bp.position or '—',
                        'crew_name': bp.name or '—',
                        'ip_address': bp.ip_address or '',
                        'has_dual_ip': False,
                        'admin_url': f'/admin/planner/commbeltpack/{bp.id}/change/'
                    }
                    for bp in belt_packs
                ]
            },
        ]
    }
    
    return render(request, 'admin/planner/ip_address_report.html', context)


@staff_member_required
@require_http_methods(["POST"])
def save_ip_address(request):
    """
    AJAX endpoint to save IP address changes.
    Handles both single and dual IP address fields.
    """
    try:
        from .models import Console, Device, Amp, SystemProcessor, CommBeltPack
        
        data = json.loads(request.body)
        model_name = data.get('model_name')
        object_id = data.get('object_id')
        field_name = data.get('field_name')  # 'primary_ip_address', 'secondary_ip_address', or 'ip_address'
        ip_value = data.get('ip_value', '').strip()
        
        # Validate required fields
        if not all([model_name, object_id, field_name]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
        
        # Get the appropriate model
        model_map = {
            'console': Console,
            'device': Device,
            'amp': Amp,
            'systemprocessor': SystemProcessor,
            'commbeltpack': CommBeltPack,
        }
        
        model = model_map.get(model_name.lower())
        if not model:
            return JsonResponse({
                'success': False,
                'error': f'Invalid model: {model_name}'
            }, status=400)
        
        # Get the object
        try:
            obj = model.objects.get(id=object_id)
        except model.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'{model_name} with id {object_id} not found'
            }, status=404)
        
        # Validate field name
        if not hasattr(obj, field_name):
            return JsonResponse({
                'success': False,
                'error': f'Invalid field: {field_name}'
            }, status=400)
        
        # Set the IP address (empty string becomes None for the database)
        setattr(obj, field_name, ip_value if ip_value else None)
        obj.save()
        
        return JsonResponse({
            'success': True,
            'message': f'IP address updated successfully',
            'ip_value': ip_value or '—'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)



# Device I/O PDF Export
# Add/Update these functions in your planner/views.py file

def all_devices_pdf_export(request):
    """Export all devices to PDF - filtered by current project"""
    
    # Get current project - CRITICAL for multi-tenancy
    if not hasattr(request, 'current_project') or not request.current_project:
        return HttpResponse("No project selected. Please select a project first.", status=403)
    
    # Import and call the PDF export with current project
    from planner.utils.pdf_exports.device_pdf import export_all_devices_pdf
    
    # PASS THE CURRENT PROJECT to the export function
    return export_all_devices_pdf(request.current_project)


def device_pdf_export(request, device_id):
    """Export single device to PDF"""
    from planner.models import Device
    from planner.utils.pdf_exports.device_pdf import export_device_pdf
    from django.shortcuts import get_object_or_404
    
    # Get device and ensure it belongs to current project
    device = get_object_or_404(Device, id=device_id)
    
    # Security check - ensure device belongs to current project
    if hasattr(request, 'current_project') and request.current_project:
        if device.project != request.current_project:
            return HttpResponse("Access denied - device not in current project", status=403)
    
    return export_device_pdf(device)




#-------Amplifier PDF Export----

# Amplifier PDF Export

@require_POST
def amp_reorder(request):
    """Reorder an amp within its location group"""
    try:
        data = json.loads(request.body)
        amp = get_object_or_404(Amp, id=data['amp_id'])
        direction = data.get('direction')  # 'up' or 'down'
        location_items = get_location_items(amp.location, amp.project)
        idx = next((i for i, item in enumerate(location_items) if item.get('type') == 'amp' and item['obj'].id == amp.id), None)
        if idx is None:
            return JsonResponse({'success': False, 'error': 'Amp not found'})
        if direction == 'up' and idx > 0:
            swap_idx = idx - 1
        elif direction == 'down' and idx < len(location_items) - 1:
            swap_idx = idx + 1
        else:
            return JsonResponse({'success': False, 'error': 'Cannot move'})
        # Swap sort_orders
        item_a = location_items[idx]
        item_b = location_items[swap_idx]
        a_order = item_a['obj'].sort_order
        b_order = item_b['obj'].sort_order
        item_a['obj'].sort_order = b_order
        item_b['obj'].sort_order = a_order
        item_a['obj'].save()
        item_b['obj'].save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
def amp_divider_add(request):
    """Add a new divider to a location"""
    try:
        data = request.POST
        location = get_object_or_404(AmpLocation, id=data['location_id'])
        project = get_object_or_404(Project, id=data['project_id'])
        # Place at end of location items
        location_items = get_location_items(location, project)
        max_order = max((item['obj'].sort_order for item in location_items), default=-1)
        divider = AmpDivider.objects.create(
            project=project,
            location=location,
            label=data.get('label', ''),
            sort_order=max_order + 1
        )
        return JsonResponse({'success': True, 'divider_id': divider.id, 'sort_order': divider.sort_order})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
def amp_divider_update(request, divider_id):
    """Update a divider label"""
    try:
        data = request.POST
        divider = get_object_or_404(AmpDivider, id=divider_id)
        divider.label = data.get('label', '')
        divider.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
def amp_divider_delete(request, divider_id):
    """Delete a divider"""
    try:
        divider = get_object_or_404(AmpDivider, id=divider_id)
        divider.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
def amp_divider_reorder(request, divider_id):
    """Move a divider up or down.

    Issue #27: AmpDivider.sort_order stores the `after` index (which amp
    to sit below). 'up' decrements toward -1 (before first amp), 'down'
    increments toward N (after last amp). The previous swap-with-
    adjacent logic was from the old changelist and produced wrong
    positions in the rack render path.
    """
    try:
        divider = get_object_or_404(AmpDivider, id=divider_id)
        direction = request.POST.get('direction')
        amp_count = Amp.objects.filter(
            location=divider.location, project=divider.project,
        ).count()
        if direction == 'up':
            divider.sort_order = max(-1, divider.sort_order - 1)
        elif direction == 'down':
            divider.sort_order = min(amp_count, divider.sort_order + 1)
        else:
            return JsonResponse({'success': False, 'error': 'Bad direction'})
        divider.save(update_fields=['sort_order'])
        return JsonResponse({'success': True, 'sort_order': divider.sort_order})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def get_location_items(location, project):
    """Return interleaved list of amps and dividers sorted by sort_order"""
    amps = list(Amp.objects.filter(location=location, project=project).order_by('sort_order', 'name'))
    dividers = list(AmpDivider.objects.filter(location=location, project=project).order_by('sort_order'))
    items = [{'type': 'amp', 'obj': a} for a in amps] + [{'type': 'divider', 'obj': d} for d in dividers]
    items.sort(key=lambda x: x['obj'].sort_order)
    return items


@require_POST
def amp_divider_sync(request):
    """Sync all dividers for a location from localStorage state"""
    try:
        location = get_object_or_404(AmpLocation, id=request.POST.get('location_id'))
        project = get_object_or_404(Project, id=request.POST.get('project_id'))
        dividers_data = json.loads(request.POST.get('dividers', '[]'))
        
        # Get existing dividers for this location
        existing = {d.id: d for d in AmpDivider.objects.filter(location=location, project=project)}
        seen_ids = set()
        
        result = []
        for i, d in enumerate(dividers_data):
            # Issue #25: the changelist tracks divider position as an `after`
            # index (which amp to sit below). The rack view needs the same
            # position server-side so it can mirror the changelist layout,
            # so persist `after` into sort_order. Falls back to the array
            # index when `after` is missing (legacy clients).
            after = d.get('after')
            if after is None:
                after = i
            db_id = d.get('id')
            if db_id and db_id in existing:
                div = existing[db_id]
                div.label = d.get('label', '')
                div.sort_order = after
                div.save()
                seen_ids.add(db_id)
            else:
                div = AmpDivider.objects.create(
                    location=location, project=project,
                    label=d.get('label', ''), sort_order=after,
                )
                seen_ids.add(div.id)
            result.append({'db_id': div.id, 'sort_order': after})
        
        # Delete removed dividers
        for did, div in existing.items():
            if did not in seen_ids:
                div.delete()
        
        return JsonResponse({'success': True, 'dividers': result})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# --------- Issue #27: inline edit endpoints for the unified rack page ---------

# Fields editable inline on an Amp card.
_INLINE_AMP_FIELDS = (
    {'name', 'ip_address', 'preset'}
    | {f'output_{i}' for i in (1, 2, 3, 4)}
    | {f'nl4_{a}_pair_{i}' for a in 'ab' for i in (1, 2)}
    | {f'nl8_{a}_pair_{i}' for a in 'ab' for i in (1, 2, 3, 4)}
    | {f'cacom_{c}_ch{n}' for c in (1, 2, 3, 4) for n in (1, 2, 3, 4)}
    | {f'sc32_ch{n}' for n in range(1, 17)}
)
_INLINE_CHANNEL_FIELDS = {'channel_name', 'avb_stream', 'aes_input', 'analog_input', 'channel_setting'}


def _project_or_403(request):
    project = getattr(request, 'current_project', None)
    if not project:
        return None
    return project


@require_POST
@login_required
def amp_inline_update(request, amp_id):
    """Issue #27: update a single Amp field from the rack page.

    Whitelists which fields the client can write so a stray JS bug or
    malicious POST can't reach e.g. `project_id` and re-tenant the row.
    """
    project = _project_or_403(request)
    if not project:
        return JsonResponse({'success': False, 'error': 'No project'}, status=400)
    amp = get_object_or_404(Amp, id=amp_id, project=project)
    field = request.POST.get('field', '')
    if field not in _INLINE_AMP_FIELDS:
        return JsonResponse({'success': False, 'error': f'Field {field!r} not editable'}, status=400)
    value = request.POST.get('value', '')
    if field == 'ip_address':
        value = value.strip() or None
    setattr(amp, field, value)
    try:
        amp.save(update_fields=[field])
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': True})


@require_POST
@login_required
def amp_channel_inline_update(request, channel_id):
    """Issue #27: update a single AmpChannel field from the rack page."""
    project = _project_or_403(request)
    if not project:
        return JsonResponse({'success': False, 'error': 'No project'}, status=400)
    channel = get_object_or_404(AmpChannel, id=channel_id, amp__project=project)
    field = request.POST.get('field', '')
    if field not in _INLINE_CHANNEL_FIELDS:
        return JsonResponse({'success': False, 'error': f'Field {field!r} not editable'}, status=400)
    value = request.POST.get('value', '')
    setattr(channel, field, value)
    channel.save(update_fields=[field])
    return JsonResponse({'success': True})


@require_POST
@login_required
def mic_assignment_delete(request, mic_id):
    """Issue #36: one-click delete for a MicAssignment row inside the
    MicSession admin change form. Posts here from the inline's "X"
    button instead of using Django's default "Delete?" checkbox."""
    mic = get_object_or_404(MicAssignment, id=mic_id)
    project = mic.session.day.project
    allowed = (
        request.user.is_superuser
        or project.owner_id == request.user.id
        or ProjectMember.objects.filter(
            user=request.user, project=project, role='editor'
        ).exists()
    )
    if not allowed:
        return JsonResponse({'success': False, 'error': 'Not allowed'}, status=403)
    mic.delete()
    return JsonResponse({'success': True})


@require_POST
@login_required
def mic_assignment_reorder(request):
    """Issue #38: drag-and-drop reorder of presenters between MicAssignment
    rows in the mic tracker.

    Body (JSON):
        action: 'swap' or 'move'
        source_id: MicAssignment.id being dragged
        target_id: MicAssignment.id being dropped on (swap) or near (move)
        position: 'above' or 'below' (move only)

    Mutates only the active PresenterSlot's `presenter` field on each
    affected row. Hardware-bound fields (rf_number, mic_type, placement,
    sensitivity, output_level, shared_presenters) stay where they were.
    """
    MULTI_SLOT_ERR = (
        "Drag-and-drop is only supported for single-presenter rows. "
        "Edit multi-presenter rows manually."
    )

    try:
        data = json.loads(request.body)
        action = data.get('action')
        source_id = int(data['source_id'])
        target_id = int(data['target_id'])
        position = data.get('position', 'above')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Bad request'}, status=400)

    if action not in ('swap', 'move'):
        return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)
    if position not in ('above', 'below'):
        return JsonResponse({'success': False, 'error': 'Invalid position'}, status=400)
    if source_id == target_id:
        return JsonResponse({'success': True})

    try:
        source = MicAssignment.objects.select_related('session__day__project').get(id=source_id)
        target = MicAssignment.objects.select_related('session__day__project').get(id=target_id)
    except MicAssignment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    if source.session_id != target.session_id:
        return JsonResponse({
            'success': False, 'error': 'Cross-session reorder not supported'
        }, status=400)

    project = source.session.day.project
    allowed = (
        request.user.is_superuser
        or project.owner_id == request.user.id
        or ProjectMember.objects.filter(
            user=request.user, project=project, role='editor'
        ).exists()
    )
    if not allowed:
        return JsonResponse({'success': False, 'error': 'Not allowed'}, status=403)

    def _ensure_active_slot(assignment):
        slot = assignment.presenter_slots.filter(is_active=True).first()
        if not slot:
            slot = assignment.presenter_slots.order_by('order').first()
        if not slot:
            slot = PresenterSlot.objects.create(
                assignment=assignment, order=0, is_active=True
            )
        return slot

    with transaction.atomic():
        if action == 'swap':
            if source.presenter_slots.count() > 1 or target.presenter_slots.count() > 1:
                return JsonResponse({'success': False, 'error': MULTI_SLOT_ERR}, status=400)
            src_slot = _ensure_active_slot(source)
            tgt_slot = _ensure_active_slot(target)
            src_slot.presenter, tgt_slot.presenter = tgt_slot.presenter, src_slot.presenter
            src_slot.save(update_fields=['presenter'])
            tgt_slot.save(update_fields=['presenter'])
        else:  # move — kanban rotation across single-presenter rows
            assignments = list(
                source.session.mic_assignments.order_by('rf_number')
            )
            ids = [a.id for a in assignments]
            source_idx = ids.index(source_id)
            target_idx = ids.index(target_id)

            lo, hi = min(source_idx, target_idx), max(source_idx, target_idx)
            for a in assignments[lo:hi + 1]:
                if a.presenter_slots.count() > 1:
                    return JsonResponse({'success': False, 'error': MULTI_SLOT_ERR}, status=400)

            slots = [_ensure_active_slot(a) for a in assignments]
            presenters = [s.presenter for s in slots]

            moved = presenters.pop(source_idx)
            insert_idx = target_idx
            if source_idx < target_idx:
                insert_idx -= 1
            if position == 'below':
                insert_idx += 1
            insert_idx = max(0, min(insert_idx, len(presenters)))
            presenters.insert(insert_idx, moved)

            for slot, new_p in zip(slots, presenters):
                if (slot.presenter_id or None) != (new_p.id if new_p else None):
                    slot.presenter = new_p
                    slot.save(update_fields=['presenter'])

    return JsonResponse({'success': True})


@require_POST
@login_required
def amp_inline_create(request):
    """Issue #27: create a new Amp from the rack page's per-location
    '+ Add Amp' button. Takes the minimum needed to scaffold channels
    (location + amp_model + name); everything else gets edited inline."""
    from .models import AmpModel
    project = _project_or_403(request)
    if not project:
        return JsonResponse({'success': False, 'error': 'No project'}, status=400)
    try:
        location = get_object_or_404(AmpLocation, id=request.POST.get('location_id'), project=project)
        amp_model = get_object_or_404(AmpModel, id=request.POST.get('amp_model_id'))
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    name = (request.POST.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'Name required'}, status=400)
    amp = Amp.objects.create(
        project=project,
        location=location,
        amp_model=amp_model,
        name=name,
    )
    return JsonResponse({'success': True, 'amp_id': amp.id})


def all_amps_pdf_export(request):
    """Export all amplifiers to PDF - filtered by current project"""
    
    # Get current project - CRITICAL for multi-tenancy
    if not hasattr(request, 'current_project') or not request.current_project:
        return HttpResponse("No project selected. Please select a project first.", status=403)
    
    # Import and call the PDF export with current project
    from planner.utils.pdf_exports.amplifier_pdf import export_all_amps_pdf
    
    # PASS THE CURRENT PROJECT to the export function
    return export_all_amps_pdf(request.current_project)




#-------PA Schedule PDF-------
def all_pa_cables_pdf_export(request):
    """Export all PA cables to PDF."""
    from .models import PACableSchedule
    from .utils.pdf_exports.pa_cable_pdf import generate_pa_cable_pdf
    
    # Filter by current project and preserve ordering
    if hasattr(request, 'current_project') and request.current_project:
        queryset = PACableSchedule.objects.filter(
            project=request.current_project
        ).select_related('label').order_by('label__name', 'destination')
    else:
        queryset = PACableSchedule.objects.none()
    
    pdf = generate_pa_cable_pdf(queryset)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="pa_cable_schedule.pdf"'
    return response


#--------Comm Beltpack PDF-----

def all_comm_beltpacks_pdf_export(request):
    """Export all Comm Belt Packs to PDF."""
    from .utils.pdf_exports.comm_pdf import generate_comm_beltpacks_pdf
    
    pdf = generate_comm_beltpacks_pdf()
    
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="comm_beltpacks.pdf"'
    return response



#----Import Comm Crew Names---
def import_comm_crew_names_csv(request):
    """Import Comm Crew Names from CSV (Column A only)."""
    from planner.models import CommCrewName, Project
    import csv
    from io import TextIOWrapper
    
    # Get current project
    if not hasattr(request, 'current_project') or not request.current_project:
        messages.error(request, "No project selected. Please select a project first.")
        return HttpResponseRedirect(reverse('admin:planner_commcrewname_changelist'))
    
    if isinstance(request.current_project, Project):
        project = request.current_project
    else:
        try:
            project = Project.objects.get(id=request.current_project)
        except Project.DoesNotExist:
            messages.error(request, "Invalid project selected.")
            return HttpResponseRedirect(reverse('admin:planner_commcrewname_changelist'))
    
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        
        # Decode the file
        try:
            file_data = TextIOWrapper(csv_file.file, encoding='utf-8')
            csv_reader = csv.reader(file_data)
            
            imported = 0
            skipped = 0
            errors = []
            
            for row_num, row in enumerate(csv_reader, start=1):
                # Skip empty rows
                if not row or not row[0].strip():
                    continue
                
                # Get name from Column A (first column)
                name = row[0].strip()
                
                # Skip header row if it looks like a header
                if row_num == 1 and name.lower() in ['name', 'crew name', 'crew', 'names']:
                    continue
                
                # Try to create the crew name
                try:
                    CommCrewName.objects.get_or_create(
                        name=name,
                        project=project  # ✅ Add project
                    )
                    imported += 1
                except Exception as e:
                    errors.append(f"Row {row_num}: {name} - {str(e)}")
                    skipped += 1
            
            # Success message
            if errors:
                messages.warning(
                    request,
                    f"Import completed with issues. Imported: {imported}, Skipped: {skipped}. Errors: {', '.join(errors[:5])}"
                )
            else:
                messages.success(
                    request,
                    f"Successfully imported {imported} crew names. Skipped {skipped} duplicates."
                )
                
        except Exception as e:
            messages.error(request, f"Error reading CSV file: {str(e)}")
        
        return HttpResponseRedirect(reverse('admin:planner_commcrewname_changelist'))
    
    # GET request - show upload form
    from django.template.response import TemplateResponse
    context = {
        'title': 'Import Comm Crew Names from CSV',
        'opts': CommCrewName._meta,
    }
    return TemplateResponse(request, 'admin/planner/commcrewname/import_csv.html', context)




#--------System Processor PDF Expport----

# Update this function in planner/views.py

def export_system_processor_pdf(request):
    """Export system processors as PDF - filtered by current project"""
    
    # Get current project - CRITICAL for multi-tenancy
    if not hasattr(request, 'current_project') or not request.current_project:
        return HttpResponse("No project selected. Please select a project first.", status=403)
    
    from planner.utils.pdf_exports.system_processor_pdf import generate_system_processor_pdf
    
    # PASS THE CURRENT PROJECT to the export function
    pdf = generate_system_processor_pdf(request.current_project)
    
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="system_processors.pdf"'
    return response



#-------<Mic Tracker Presenters .CSV Import---
@staff_member_required
def import_presenters_csv(request):
    """Import presenters from CSV file"""
    from planner.models import Project
    
    # Get current project
    if not hasattr(request, 'current_project') or not request.current_project:
        messages.error(request, "No project selected. Please select a project first.")
        return redirect('admin:planner_presenter_changelist')
    
    if isinstance(request.current_project, Project):
        project = request.current_project
    else:
        try:
            project = Project.objects.get(id=request.current_project)
        except Project.DoesNotExist:
            messages.error(request, "Invalid project selected.")
            return redirect('admin:planner_presenter_changelist')
    
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        
        try:
            # Read CSV file
            decoded_file = csv_file.read().decode('utf-8')
            csv_reader = csv.reader(decoded_file.splitlines())
            
            imported_count = 0
            skipped_count = 0
            
            for row in csv_reader:
                if row and row[0].strip():  # Check if Column A has data
                    name = row[0].strip()
                    
                    # Skip header rows (common headers)
                    if name.lower() in ['name', 'presenter', 'names', 'presenters']:
                        continue
                    
                    # Get or create presenter with project
                    presenter, created = Presenter.objects.get_or_create(
                        name=name,
                        project=project  # ✅ Add project
                    )
                    
                    if created:
                        imported_count += 1
                    else:
                        skipped_count += 1
            
            messages.success(
                request,
                f'Successfully imported {imported_count} presenters. '
                f'Skipped {skipped_count} duplicates.'
            )
            
        except Exception as e:
            messages.error(request, f'Error importing CSV: {str(e)}')
        
        return redirect('admin:planner_presenter_changelist')
    
    return render(request, 'admin/planner/presenter/import_csv.html')




#-------SoundVidsion PDF Export----
# Add this to planner/views.py




@staff_member_required
def export_soundvision_pdf(request, prediction_id):
    """Export Soundvision Prediction as PDF"""
    from planner.utils.pdf_exports.soundvision_pdf import generate_soundvision_pdf
    
    prediction = get_object_or_404(SoundvisionPrediction, id=prediction_id)
    pdf = generate_soundvision_pdf(prediction)
    
    response = HttpResponse(pdf, content_type='application/pdf')
    filename = f"Soundvision_{prediction.file_name.replace(' ', '_')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response



#------Ip Address Report PDF Export

@staff_member_required
def export_ip_address_report_pdf(request):
    """
    Export IP Address Report as PDF.
    """
    from .utils.pdf_exports.ip_address_report_pdf import generate_ip_address_report_pdf

    
    # Generate PDF
    buf = generate_ip_address_report_pdf(project=getattr(request, "current_project", None))
    
    # Return as download
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="IP_Address_Report.pdf"'
    
    return response


#-----Ip Address CSV Export-----

@staff_member_required
def export_ip_address_report_csv(request):
    """
    Export IP Address Report as CSV for spreadsheet import.
    """
    import csv

    from .models import Console, Device, Amp, SystemProcessor, CommBeltPack
    current_project = getattr(request, 'current_project', None)
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="IP_Address_Report.csv"'
    
    writer = csv.writer(response)
    
    # ==================== MIXING CONSOLES ====================
    writer.writerow(['MIXING CONSOLES'])
    writer.writerow(['Console Name', 'Primary IP Address', 'Secondary IP Address'])
    
    consoles = Console.objects.filter(project=current_project).order_by('name') if current_project else Console.objects.none()
    if consoles.exists():
        for console in consoles:
            writer.writerow([
                console.name,
                console.primary_ip_address or '',
                console.secondary_ip_address or ''
            ])
    else:
        writer.writerow(['No consoles defined'])
    
    writer.writerow([])  # Blank line
    
    # ==================== I/O DEVICES ====================
    writer.writerow(['I/O DEVICES'])
    writer.writerow(['Device Name', 'Primary IP Address', 'Secondary IP Address'])
    
    devices = Device.objects.filter(project=current_project).order_by('name') if current_project else Device.objects.none()
    if devices.exists():
        for device in devices:
            writer.writerow([
                device.name,
                device.primary_ip_address or '',
                device.secondary_ip_address or ''
            ])
    else:
        writer.writerow(['No I/O devices defined'])
    
    writer.writerow([])  # Blank line
    
    # ==================== AMPLIFIERS ====================
    writer.writerow(['AMPLIFIERS'])
    writer.writerow(['Amplifier Name', 'Location', 'IP Address (AVB Network)'])
    
    amps = Amp.objects.filter(project=current_project).order_by('location__name', 'name') if current_project else Amp.objects.none()
    if amps.exists():
        for amp in amps:
            writer.writerow([
                amp.name,
                amp.location.name if amp.location else 'No Location',
                amp.ip_address or ''
            ])
    else:
        writer.writerow(['No amplifiers defined'])
    
    writer.writerow([])  # Blank line
    
    # ==================== SYSTEM PROCESSORS ====================
    writer.writerow(['SYSTEM PROCESSORS'])
    writer.writerow(['Processor Name', 'Type', 'IP Address (AVB Network)'])
    
    processors = SystemProcessor.objects.filter(project=current_project).order_by('device_type', 'name') if current_project else SystemProcessor.objects.none()
    if processors.exists():
        for processor in processors:
            device_type = processor.get_device_type_display() if hasattr(processor, 'get_device_type_display') else processor.device_type
            writer.writerow([
                processor.name,
                device_type,
                processor.ip_address or ''
            ])
    else:
        writer.writerow(['No system processors defined'])
    
    writer.writerow([])  # Blank line
    
    # ==================== COMM CONFIG BELTPACKS ====================
    comm_configs = CommConfig.objects.filter(project=current_project, is_template=False).order_by('name') if current_project else CommConfig.objects.none()
    for config in comm_configs:
        roles = config.roles.filter(
            device_type__in=['FSII-BP', 'E-BP', 'HBP-2X', 'HMS-4X', 'HRM-4X', 'V12', 'V24', 'V32']
        ).order_by('role_number')
        if roles.exists():
            writer.writerow([f'COMM CONFIG — {config.name.upper()}'])
            writer.writerow(['Role Name', 'Device Type', 'IP Address'])
            for role in roles:
                writer.writerow([
                    role.label,
                    role.get_device_type_display(),
                    role.ip_address or ''
                ])
            writer.writerow([])

    # ==================== COMM BELT PACKS (HARDWIRED) ====================
    writer.writerow(['COMM BELT PACKS (HARDWIRED)'])
    writer.writerow(['BP #', 'Position', 'Name', 'IP Address'])
    
    belt_packs = CommBeltPack.objects.filter(project=current_project, system_type='HARDWIRED').order_by('bp_number') if current_project else CommBeltPack.objects.none()
    if belt_packs.exists():
        for bp in belt_packs:
            writer.writerow([
                f"BP{bp.bp_number}",
                bp.position or '',
                bp.name or '',
                bp.ip_address or ''
            ])
    else:
        writer.writerow(['No hardwired belt packs defined'])
    
    writer.writerow([])  # Blank line
    
    # ==================== SUMMARY ====================
    writer.writerow(['SUMMARY'])
    writer.writerow(['Module', 'IP Addresses Assigned'])
    
    # Count IPs
    console_ips = sum([
        1 if c.primary_ip_address else 0 for c in consoles
    ] + [
        1 if c.secondary_ip_address else 0 for c in consoles
    ])
    
    device_ips = sum([
        1 if d.primary_ip_address else 0 for d in devices
    ] + [
        1 if d.secondary_ip_address else 0 for d in devices
    ])
    
    amp_ips = sum([1 if a.ip_address else 0 for a in amps])
    processor_ips = sum([1 if p.ip_address else 0 for p in processors])
    bp_ips = sum([1 if bp.ip_address else 0 for bp in belt_packs])
    total_ips = console_ips + device_ips + amp_ips + processor_ips + bp_ips
    
    writer.writerow(['Mixing Consoles', console_ips])
    writer.writerow(['I/O Devices', device_ips])
    writer.writerow(['Amplifiers', amp_ips])
    writer.writerow(['System Processors', processor_ips])
    writer.writerow(['COMM Belt Packs (Hardwired)', bp_ips])
    writer.writerow(['TOTAL', total_ips])
    
    return response



#-----Project Switcher View---


@staff_member_required
def switch_project(request, project_id):
    """Switch the current active project"""
    try:
        project = Project.objects.get(id=project_id)
        
        # Verify user has access
        if project.owner == request.user or \
           project.projectmember_set.filter(user=request.user).exists():
            request.session['current_project_id'] = project_id
            request.session.modified = True 
            
            # Redirect back to where they came from, or admin home if no referrer
            referer = request.META.get('HTTP_REFERER', '/admin/')
            return redirect(referer)
        else:
            return JsonResponse({'error': 'Access denied'}, status=403)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    


    #-------Admin action to populate amp models in Railway Databae  for Amp Assignments



from django.http import HttpResponse
from django.core.management import call_command

@staff_member_required
def populate_amp_models_view(request):
    """Admin view to populate amp models - only accessible by staff"""
    try:
        # Run the management command
        call_command('populate_amp_models')
        return HttpResponse("""
            <h1>✓ Success!</h1>
            <p>Amp models have been populated.</p>
            <p><a href="/admin/planner/ampmodel/">View Amp Models</a></p>
            <p><a href="/admin/">Back to Admin</a></p>
        """)
    except Exception as e:
        return HttpResponse(f"""
            <h1>✗ Error</h1>
            <p>Error populating amp models: {e}</p>
            <p><a href="/admin/">Back to Admin</a></p>
        """, status=500)

    
#------Auto Refresh for Mic Tracker------


@login_required
@require_http_methods(["GET"])
def mic_tracker_checksum(request):
    """Return a checksum of mic tracker data to detect changes."""
    project_id = request.session.get('current_project_id')
    if not project_id:
        return JsonResponse({'checksum': None})

    sessions = MicSession.objects.filter(
        day__project_id=project_id
    ).values('id', 'name', 'start_time', 'end_time').order_by('id')

    assignments = MicAssignment.objects.filter(
        session__day__project_id=project_id
    ).values('id', 'rf_number', 'is_micd', 'is_d_mic').order_by('id')

    # Include presenter slots so name/type/notes changes trigger refresh
    slots = PresenterSlot.objects.filter(
        assignment__session__day__project_id=project_id
    ).values('id', 'assignment_id', 'presenter_id', 'mic_type', 'is_micd', 'is_active').order_by('id')

    data_string = json.dumps({
        'sessions': list(sessions),
        'assignments': list(assignments),
        'slots': list(slots),
    }, default=str)

    checksum = hashlib.md5(data_string.encode()).hexdigest()
    return JsonResponse({'checksum': checksum})





from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
import json


@login_required
@require_POST
def create_day(request):
    """Create a new ShowDay for the current project."""
    try:
        data = json.loads(request.body)
        date_str = data.get('date')       # ISO format: YYYY-MM-DD
        name = data.get('name', '').strip()

        if not date_str:
            return JsonResponse({'success': False, 'error': 'Date is required.'})

        project_id = request.session.get('current_project_id')
        if not project_id:
            return JsonResponse({'success': False, 'error': 'No project selected.'})

        # unique_together = [['project', 'date']] so get_or_create is safe
        day, created = ShowDay.objects.get_or_create(
            project_id=project_id,
            date=date_str,
            defaults={'name': name}
        )

        if not created:
            return JsonResponse({'success': False, 'error': f'A day for {date_str} already exists.'})

        if name and not created:
            # Shouldn't reach here, but just in case
            day.name = name
            day.save()

        return JsonResponse({'success': True, 'day_id': day.id})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def create_session(request):
    """Create a new MicSession with blank mic assignments."""
    try:
        data = json.loads(request.body)
        day_id   = data.get('day_id')
        name     = data.get('name', '').strip()
        num_mics = int(data.get('num_mics', 16))
        location = data.get('location', '').strip()

        if not day_id:
            return JsonResponse({'success': False, 'error': 'day_id is required.'})
        if not name:
            return JsonResponse({'success': False, 'error': 'Session name is required.'})
        if not (1 <= num_mics <= 100):
            return JsonResponse({'success': False, 'error': 'Mic count must be between 1 and 100.'})

        day = ShowDay.objects.get(id=day_id)

        # Determine order (append after existing sessions)
        order = day.sessions.count()

        # MicSession.save() calls create_mic_assignments() automatically
        session = MicSession.objects.create(
            day=day,
            name=name,
            num_mics=num_mics,
            location=location,
            order=order,
        )

        # Each new assignment also needs a default PresenterSlot so the
        # A2 card and slot system works from the start.
        for assignment in session.mic_assignments.all():
            if not assignment.presenter_slots.exists():
                PresenterSlot.objects.create(
                    assignment=assignment,
                    order=0,
                    is_active=True,
                )

        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'num_mics': session.mic_assignments.count(),
        })

    except ShowDay.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Day not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    




    

# ─────────────────────────────────────────────────────────────
# COMM Config — Create
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_create(request):
    try:
        data = _json.loads(request.body)
        device_type = data.get('device_type', 'arcadia')
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        name = data.get('name', '').strip() or f"New {device_type.title()} Config"
        config = CommConfig.objects.create(
            project=current_project,
            name=name,
            device_type=device_type,
        )

        # Seed factory defaults
        if config.device_type == 'freespeak':
            _seed_freespeak_defaults(config)
        else:
            _seed_factory_defaults(config)

        return JsonResponse({'ok': True, 'config_id': config.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _seed_freespeak_defaults(config):
    """Populate a new FreeSpeak config with 12 default channels and ports."""
    for ch in range(1, 13):
        CommConfigPartyline.objects.create(
            config=config,
            channel_number=ch,
            label=f'Channel {ch}',
            helixnet_enabled=False,
        )
    # Seed ports
    port_defaults = [
        ('2W', '2W Port A', '2w_1'),
        ('2W', '2W Port B', '2w_2'),
        ('2W', '2W Port C', '2w_3'),
        ('2W', '2W Port D', '2w_4'),
        ('4W', '4W Port 1', '4w_1'),
        ('4W', '4W Port 2', '4w_2'),
        ('4W', '4W Port 3', '4w_3'),
        ('4W', '4W Port 4', '4w_4'),
        ('SA', 'SA',        'sa'),
        ('PGM', 'PGM',      'pgm'),
    ]
    for port_type, label, gid in port_defaults:
        CommConfigPortAssignment.objects.create(
            config=config,
            port_type=port_type,
            port_label=label,
            port_gid=gid,
        )


def _seed_factory_defaults(config):
    """
    Populate a new CommConfig with Arcadia factory defaults:
    4 partylines, 13 roles with keysets, 1 roleset, 2 sessions.
    """
    # ── Partylines ──
    partyline_defaults = [
        (1, 'PL 1'),
        (2, 'PL 2'),
        (3, 'PL 3'),
        (4, 'PL 4'),
    ]
    partylines = {}
    for ch, label in partyline_defaults:
        pl = CommConfigPartyline.objects.create(
            config=config,
            channel_number=ch,
            label=label,
            helixnet_enabled=True,
        )
        partylines[ch] = pl

    # ── Roles ──
    # Format: (role_number, device_type, label, is_default, keysets)
    # keysets: list of (key_index, partyline_ch_or_None, activation, talk_mode)
    role_defaults = []

    roles = {}
    for role_num, dev_type, label, is_default, keysets in role_defaults:
        role = CommConfigRole.objects.create(
            config=config,
            role_number=role_num,
            device_type=dev_type,
            label=label,
            is_default=is_default,
        )
        roles[role_num] = role
        for key_index, pl_ch, activation, talk_mode in keysets:
            CommConfigKeyset.objects.create(
                role=role,
                key_index=key_index,
                entity_type=0,  # Partyline
                partyline=partylines.get(pl_ch) if pl_ch else None,
                activation_state=activation,
                talk_mode=talk_mode,
            )

    # ── Roleset ──
    roleset = CommConfigRoleset.objects.create(
        config=config,
        roleset_number=1,
        label='Default',
        addressable=True,
    )

    # ── Sessions ──
    CommConfigSession.objects.create(
        config=config,
        session_type='B.FSII',
        label='Beltpack',
        roleset=roleset,
        default_role=roles.get(1),
    )
    CommConfigSession.objects.create(
        config=config,
        session_type='S.NEP',
        label='Station',
        roleset=roleset,
        default_role=roles.get(13),
    )


    # ── Physical Ports ──
    # 4x 2-Wire ports (labeled A-D like CCM)
    for i, letter in enumerate(['A', 'B', 'C', 'D'], 1):
        CommConfigPortAssignment.objects.create(
            config=config,
            port_type='2W',
            port_label=f'2W Port {letter}',
            port_gid=f'2w_{i}',
            join_mode='Talk-Listen',
            mode_2w='clearcom',
            power_enabled=False,
            termination_enabled=False,
        )
    # 8x 4-Wire ports
    for i in range(1, 9):
        CommConfigPortAssignment.objects.create(
            config=config,
            port_type='4W',
            port_label=f'4W Port {i}',
            port_gid=f'4w_{i}',
            join_mode='Talk-Listen',
            port_function='4wire-x',
            receive_call_signal=False,
            output_level='line',
        )


# ─────────────────────────────────────────────────────────────
# COMM Config — Partyline CRUD
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_update_partyline(request):
    try:
        data = _json.loads(request.body)
        pl = CommConfigPartyline.objects.get(id=data['partyline_id'])
        if 'label' in data:
            pl.label = data['label']
        if 'helixnet_enabled' in data:
            pl.helixnet_enabled = data['helixnet_enabled']
        pl.save()
        return JsonResponse({'ok': True})
    except CommConfigPartyline.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_add_partyline(request):
    try:
        data = _json.loads(request.body)
        config = CommConfig.objects.get(id=data['config_id'])
        # Next available channel number
        existing = config.partylines.values_list('channel_number', flat=True)
        next_ch = max(existing, default=0) + 1
        pl = CommConfigPartyline.objects.create(
            config=config,
            channel_number=next_ch,
            label=f'PL {next_ch}',
            helixnet_enabled=True,
        )
        return JsonResponse({'ok': True, 'partyline_id': pl.id, 'channel_number': pl.channel_number, 'label': pl.label})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_delete_partyline(request):
    try:
        data = _json.loads(request.body)
        pl = CommConfigPartyline.objects.get(id=data['partyline_id'])
        # Detach any keyset assignments pointing to this partyline
        CommConfigKeyset.objects.filter(partyline=pl).update(partyline=None, entity_type=None)
        pl.delete()
        return JsonResponse({'ok': True})
    except CommConfigPartyline.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Port Assignments
# Note: ports are created on import/.cca upload.
# ─────────────────────────────────────────────────────────────
# COMM Config — Keyset update
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_update_keyset(request):
    try:
        data = _json.loads(request.body)
        key = CommConfigKeyset.objects.get(id=data['keyset_id'])
        field = data.get('field')
        value = data.get('value')
        allowed = {'activation_state', 'talk_mode', 'partyline'}
        if field not in allowed:
            return JsonResponse({'error': f'Field "{field}" not editable'}, status=400)
        if field == 'partyline':
            if value == 'call':
                key.partyline = None
                key.is_call_key = True
                key.entity_type = None
            elif value:
                key.partyline = CommConfigPartyline.objects.get(id=value)
                key.is_call_key = False
                key.entity_type = 0
            else:
                key.partyline = None
                key.is_call_key = False
                key.entity_type = None
        else:
            setattr(key, field, value)
        key.save()
        return JsonResponse({'ok': True, 'role_id': key.role_id})
    except CommConfigKeyset.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Role update
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_update_role(request):
    try:
        data = _json.loads(request.body)
        role = CommConfigRole.objects.get(id=data['role_id'])
        if 'label' in data:
            role.label = data['label']
        role.save()
        return JsonResponse({'ok': True})
    except CommConfigRole.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Role delete
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_delete_role(request):
    try:
        data = _json.loads(request.body)
        role = CommConfigRole.objects.get(id=data['role_id'])
        role.delete()
        return JsonResponse({'ok': True})
    except CommConfigRole.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)




# ─────────────────────────────────────────────────────────────
# COMM Config — Add Role
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_add_role(request):
    try:
        data = _json.loads(request.body)
        config = CommConfig.objects.get(id=data['config_id'])
        device_type = data['device_type']
        label = data['label']
        role_number = int(data.get('role_number', 1))
        # Ensure unique role number
        while CommConfigRole.objects.filter(config=config, role_number=role_number).exists():
            role_number += 1
        role = CommConfigRole.objects.create(
            config=config,
            role_number=role_number,
            device_type=device_type,
            label=label,
        )
        # Seed empty keysets based on device max_keysets
        reply_key_index = role.max_keysets - 1 if device_type in ('FSII-BP', 'E-BP') else None
        for i in range(role.max_keysets):
            is_reply = (i == reply_key_index)
            CommConfigKeyset.objects.create(
                role=role,
                key_index=i,
                activation_state='talk' if is_reply else 'talkforcelisten',
                talk_mode='disabled' if is_reply else 'latching',
                is_reply_key=is_reply,
            )
        return JsonResponse({'ok': True, 'role_id': role.id})
    except CommConfig.DoesNotExist:
        return JsonResponse({'error': 'Config not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Role chips (refresh after keyset change)
# ─────────────────────────────────────────────────────────────
def comm_config_role_chips(request):
    try:
        role_id = request.GET.get('role_id')
        role = CommConfigRole.objects.get(id=role_id)
        chips = []
        for key in role.keysets.all().order_by('key_index'):
            chips.append({
                'letter': key.key_letter,
                'assigned': bool(key.partyline_id),
                'label': key.partyline.label[:8] if key.partyline else '',
            })
        return JsonResponse({'ok': True, 'chips': chips})
    except CommConfigRole.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# This endpoint only assigns an existing port to a partyline.
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_assign_port(request):
    try:
        data = _json.loads(request.body)
        port = CommConfigPortAssignment.objects.get(id=data['port_id'])
        pl_id = data.get('partyline_id')
        allowed_fields = {
            'join_mode', 'port_function', 'receive_call_signal',
            'output_level', 'mode_2w', 'power_enabled',
            'termination_enabled', 'port_label',
        }
        if 'partyline_id' in data:
            port.partyline = CommConfigPartyline.objects.get(id=pl_id) if pl_id else None
        for field in allowed_fields:
            if field in data:
                setattr(port, field, data[field])
        port.save()
        return JsonResponse({'ok': True})
    except (CommConfigPortAssignment.DoesNotExist, CommConfigPartyline.DoesNotExist):
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Settings
# ─────────────────────────────────────────────────────────────

# Fields the settings endpoint is allowed to write
_SETTINGS_ALLOWED_FIELDS = {
    'name', 'wireless_region', 'wireless_id', 'admin_pin', 'ota_pin',
    'display_brightness', 'touch_sensitivity', 'battery_type',
    'dsp_plc_state', 'disable_http', 'role_sorting',
    'antenna_0_connector', 'antenna_1_connector',
}

@require_POST
def comm_config_update_setting(request):
    try:
        data = _json.loads(request.body)
        field = data.get('field')
        if field not in _SETTINGS_ALLOWED_FIELDS:
            return JsonResponse({'error': f'Field "{field}" not editable'}, status=400)
        config = CommConfig.objects.get(id=data['config_id'])
        # Type-coerce booleans and integers as needed
        value = data['value']
        int_fields = {'wireless_region', 'display_brightness', 'touch_sensitivity'}
        bool_fields = {'dsp_plc_state', 'disable_http'}
        if field in int_fields:
            value = int(value)
        elif field in bool_fields:
            value = bool(value)
        setattr(config, field, value)
        config.save(update_fields=[field])
        return JsonResponse({'ok': True})
    except CommConfig.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Delete Config
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_delete(request):
    try:
        data = _json.loads(request.body)
        config = CommConfig.objects.get(id=data['config_id'])
        current_project = getattr(request, 'current_project', None)
        if config.project != current_project:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        config.delete()
        return JsonResponse({'ok': True})
    except CommConfig.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)




# ─────────────────────────────────────────────────────────────
# COMM Config — Export .cca
# ─────────────────────────────────────────────────────────────
def comm_config_export(request, config_id):
    import json, os, tarfile, gzip, tempfile, shutil, io, uuid
    from django.http import HttpResponse
    from django.conf import settings
    from datetime import datetime, timezone

    config = get_object_or_404(CommConfig, id=config_id)

    FACTORY_SYS_ID = 'lKcw3zUU'
    SEP = b'\xc3\xbf'

    factory_path = os.path.join(settings.BASE_DIR, 'planner', 'static', 'comm_config', 'arcadia_factory_docs.json')
    with open(factory_path) as f:
        factory_docs = json.load(f)

    device_defaults = {}
    for fdoc_id, fdoc in factory_docs.items():
        if '3.23.' in fdoc_id and fdoc_id != '3.23.!':
            dtype = fdoc.get('type')
            if dtype and dtype not in device_defaults:
                device_defaults[dtype] = fdoc['data']['settings']

    tmp_dir = tempfile.mkdtemp()
    try:
        import plyvel

        factory_db_path = os.path.join(settings.BASE_DIR, 'planner', 'data', 'comm_config', 'pouchdb_factory')
        db_path = os.path.join(tmp_dir, 'pouchdb')

        if not os.path.exists(factory_db_path):
            return HttpResponse(f'Factory pouchdb not found at {factory_db_path}', status=500)
        shutil.copytree(factory_db_path, db_path)

        db = plyvel.DB(db_path, create_if_missing=False)

        existing_docs = {}
        max_seq = 0
        for key, value in db:
            if b'by-sequence' in key:
                try:
                    seq_num = int(key.split(SEP)[-1].decode())
                    max_seq = max(max_seq, seq_num)
                    v = value.decode('utf-8', errors='replace')
                    doc = json.loads(v)
                    if '_id' in doc:
                        existing_docs[doc['_id']] = doc
                except:
                    pass

        next_seq = [max_seq + 1]

        def make_rev():
            return f'1-{uuid.uuid4().hex}'

        def write_doc(doc):
            doc_id = doc['_id']
            rev = doc.get('_rev', '1-0000000000000000')
            rev_hash = rev.split('-')[1] if '-' in rev else rev
            seq = next_seq[0]
            next_seq[0] += 1
            seq_key = SEP + b'by-sequence' + SEP + f'{seq:016d}'.encode()
            db.put(seq_key, json.dumps(doc, separators=(',', ':')).encode('utf-8'))
            doc_store_key = SEP + b'document-store' + SEP + doc_id.encode()
            db.put(doc_store_key, json.dumps({
                'id': doc_id, 'rev': rev,
                'revisions': {'start': 1, 'ids': [rev_hash]},
                'rev_tree': [{'pos': 1, 'ids': [rev_hash, {'status': 'available'}, []]}],
                'rev_map': {rev: seq}, 'winningRev': rev, 'deleted': False, 'seq': seq,
            }, separators=(',', ':')).encode('utf-8'))

        owner_id = f'0.02.{FACTORY_SYS_ID}.0000.0000'

        # ── Update partylines ──
        partylines = list(config.partylines.all().order_by('channel_number'))
        for pl in partylines:
            doc_id = f'3.20.{FACTORY_SYS_ID}.0000.{pl.channel_number:04d}'
            if doc_id in existing_docs:
                doc = existing_docs[doc_id]
                doc['data']['label'] = pl.label
                doc['data']['helixnetEnabled'] = pl.helixnet_enabled
            else:
                doc = {
                    '_id': doc_id, '_rev': make_rev(),
                    'data': {'helixnetEnabled': pl.helixnet_enabled, 'id': pl.channel_number, 'label': pl.label, 'type': 'partyline'},
                    'owner': owner_id, 'type': 'partyline',
                }
            write_doc(doc)

        # ── Write 3.06 port docs ──
        # Detect hardware sys_id from existing factory 3.06 docs
        hw_sys_id = FACTORY_SYS_ID  # fallback
        for _doc_id in existing_docs:
            if _doc_id.startswith('3.06.') and _doc_id != '3.06.!':
                _parts = _doc_id.split('.')
                if len(_parts) == 5:
                    hw_sys_id = _parts[2]
                    break
        PORT_GID_MAP = {
            '2w_1': ('0000.0000', '2W',  0, '0000.0000', 0, 135208704),
            '2w_2': ('0000.0001', '2W',  1, '0000.0000', 1, 135208705),
            '2w_3': ('0001.0000', '2W',  0, '0001.0000', 0, 135208706),
            '2w_4': ('0001.0001', '2W',  1, '0001.0000', 1, 135208707),
            '4w_1': ('0002.0000', '4W',  0, '0002.0000', 0, 135208708),
            '4w_2': ('0002.0001', '4W',  1, '0002.0000', 1, 135208709),
            '4w_3': ('0002.0002', '4W',  2, '0002.0000', 2, 135208710),
            '4w_4': ('0002.0003', '4W',  3, '0002.0000', 3, 135208711),
            '4w_5': ('0002.0004', '4W',  4, '0002.0000', 4, 135208712),
            '4w_6': ('0002.0005', '4W',  5, '0002.0000', 5, 135208713),
            '4w_7': ('0002.0006', '4W',  6, '0002.0000', 6, 135208714),
            'sa':   ('0002.0007', 'SA',  7, '0002.0000', 7, 135208715),
            'pgm':  ('0002.0008', 'PGM', 7, '0002.0000', 8, 135208716),
        }

        import random as _random, string as _string
        def make_4char():
            return ''.join(_random.choices(_string.ascii_letters + _string.digits, k=4))

        port_assignments = list(config.port_assignments.select_related('partyline').all())
        written_port_gids = set()

        for pa in port_assignments:
            gid = pa.port_gid
            if gid not in PORT_GID_MAP or gid in written_port_gids:
                continue
            written_port_gids.add(gid)
            doc_suffix, ptype, hw_index, owner_suffix, slot_int, user_id = PORT_GID_MAP[gid]
            doc_id = f'3.06.{hw_sys_id}.{doc_suffix}'
            owner  = f'2.05.{hw_sys_id}.{owner_suffix}'
            label  = pa.port_label or f'{ptype} Port {slot_int + 1}'
            if ptype == '2W':
                data = {
                    'hwIndex': hw_index, 'label': label, 'type': '2W',
                    'settings': {
                        'termination': pa.termination_enabled,
                        'inputGain': 0, 'outputGain': 0,
                        'joinMode': pa.join_mode, 'callSignal': True,
                    },
                    'id': hw_index, 'desc': label, 'userId': user_id,
                }
            elif ptype == '4W':
                data = {
                    'hwIndex': hw_index, 'label': label, 'type': '4W',
                    'settings': {
                        'inputGain': 0, 'outputGain': 0,
                        'joinMode': pa.join_mode, 'callSignal': True,
                        'pinout': 'panel',
                        'serial': {
                            'state': 'disabled', 'baudRate': 19200,
                            'data': 8, 'parity': 0, 'stop': 1,
                            'flowControl': 'none', 'framingType': 'Eclipse/4000',
                        },
                    },
                    'id': hw_index, 'desc': label, 'userId': user_id,
                }
            elif ptype == 'SA':
                data = {
                    'portId': 7, 'hwIndex': 7, 'label': label, 'desc': label, 'type': 'SA',
                    'settings': {
                        'outputGain': 0, 'pinout': 'panel',
                        'splitLabel': {'otherPortId': 8, 'direction': 'output'},
                        'joinMode': 'Listen',
                    },
                    'id': 7, 'userId': user_id,
                }
            elif ptype == 'PGM':
                data = {
                    'portId': 8, 'hwIndex': 7, 'label': label, 'desc': label, 'type': 'PGM',
                    'settings': {
                        'inputGain': 0, 'pinout': 'panel',
                        'splitLabel': {'otherPortId': 7, 'direction': 'input'},
                        'joinMode': 'Talk',
                    },
                    'id': 8, 'userId': user_id,
                }
            else:
                continue
            write_doc({'_id': doc_id, '_rev': make_rev(), 'owner': owner, 'type': ptype, 'data': data})

        # ── Write 4.44 partyline.port assignment docs ──
        for pa in port_assignments:
            gid = pa.port_gid
            if gid not in PORT_GID_MAP or not pa.partyline:
                continue
            write_doc({
                '_id': f'4.44.{FACTORY_SYS_ID}.{make_4char()}.{make_4char()}',
                '_rev': make_rev(),
                'owner': f'3.06.{hw_sys_id}.{PORT_GID_MAP[gid][0]}',
                'type': 'partyline.port',
                'data': {
                    'destination': f'3.20.{FACTORY_SYS_ID}.0000.{pa.partyline.channel_number:04x}',
                    'joinMode': pa.join_mode,
                    'type': 'partyline.port',
                    'id': pa.partyline.channel_number,
                },
            })

        # ── Write roles, rolesets, sessions (one of each per role) ──
        # Factory has roleset 1 and roles 1-13. Ours start at slot 2 for rolesets, 0x000e for roles.
        ROLE_SLOT_START = 0x000e
        ROLESET_SLOT_START = 2
        SESSION_SLOT_START = 1  # B.FSII sessions use 3.99.SYSID.0002.XXXX

        # Only export FSII-BP and E-BP roles - other types caused firmware crash on testing
        SAFE_DEVICE_TYPES = {'FSII-BP', 'E-BP', 'HBP-2X', 'HMS-4X', 'HRM-4X', 'V12', 'V24', 'V32'}
        roles = list(config.roles.filter(device_type__in=SAFE_DEVICE_TYPES).order_by('role_number'))

        for i, role in enumerate(roles):
            role_slot = ROLE_SLOT_START + i
            roleset_slot = ROLESET_SLOT_START + i
            session_slot = SESSION_SLOT_START + i

            role_doc_id = f'3.23.{FACTORY_SYS_ID}.0000.{role_slot:04x}'
            roleset_doc_id = f'3.88.{FACTORY_SYS_ID}.0000.{roleset_slot:04x}'
            # Session doc ID prefix by device type
            SESSION_PREFIX_MAP = {
                'B.FSII': '0002',
                'B.HBP': '0008',
                'B.HKB': '000a',
                'S.NEP': '0003',
                'P.V12': '000b',
                'P.V24': '000c',
                'P.V32': '000d',
            }
            # Determine session type first (needed for prefix)
            SESSION_TYPE_MAP2 = {
                'FSII-BP': 'B.FSII', 'E-BP': 'B.FSII',
                'HBP-2X': 'B.HBP', 'HMS-4X': 'B.HBP', 'HRM-4X': 'B.HBP',
                'V12': 'P.V12', 'V24': 'P.V24', 'V32': 'P.V32',
            }
            _st = SESSION_TYPE_MAP2.get(role.device_type, 'B.FSII')
            _prefix = SESSION_PREFIX_MAP.get(_st, '0002')
            session_doc_id = f'3.99.{FACTORY_SYS_ID}.{_prefix}.{session_slot:04x}'
            dp_doc_id = f'4.55.{FACTORY_SYS_ID}.0000.{roleset_slot:04x}'

            # Build keysets
            is_vpanel = role.device_type in ('V12', 'V24', 'V32')
            keysets = []
            for key in role.keysets.all().order_by('key_index'):
                entities = []
                if key.partyline:
                    entities.append({'res': f'/api/1/connections/{key.partyline.channel_number}', 'type': 0})
                elif key.port_reference:
                    entities.append({'res': key.port_reference, 'type': 1})
                if is_vpanel:
                    if key.key_index == 0:
                        keyset_entry = {
                            'keysetIndex': key.key_index,
                            'entities': entities,
                            'isReplyKey': True,
                            'isCallKey': False,
                            'activationState': 'talk',
                            'talkBtnMode': 'disabled',
                            'colorIndex': None,
                        }
                    else:
                        keyset_entry = {
                            'keysetIndex': key.key_index,
                            'entities': entities,
                            'isCallKey': False,
                            'activationState': 'talk',
                            'talkBtnMode': 'latching',
                            'colorIndex': None,
                        }
                else:
                    keyset_entry = {
                        'activationState': key.activation_state,
                        'entities': entities,
                        'isCallKey': key.is_call_key,
                        'keysetIndex': key.key_index,
                        'talkBtnMode': key.talk_mode,
                    }
                    if key.is_reply_key:
                        keyset_entry['isReplyKey'] = True
                keysets.append(keyset_entry)
            settings_obj = dict(device_defaults.get(role.device_type, {}))
            settings_obj['keysets'] = keysets
            if not is_vpanel:
                settings_obj.update({
                    'displayBrightness': role.display_brightness,
                    'masterVolume': role.master_volume,
                    'micType': role.mic_type,
                    'sidetoneControl': role.sidetone_control,
                    'sidetoneGain': role.sidetone_gain,
                    'headphoneLimit': role.headphone_limit,
            })

            # Write role
            write_doc({
                '_id': role_doc_id, '_rev': make_rev(),
                'data': {
                    'description': role.description or '',
                    'id': role_slot,
                    'isDefault': False,
                    'label': role.label,
                    'settings': settings_obj,
                    'type': role.device_type,
                },
                'owner': owner_id,
                'type': role.device_type,
            })

            # Write roleset
            write_doc({
                '_id': roleset_doc_id, '_rev': make_rev(),
                'data': {
                    'id': roleset_slot, 'type': 'Roleset',
                    'name': role.label, 'dpId': roleset_slot,
                    'label': role.label, 'addressable': True,
                },
                'owner': owner_id, 'type': 'Roleset',
            })

            # Write 4.55 dynamic port
            write_doc({
                '_id': dp_doc_id, '_rev': make_rev(),
                'data': {'destination': roleset_doc_id, 'id': roleset_slot, 'type': 'roleset'},
                'owner': owner_id, 'type': 'roleset',
            })

            # Map device type to session type
            SESSION_TYPE_MAP = {
                'FSII-BP': 'B.FSII', 'E-BP': 'B.FSII',
                'HBP-2X': 'B.HBP', 'HMS-4X': 'B.HBP', 'HRM-4X': 'B.HBP',
                'V12': 'P.V12', 'V24': 'P.V24', 'V32': 'P.V32',
            }
            session_type = SESSION_TYPE_MAP.get(role.device_type, 'B.FSII')

            # Write session
            # V-panel sessions always use id=0, slot 0000, no auth field (confirmed from CCM export)
            is_vpanel = role.device_type in ('V12', 'V24', 'V32')
            vpanel_doc_id = f'3.99.{FACTORY_SYS_ID}.{_prefix}.0000'
            session_id_val = 0 if is_vpanel else session_slot
            actual_session_doc_id = vpanel_doc_id if is_vpanel else session_doc_id
            session_data = {
                'id': session_id_val, 'type': session_type,
                'label': role.label,
                'settings': {'defaultRole': role_slot},
                'addressable': False,
            }
            if not is_vpanel:
                session_data['auth'] = {'pin': {'provider': 'pin'}}
            write_doc({
                '_id': actual_session_doc_id, '_rev': make_rev(),
                'data': session_data,
                'owner': roleset_doc_id,
                'type': session_type,
            })

        # ── Update 1.03 device doc network settings ──
        ports_by_type = {p.traffic_type: p for p in config.network_ports.all()}
        dev_doc_id = f'1.03.{hw_sys_id}.0000.0000'
        if dev_doc_id in existing_docs:
            dev_doc = existing_docs[dev_doc_id]
            network = dev_doc.get('data', {}).get('settings', {}).get('network', [])
            for entry in network:
                iface = entry.get('interface')
                # Find which physical port carries this traffic type
                port = ports_by_type.get(iface)
                # rearConnector: port_number if assigned, else 255
                entry['rearConnector'] = port.port_number if port else 255
                if iface not in ('danteprim', 'dantesec'):
                    if port:
                        entry['mode'] = 'dhcp' if port.mode == 'dhcp' else 'static'
                        if port.mode == 'static':
                            entry['staticIP'] = port.static_ip
                            entry['netmask']  = port.netmask
                            entry['gateway']  = port.gateway
                            entry['dns1']     = port.dns1
                            entry['dns2']     = port.dns2
                        else:
                            entry['staticIP'] = ''
                            entry['netmask']  = ''
                            entry['gateway']  = ''
                            entry['dns1']     = ''
                            entry['dns2']     = ''
                    if iface in ('aes67', 'aes67Secondary') and port:
                        entry['ptpFollowerMode'] = port.ptp_follower_mode
            dev_doc['_rev'] = make_rev()
            write_doc(dev_doc)

        # ── Keep A.CCM and S.NEP sessions from factory ──
        for doc_id in [f'3.99.{FACTORY_SYS_ID}.0000.0000', f'3.99.{FACTORY_SYS_ID}.0003.0000']:
            if doc_id in existing_docs:
                write_doc(existing_docs[doc_id])

        db.put(SEP + b'meta-store' + SEP + b'_local_last_update_seq', str(next_seq[0] - 1).encode())
        # Delete fixedGroup before closing — prevents password reset on import
        # Arcadia uses this doc to set password; if absent it keeps existing password
        try:
            for _fg_key in [
                SEP + b'document-store' + SEP + b'admin/author.0.data.fixedGroup',
                SEP + b'by-sequence' + SEP + b'admin/author.0.data.fixedGroup',
            ]:
                try: db.delete(_fg_key)
                except: pass
            # Also delete via plyvel iterator to catch any key format
            for _k, _v in db:
                if b'fixedGroup' in _k:
                    db.delete(_k)
        except: pass
        db.close()
        # Patch ldb to replace factory hash with correct default password hash
        # Factory pouchdb has wrong hash; correct is SHA1 of Arcadia default password
        import glob as _glob
        for _ldb_path in _glob.glob(os.path.join(db_path, "*.ldb")):
            with open(_ldb_path, "rb") as _f:
                _ldb = _f.read()
            _factory_hash = b"8d90a8dcfd7605877229f8d6cba55ed55070167b"
            _correct_hash = b"037ee3346d037c4054be32e888f5330a8ba777f7"  # hash for 04312B48
            if _factory_hash in _ldb:
                _ldb = _ldb.replace(_factory_hash, _correct_hash)
                with open(_ldb_path, "wb") as _f:
                    _f.write(_ldb)
        # The ldb contains fixedGroup/passwordHash from factory pouchdb
        # Future work: find a way to strip credentials without breaking LevelDB format

        with open(os.path.join(tmp_dir, 'type.txt'), 'w') as f:
            f.write('NEP-ARCADIA')
        with open(os.path.join(tmp_dir, 'datetime.txt'), 'w') as f:
            f.write(datetime.now(timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y'))
        with open(os.path.join(tmp_dir, 'SystemEnvironment.json'), 'w') as f:
            f.write(json.dumps({'system': FACTORY_SYS_ID, 'domain': FACTORY_SYS_ID, 'context': 'device'}, separators=(',', ':')))

        tar_path = os.path.join(tmp_dir, 'config.tar')
        with tarfile.open(tar_path, 'w') as tar:
            for item in ['pouchdb', 'datetime.txt', 'type.txt', 'SystemEnvironment.json']:
                tar.add(os.path.join(tmp_dir, item), arcname=item)

        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9) as gz:
            with open(tar_path, 'rb') as f:
                gz.write(f.read())

        filename = f'{config.name.replace(" ", "_")}_{FACTORY_SYS_ID}.cca'
        response = HttpResponse(buf.getvalue(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except ImportError:
        return HttpResponse('plyvel not installed on this server.', status=501)
    except Exception as e:
        import traceback
        return HttpResponse(f'Export error: {str(e)}\n{traceback.format_exc()}', status=500)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)




def debug_device_ordering(request):
    """
    Temporary debug view to check device input/output ordering
    Access at: /audiopatch/debug-device-ordering/
    """
    html = ["<html><body><pre>"]
    html.append("<h1>Device Ordering Debug</h1>")
    
    # Get first 3 devices
    devices = Device.objects.all()[:3]
    
    for device in devices:
        html.append(f"\n{'='*60}")
        html.append(f"Device: {device.name}")
        html.append(f"{'='*60}\n")
        
        html.append("\nINPUTS (no ORDER BY):")
        for inp in device.inputs.all()[:10]:
            html.append(f"  ID: {inp.id:3d} | input_number: {inp.input_number} | signal: {inp.signal_name or 'None'}")
        
        html.append("\n\nINPUTS (with ORDER BY input_number):")
        for inp in device.inputs.all().order_by('input_number')[:10]:
            html.append(f"  ID: {inp.id:3d} | input_number: {inp.input_number} | signal: {inp.signal_name or 'None'}")
        
        html.append("\n\nOUTPUTS (no ORDER BY):")
        for out in device.outputs.all()[:10]:
            html.append(f"  ID: {out.id:3d} | output_number: {out.output_number} | signal: {out.signal_name or 'None'}")
        
        html.append("\n\nOUTPUTS (with ORDER BY output_number):")
        for out in device.outputs.all().order_by('output_number')[:10]:
            html.append(f"  ID: {out.id:3d} | output_number: {out.output_number} | signal: {out.signal_name or 'None'}")
        
        html.append("\n\n")
    
    html.append("</pre></body></html>")
    
    return HttpResponse('\n'.join(html))


#------Checklist---


# Add these views to your views.py file

from django.http import JsonResponse

from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
import json

from .models import AudioChecklist, AudioChecklistTask


@login_required
def audio_checklist_view(request):
    """Main audio checklist page"""
    # Get current project from session
    current_project_id = request.session.get('current_project_id')
    if not current_project_id:
        messages.warning(request, "Please select a project first.")
        return redirect('admin:index')
    
    try:
        project = Project.objects.get(id=current_project_id)
    except Project.DoesNotExist:
        messages.error(request, "Project not found.")
        return redirect('admin:index')
    
    # Check user has access to this project
    if not request.user.is_superuser:
        if not ProjectMember.objects.filter(project=project, user=request.user).exists():
            if project.owner != request.user:
                messages.error(request, "You don't have access to this project.")
                return redirect('admin:index')
    
    # Create default checklists if they don't exist
    if not AudioChecklist.objects.filter(project=project).exists():
        AudioChecklist.create_default_checklists(project)
    
    context = {
        'title': 'Audio Production Checklist',
        'project': project,
    }
    
    return render(request, 'admin/planner/audio_checklist.html', context)


@login_required
@require_GET
def audio_checklist_data(request):
    """API endpoint to get checklist data for current project"""
    current_project_id = request.session.get('current_project_id')
    if not current_project_id:
        return JsonResponse({'error': 'No project selected'}, status=400)
    
    try:
        project = Project.objects.get(id=current_project_id)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    
    # Create default checklists if they don't exist
    if not AudioChecklist.objects.filter(project=project).exists():
        AudioChecklist.create_default_checklists(project)
    
    # Build checklist data structure
    checklists = {}
    statuses = {}
    
    for checklist in AudioChecklist.objects.filter(project=project).prefetch_related('tasks'):
        checklist_name = checklist.name
        checklists[checklist_name] = {'setup': [], 'daily': []}
        statuses[checklist_name] = {'setup': [], 'daily': []}
        
        for task in checklist.tasks.all().order_by('task_type', 'sort_order'):
            task_data = {
                'id': task.id,
                'task': task.task,
                'stage': task.stage,
            }
            status_data = {
                'id': task.id,
                'day1': task.day1_status,
                'day2': task.day2_status,
                'day3': task.day3_status,
                'day4': task.day4_status,
            }
            
            checklists[checklist_name][task.task_type].append(task_data)
            statuses[checklist_name][task.task_type].append(status_data)
    
    return JsonResponse({
        'checklists': checklists,
        'statuses': statuses,
        'project_name': project.name,
    })


@login_required
@require_POST
@csrf_protect
def audio_checklist_update_task(request):
    """API endpoint to update a task's text or stage"""
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        field = data.get('field')  # 'task' or 'stage'
        value = data.get('value')
        
        task = AudioChecklistTask.objects.get(id=task_id)
        
        # Verify user has access to this project
        current_project_id = request.session.get('current_project_id')
        if task.checklist.project_id != current_project_id:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        if field == 'task':
            task.task = value
        elif field == 'stage':
            task.stage = value
        
        task.save()
        
        return JsonResponse({'success': True})
    except AudioChecklistTask.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
@csrf_protect
def audio_checklist_update_status(request):
    """API endpoint to update a task's status for a specific day"""
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        day = data.get('day')  # 'day1', 'day2', 'day3', 'day4'
        status = data.get('status')  # 'not-started', 'in-progress', 'complete', 'na'
        
        task = AudioChecklistTask.objects.get(id=task_id)
        
        # Verify user has access to this project
        current_project_id = request.session.get('current_project_id')
        if task.checklist.project_id != current_project_id:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Update the appropriate day status
        if day == 'day1':
            task.day1_status = status
        elif day == 'day2':
            task.day2_status = status
        elif day == 'day3':
            task.day3_status = status
        elif day == 'day4':
            task.day4_status = status
        
        # For setup tasks, sync all days to the same status
        if task.task_type == 'setup':
            task.day1_status = status
            task.day2_status = status
            task.day3_status = status
            task.day4_status = status
        
        task.save()
        
        return JsonResponse({'success': True})
    except AudioChecklistTask.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
@csrf_protect
def audio_checklist_add_task(request):
    """API endpoint to add a new task"""
    try:
        data = json.loads(request.body)
        checklist_name = data.get('checklist_name')
        task_type = data.get('task_type')  # 'setup' or 'daily'
        task_text = data.get('task')
        
        current_project_id = request.session.get('current_project_id')
        if not current_project_id:
            return JsonResponse({'error': 'No project selected'}, status=400)
        
        checklist = AudioChecklist.objects.get(
            project_id=current_project_id,
            name=checklist_name
        )
        
        # Get the next sort order
        max_order = checklist.tasks.filter(task_type=task_type).aggregate(
            Max('sort_order')
        )['sort_order__max'] or 0
                
        task = AudioChecklistTask.objects.create(
            checklist=checklist,
            task=task_text,
            task_type=task_type,
            sort_order=max_order + 1
        )
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
        })
    except AudioChecklist.DoesNotExist:
        return JsonResponse({'error': 'Checklist not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
@csrf_protect
def audio_checklist_delete_task(request):
    """API endpoint to delete a task"""
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        
        task = AudioChecklistTask.objects.get(id=task_id)
        
        # Verify user has access to this project
        current_project_id = request.session.get('current_project_id')
        if task.checklist.project_id != current_project_id:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        task.delete()
        
        return JsonResponse({'success': True})
    except AudioChecklistTask.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
@csrf_protect
def audio_checklist_reset(request):
    """API endpoint to reset checklists to defaults"""
    try:
        current_project_id = request.session.get('current_project_id')
        if not current_project_id:
            return JsonResponse({'error': 'No project selected'}, status=400)
        
        project = Project.objects.get(id=current_project_id)
        
        # Delete existing checklists
        AudioChecklist.objects.filter(project=project).delete()
        
        # Recreate defaults
        AudioChecklist.create_default_checklists(project)
        
        return JsonResponse({'success': True})
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)




# ─────────────────────────────────────────────────────────────
# Audio Checklist Templates
# ─────────────────────────────────────────────────────────────
@require_POST
def audio_checklist_save_template(request):
    """Save current checklist as a named template."""
    try:
        data = _json.loads(request.body)
        name = data.get('name', '').strip()
        current_project = getattr(request, 'current_project', None)
        if not name or not current_project:
            return JsonResponse({'error': 'Missing name or project'}, status=400)

        # Delete existing template with same name in this project
        AudioChecklistTemplate.objects.filter(project=current_project, name=name).delete()

        # Create new template
        template = AudioChecklistTemplate.objects.create(
            project=current_project,
            name=name,
            created_by=request.user,
        )

        # Copy all tasks from current checklists
        from .models import AudioChecklist
        section_map = {'FOH': 'FOH', 'A2': 'A2', 'Prep': 'Prep'}
        sort_order = 0
        for checklist in AudioChecklist.objects.filter(project=current_project):
            section = checklist.name.replace(' Check List', '').replace(' Checklist', '').strip()
            if section not in section_map:
                section = 'FOH'
            for task in checklist.tasks.all().order_by('task_type', 'sort_order'):
                AudioChecklistTemplateTask.objects.create(
                    template=template,
                    task=task.task,
                    section=section,
                    task_type=task.task_type,
                    stage=task.stage,
                    sort_order=sort_order,
                )
                sort_order += 1

        return JsonResponse({'ok': True, 'template_id': template.id, 'name': template.name})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def audio_checklist_list_templates(request):
    """List all templates for the current project."""
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'templates': []})
        templates = AudioChecklistTemplate.objects.filter(
            project=current_project
        ).order_by('name').values('id', 'name', 'created_at')
        return JsonResponse({'templates': list(templates)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def audio_checklist_load_template(request):
    """Replace current checklist tasks with a template."""
    try:
        data = _json.loads(request.body)
        template_id = data.get('template_id')
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No project'}, status=400)

        template = AudioChecklistTemplate.objects.get(id=template_id, project=current_project)

        from .models import AudioChecklist
        # Delete all existing tasks
        for checklist in AudioChecklist.objects.filter(project=current_project):
            checklist.tasks.all().delete()

        # Ensure checklists exist for each section
        section_checklist_map = {}
        section_names = {
            'FOH': 'FOH Check List',
            'A2': 'A2 Check List',
            'Prep': 'Prep Check List',
        }
        for section, checklist_name in section_names.items():
            cl, _ = AudioChecklist.objects.get_or_create(
                project=current_project,
                name=checklist_name,
            )
            section_checklist_map[section] = cl

        # Load template tasks
        from .models import AudioChecklistTask
        for task in template.tasks.all().order_by('sort_order'):
            section = task.section if task.section in section_checklist_map else 'FOH'
            AudioChecklistTask.objects.create(
                checklist=section_checklist_map[section],
                task=task.task,
                task_type=task.task_type,
                stage=task.stage,
                sort_order=task.sort_order,
            )

        return JsonResponse({'ok': True})
    except AudioChecklistTemplate.DoesNotExist:
        return JsonResponse({'error': 'Template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def audio_checklist_delete_template(request):
    """Delete a saved template."""
    try:
        data = _json.loads(request.body)
        current_project = getattr(request, 'current_project', None)
        template = AudioChecklistTemplate.objects.get(
            id=data['template_id'], project=current_project
        )
        template.delete()
        return JsonResponse({'ok': True})
    except AudioChecklistTemplate.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Dante Channel CRUD
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_add_dante(request):
    try:
        data = _json.loads(request.body)
        config = CommConfig.objects.get(id=data['config_id'])
        direction = data.get('direction', 'receive')
        existing = config.dante_channels.filter(direction=direction).count()
        ch = CommConfigDanteChannel.objects.create(
            config=config,
            channel_number=existing + 1,
            label=data['label'],
            direction=direction,
        )
        return JsonResponse({'ok': True, 'channel_id': ch.id})
    except CommConfig.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_update_dante(request):
    try:
        data = _json.loads(request.body)
        ch = CommConfigDanteChannel.objects.get(id=data['channel_id'])
        if 'label' in data:
            ch.label = data['label']
        if 'partyline_id' in data:
            pl_id = data['partyline_id']
            ch.partyline = CommConfigPartyline.objects.get(id=pl_id) if pl_id else None
        ch.save()
        return JsonResponse({'ok': True})
    except CommConfigDanteChannel.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_delete_dante(request):
    try:
        data = _json.loads(request.body)
        ch = CommConfigDanteChannel.objects.get(id=data['channel_id'])
        ch.delete()
        return JsonResponse({'ok': True})
    except CommConfigDanteChannel.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Session CRUD
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_add_session(request):
    try:
        data = _json.loads(request.body)
        config = CommConfig.objects.get(id=data['config_id'])
        session = CommConfigSession.objects.create(
            config=config,
            session_type=data['session_type'],
            label=data['label'],
        )
        return JsonResponse({'ok': True, 'session_id': session.id})
    except CommConfig.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_update_session(request):
    try:
        data = _json.loads(request.body)
        session = CommConfigSession.objects.get(id=data['session_id'])
        if 'label' in data:
            session.label = data['label']
        if 'roleset' in data:
            rs_id = data['roleset']
            session.roleset = CommConfigRoleset.objects.get(id=rs_id) if rs_id else None
        if 'default_role' in data:
            role_id = data['default_role']
            session.default_role = CommConfigRole.objects.get(id=role_id) if role_id else None
        if 'addressable' in data:
            session.addressable = data['addressable']
        session.save()
        return JsonResponse({'ok': True})
    except CommConfigSession.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_delete_session(request):
    try:
        data = _json.loads(request.body)
        session = CommConfigSession.objects.get(id=data['session_id'])
        session.delete()
        return JsonResponse({'ok': True})
    except CommConfigSession.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Roleset CRUD
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_add_roleset(request):
    try:
        data = _json.loads(request.body)
        config = CommConfig.objects.get(id=data['config_id'])
        next_num = (config.rolesets.aggregate(
            m=__import__('django.db.models', fromlist=['Max']).Max('roleset_number')
        )['m'] or 0) + 1
        rs = CommConfigRoleset.objects.create(
            config=config,
            roleset_number=next_num,
            label=f'Roleset {next_num}',
        )
        return JsonResponse({'ok': True, 'roleset_id': rs.id})
    except CommConfig.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_update_roleset(request):
    try:
        data = _json.loads(request.body)
        rs = CommConfigRoleset.objects.get(id=data['roleset_id'])
        if 'label' in data:
            rs.label = data['label']
        if 'addressable' in data:
            rs.addressable = data['addressable']
        rs.save()
        return JsonResponse({'ok': True})
    except CommConfigRoleset.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_delete_roleset(request):
    try:
        data = _json.loads(request.body)
        rs = CommConfigRoleset.objects.get(id=data['roleset_id'])
        rs.delete()
        return JsonResponse({'ok': True})
    except CommConfigRoleset.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# COMM Config — Crew Name CRUD
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_add_crew_name(request):
    try:
        data = _json.loads(request.body)
        name = data.get('name', '').strip()
        current_project = getattr(request, 'current_project', None)
        if not name or not current_project:
            return JsonResponse({'error': 'Missing name or project'}, status=400)
        cn, created = CommCrewName.objects.get_or_create(
            name=name, project=current_project
        )
        if not created:
            return JsonResponse({'error': 'Name already exists'}, status=400)
        return JsonResponse({'ok': True, 'id': cn.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def comm_config_delete_crew_name(request):
    try:
        data = _json.loads(request.body)
        cn = CommCrewName.objects.get(id=data['crew_name_id'])
        cn.delete()
        return JsonResponse({'ok': True})
    except CommCrewName.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
# Dashboard Stats JSON endpoint
# ─────────────────────────────────────────────────────────────
@require_GET
@require_GET
@require_GET
def dashboard_stats(request):
    """JSON stats for the system overview dashboard."""
    from .models import ShowDay, MicAssignment
    cp = getattr(request, 'current_project', None)
    p = {'project': cp} if cp else {}

    try:
        # Show days with mic counts
        show_days = []
        if cp:
            for day in ShowDay.objects.filter(project=cp).order_by('date')[:5]:
                mic_count = MicAssignment.objects.filter(session__day=day).count()
                show_days.append({
                    'date': str(day.date),
                    'name': day.name,
                    'mic_count': mic_count,
                })

        from .models import MultitrackSession
        data = {
            'project_name': cp.name if cp else 'No Project Selected',
            'console_total': Console.objects.filter(**p).count(),
            'device_total': Device.objects.filter(**p).count(),
            'proc_p1': SystemProcessor.objects.filter(**{**p, 'device_type': 'P1'}).count(),
            'proc_galaxy': SystemProcessor.objects.filter(**{**p, 'device_type': 'GALAXY'}).count(),
            'amp_total': Amp.objects.filter(**p).count(),
            'amp_locations': AmpLocation.objects.filter(**p).count(),
            'pa_cables': PACableSchedule.objects.filter(**p).count(),
            'pa_zones': PAZone.objects.filter(**p).count(),
            'sv_total': SoundvisionPrediction.objects.filter(**p).count(),
            'sv_arrays': 0,
            'multitrack_total': MultitrackSession.objects.filter(**p).count(),
            'comm_packs': CommBeltPack.objects.filter(**p).count(),
            'comm_checked': CommBeltPack.objects.filter(**{**p, 'checked_out': True}).count(),
            'mic_total': sum(d['mic_count'] for d in show_days),
            'mic_micd': MicAssignment.objects.filter(session__day__project=cp, is_micd=True).count() if cp else 0,
            'power_plans': PowerDistributionPlan.objects.filter(**p).count(),
            'power_amps': 0,
            'show_days': show_days,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def comm_config_update_lan(request):
    import json
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    data = json.loads(request.body)
    from planner.models import CommConfigNetworkPort
    lan = CommConfigNetworkPort.objects.get(id=data['lan_id'])
    allowed = {'mode', 'static_ip', 'netmask', 'gateway', 'dns1', 'dns2', 'traffic_type', 'ptp_follower_mode', 'dante_redundancy'}
    for field, value in data.items():
        if field in allowed:
            setattr(lan, field, value)
    lan.save()
    return JsonResponse({'ok': True})

# ─────────────────────────────────────────────────────────────
# COMM Config — Templates
# ─────────────────────────────────────────────────────────────
@require_POST
def comm_config_save_as_template(request):
    import json as _j
    try:
        data = _j.loads(request.body)
        config_id = data.get('config_id')
        template_name = data.get('template_name', '').strip()
        if not config_id or not template_name:
            return JsonResponse({'error': 'Missing config_id or template_name'}, status=400)
        src = CommConfig.objects.get(id=config_id)

        # Delete existing template with same name
        CommConfig.objects.filter(is_template=True, template_name=template_name).delete()

        # Create template record (no project)
        tmpl = CommConfig.objects.create(
            project=None,
            name=template_name,
            template_name=template_name,
            is_template=True,
            device_type=src.device_type,
            wireless_region=src.wireless_region,
            wireless_id=src.wireless_id,
            admin_pin=src.admin_pin,
            ota_pin=src.ota_pin,
            display_brightness=src.display_brightness,
            touch_sensitivity=src.touch_sensitivity,
            battery_type=src.battery_type,
            dsp_plc_state=src.dsp_plc_state,
            disable_http=src.disable_http,
            role_sorting=src.role_sorting,
            antenna_0_connector=src.antenna_0_connector,
            antenna_1_connector=src.antenna_1_connector,
        )

        # Copy partylines
        pl_map = {}
        for pl in src.partylines.all():
            new_pl = CommConfigPartyline.objects.create(
                config=tmpl, channel_number=pl.channel_number,
                label=pl.label, helixnet_enabled=pl.helixnet_enabled,
            )
            pl_map[pl.id] = new_pl

        # Copy roles + keysets
        for role in src.roles.all():
            new_role = CommConfigRole.objects.create(
                config=tmpl, label=role.label, device_type=role.device_type,
                role_number=role.role_number, description=role.description,
                display_brightness=role.display_brightness, master_volume=role.master_volume,
                mic_type=role.mic_type, sidetone_control=role.sidetone_control,
                sidetone_gain=role.sidetone_gain, headphone_limit=role.headphone_limit,
            )
            for key in role.keysets.all():
                CommConfigKeyset.objects.create(
                    role=new_role, key_index=key.key_index,
                    partyline=pl_map.get(key.partyline_id),
                    activation_state=key.activation_state,
                    talk_mode=key.talk_mode,
                    is_call_key=key.is_call_key,
                    is_reply_key=key.is_reply_key,
                    port_reference=key.port_reference,
                )

        # Copy port assignments
        for pa in src.port_assignments.all():
            CommConfigPortAssignment.objects.create(
                config=tmpl, port_type=pa.port_type, port_label=pa.port_label,
                port_gid=pa.port_gid,
                partyline=pl_map.get(pa.partyline_id),
                join_mode=pa.join_mode, port_function=pa.port_function,
                receive_call_signal=pa.receive_call_signal, output_level=pa.output_level,
                mode_2w=pa.mode_2w, power_enabled=pa.power_enabled,
                termination_enabled=pa.termination_enabled,
            )

        return JsonResponse({'ok': True, 'template_id': tmpl.id, 'template_name': template_name})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def comm_config_list_templates(request):
    templates = CommConfig.objects.filter(is_template=True).order_by('template_name').values('id', 'template_name', 'device_type')
    return JsonResponse({'templates': list(templates)})


@require_POST
def comm_config_load_template(request):
    import json as _j
    try:
        data = _j.loads(request.body)
        template_id = data.get('template_id')
        current_project = getattr(request, 'current_project', None)
        if not template_id or not current_project:
            return JsonResponse({'error': 'Missing template_id or project'}, status=400)
        tmpl = CommConfig.objects.get(id=template_id, is_template=True)

        name = data.get('name', tmpl.template_name).strip() or tmpl.template_name
        config = CommConfig.objects.create(
            project=current_project, name=name, device_type=tmpl.device_type,
            wireless_region=tmpl.wireless_region, wireless_id=tmpl.wireless_id,
            admin_pin=tmpl.admin_pin, ota_pin=tmpl.ota_pin,
            display_brightness=tmpl.display_brightness, touch_sensitivity=tmpl.touch_sensitivity,
            battery_type=tmpl.battery_type, dsp_plc_state=tmpl.dsp_plc_state,
            disable_http=tmpl.disable_http, role_sorting=tmpl.role_sorting,
            antenna_0_connector=tmpl.antenna_0_connector, antenna_1_connector=tmpl.antenna_1_connector,
        )

        pl_map = {}
        for pl in tmpl.partylines.all():
            new_pl = CommConfigPartyline.objects.create(
                config=config, channel_number=pl.channel_number,
                label=pl.label, helixnet_enabled=pl.helixnet_enabled,
            )
            pl_map[pl.id] = new_pl

        for role in tmpl.roles.all():
            new_role = CommConfigRole.objects.create(
                config=config, label=role.label, device_type=role.device_type,
                role_number=role.role_number, description=role.description,
                display_brightness=role.display_brightness, master_volume=role.master_volume,
                mic_type=role.mic_type, sidetone_control=role.sidetone_control,
                sidetone_gain=role.sidetone_gain, headphone_limit=role.headphone_limit,
            )
            for key in role.keysets.all():
                CommConfigKeyset.objects.create(
                    role=new_role, key_index=key.key_index,
                    partyline=pl_map.get(key.partyline_id),
                    activation_state=key.activation_state,
                    talk_mode=key.talk_mode,
                    is_call_key=key.is_call_key,
                    is_reply_key=key.is_reply_key,
                    port_reference=key.port_reference,
                )

        for pa in tmpl.port_assignments.all():
            CommConfigPortAssignment.objects.create(
                config=config, port_type=pa.port_type, port_label=pa.port_label,
                port_gid=pa.port_gid,
                partyline=pl_map.get(pa.partyline_id),
                join_mode=pa.join_mode, port_function=pa.port_function,
                receive_call_signal=pa.receive_call_signal, output_level=pa.output_level,
                mode_2w=pa.mode_2w, power_enabled=pa.power_enabled,
                termination_enabled=pa.termination_enabled,
            )

        return JsonResponse({'ok': True, 'config_id': config.id})
    except CommConfig.DoesNotExist:
        return JsonResponse({'error': 'Template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ─────────────────────────────────────────────────────────────
# FreeSpeak II .cca Export
# ─────────────────────────────────────────────────────────────
@login_required
def comm_config_export_freespeak(request, config_id):
    import json, os, tarfile, gzip, tempfile, shutil, io
    from django.http import HttpResponse
    from django.conf import settings
    from datetime import datetime, timezone

    config = get_object_or_404(CommConfig, id=config_id)
    factory_path = os.path.join(settings.BASE_DIR, 'planner', 'data', 'comm_config', 'fsii_factory')

    if not os.path.exists(factory_path):
        return HttpResponse('FreeSpeak factory files not found', status=500)

    tmp_dir = tempfile.mkdtemp()
    try:
        db_dir = os.path.join(tmp_dir, 'db')
        shutil.copytree(factory_path, db_dir)

        # Update channel labels from ShowStack partylines
        channels = {pl.channel_number: pl.label for pl in config.partylines.all()}
        ch_id_map = {pl.channel_number: pl.id for pl in config.partylines.all()}
        connections_path = os.path.join(db_dir, 'connections')
        new_lines = []
        with open(connections_path) as f:
            for line in f:
                obj = json.loads(line.strip())
                if obj['val']['type'] == 'partyline':
                    ch_id = obj['val']['id']
                    if ch_id in channels:
                        obj['val']['label'] = channels[ch_id]
                new_lines.append(json.dumps(obj, separators=(',', ':')))
        with open(connections_path, 'w') as f:
            f.write('\n'.join(new_lines))

        # Update port assignments in devices file
        port_assignments = {pa.port_gid: pa for pa in config.port_assignments.select_related('partyline').all()}
        FSII_GID_MAP = {
            '2w_1': ('2W', 2, 0), '2w_2': ('2W', 2, 1),
            '2w_3': ('2W', 3, 0), '2w_4': ('2W', 3, 1),
            '4w_1': ('4W', 0, 0), '4w_2': ('4W', 0, 1),
            '4w_3': ('4W', 1, 0), '4w_4': ('4W', 1, 1),
            'sa':   ('E1', 4, 1), 'pgm':  ('E1', 4, 0),
        }
        devices_path = os.path.join(db_dir, 'devices')
        new_device_lines = []
        with open(devices_path) as f:
            for line in f:
                obj = json.loads(line.strip())
                for iface in obj['val'].get('audioInterfaces', []):
                    for port in iface.get('ports', []):
                        # Find matching gid
                        for gid, (itype, hw, pidx) in FSII_GID_MAP.items():
                            if iface['type'] == itype and iface['hwIndex'] == hw and port['hwIndex'] == pidx:
                                pa = port_assignments.get(gid)
                                if pa and pa.partyline:
                                    port['connections'] = {
                                        f'/api/1/connections/{pa.partyline.channel_number}': {
                                            'joinMode': pa.join_mode
                                        }
                                    }
                                    port['label'] = pa.port_label
                                else:
                                    port['connections'] = {}
                new_device_lines.append(json.dumps(obj, separators=(',', ':')))
        with open(devices_path, 'w') as f:
            f.write('\n'.join(new_device_lines))

        # Update port assignments in devices file
        port_assignments = {pa.port_gid: pa for pa in config.port_assignments.select_related('partyline').all()}
        FSII_GID_MAP = {
            '2w_1': ('2W', 2, 0), '2w_2': ('2W', 2, 1),
            '2w_3': ('2W', 3, 0), '2w_4': ('2W', 3, 1),
            '4w_1': ('4W', 0, 0), '4w_2': ('4W', 0, 1),
            '4w_3': ('4W', 1, 0), '4w_4': ('4W', 1, 1),
            'sa':   ('E1', 4, 1), 'pgm':  ('E1', 4, 0),
        }
        # 2W interface-level mode setting
        MODE_MAP = {
            '2w_1': ('2W', 2), '2w_2': ('2W', 2),
            '2w_3': ('2W', 3), '2w_4': ('2W', 3),
        }
        devices_path = os.path.join(db_dir, 'devices')
        # FSII stores multiple history entries — parse all, only modify the last
        with open(devices_path) as f:
            all_lines = [l for l in f if l.strip()]
        all_objs = [json.loads(l) for l in all_lines]
        # Only update the last device entry
        obj = all_objs[-1]
        for iface in obj['val'].get('audioInterfaces', []):
            for gid, (itype, hw) in MODE_MAP.items():
                if iface['type'] == itype and iface['hwIndex'] == hw:
                    pa = port_assignments.get(gid)
                    if pa and 'settings' in iface:
                        iface['settings']['mode'] = 'RTS' if pa.mode_2w == 'rts' else 'ClearCom'
                        iface['settings']['power'] = pa.power_enabled
            for port in iface.get('ports', []):
                for gid, (itype, hw, pidx) in FSII_GID_MAP.items():
                    if iface['type'] == itype and iface['hwIndex'] == hw and port['hwIndex'] == pidx:
                        pa = port_assignments.get(gid)
                        if pa:
                            if pa.partyline:
                                port['connections'] = {str(pa.partyline.channel_number): {'connectionState': 0}}
                            else:
                                port['connections'] = {}
                            if pa.port_label:
                                port['label'] = pa.port_label
                            if itype == '2W':
                                port['settings']['callSignal'] = pa.receive_call_signal
                                port['settings']['termination'] = pa.termination_enabled
                            elif itype == '4W':
                                port['settings']['callSignal'] = pa.receive_call_signal
                                port['settings']['pinout'] = 'matrix' if pa.port_function == '4wire-x' else 'panel'
                        break  # stop checking other gids once matched
        all_objs[-1] = obj
        with open(devices_path, 'w') as f:
            f.write('\n'.join(json.dumps(o, separators=(',', ':')) for o in all_objs) + '\n')

        # Write roles from ShowStack data
        roles_path = os.path.join(db_dir, 'roles')
        # Read factory roles to keep non-FSII-BP/E-BP types
        factory_roles = []
        with open(roles_path) as f:
            for line in f:
                obj = json.loads(line.strip())
                if obj['val']['type'] not in ('FSII-BP', 'E-BP'):
                    factory_roles.append(obj)

        showstack_roles = []
        next_id = 1000
        for role in config.roles.all().order_by('role_number'):
            if role.device_type not in ('FSII-BP', 'E-BP'):
                continue
            keysets = []
            for key in role.keysets.all().order_by('key_index'):
                if key.is_call_key:
                    keyset = {
                        'keysetIndex': key.key_index,
                        'connections': [{'res': '/api/1/special/call'}],
                        'activationState': 'listen',
                        'isReplyKey': False,
                        'isCallKey': True,
                        'talkBtnMode': 'disabled',
                    }
                elif key.is_reply_key:
                    keyset = {
                        'keysetIndex': key.key_index,
                        'connections': [],
                        'isReplyKey': True,
                        'isCallKey': False,
                        'activationState': 'talk',
                        'talkBtnMode': 'disabled',
                    }
                elif key.partyline:
                    keyset = {
                        'keysetIndex': key.key_index,
                        'connections': [{'res': f'/api/1/connections/{key.partyline.channel_number}'}],
                        'activationState': key.activation_state,
                        'isReplyKey': False,
                        'isCallKey': False,
                        'talkBtnMode': key.talk_mode,
                    }
                else:
                    keyset = {
                        'keysetIndex': key.key_index,
                        'connections': [],
                        'activationState': key.activation_state,
                        'isReplyKey': False,
                        'isCallKey': False,
                        'talkBtnMode': key.talk_mode,
                    }
                keysets.append(keyset)

            role_obj = {
                'key': str(next_id),
                'val': {
                    'id': next_id,
                    'type': role.device_type,
                    'label': role.label,
                    'description': role.description or '',
                    'isDefault': False,
                    'settings': {
                        'keysets': keysets,
                        'groups': [],
                        'headphoneLimit': 0,
                        'sidetoneGain': -9.6,
                        'sidetoneControl': 'tracking',
                        'masterVolume': -9.6,
                        'lineInVolume': 0,
                        'portInputGain': 0,
                        'portOutputGain': 0,
                        'micEchoCancellation': False,
                        'masterVolumeOperation': False,
                        'batteryAlarmMode': 'vibrate+audio',
                        'lowBatteryThreshold': 25,
                        'callAlertMode': 'off',
                        'outOfRangeAlarm': 'off',
                        'displayBrightness': 'veryhigh',
                        'displayDimTimeout': 30,
                        'displayOffTimeout': 30,
                        'listenAgainAutoDelete': 240,
                        'listenAgainRecordTime': 15,
                        'replyTalkAutoClear': 10,
                        'menuLevel': 'normal',
                        'latchingTalkKeys': True,
                        'dimmedTallies': False,
                        'partyLineDisplayMode': False,
                        'menuKeyMode': 'switchvolctrl',
                        'eavesdropping': False,
                        'useLocalSettings': False,
                    }
                }
            }
            showstack_roles.append(role_obj)
            next_id += 1

        with open(roles_path, 'w') as f:
            for obj in factory_roles + showstack_roles:
                f.write(json.dumps(obj, separators=(',', ':')) + '\n')

        # Write datetime and type
        with open(os.path.join(tmp_dir, 'datetime.txt'), 'w') as f:
            f.write(datetime.now(timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y'))
        with open(os.path.join(tmp_dir, 'type.txt'), 'w') as f:
            f.write('FSII')

        tar_path = os.path.join(tmp_dir, 'config.tar')
        with tarfile.open(tar_path, 'w') as tar:
            tar.add(db_dir, arcname='db')
            tar.add(os.path.join(tmp_dir, 'datetime.txt'), arcname='datetime.txt')
            tar.add(os.path.join(tmp_dir, 'type.txt'), arcname='type.txt')

        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9) as gz:
            with open(tar_path, 'rb') as f:
                gz.write(f.read())

        filename = f'{config.name.replace(" ", "_")}.cca'
        response = HttpResponse(buf.getvalue(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    finally:
        shutil.rmtree(tmp_dir)


# ──────────────────────────────────────────────────────────────────
# Multitrack Session Builder (Phase 1 of v2.0)
# All views project-scoped via request.current_project (CurrentProjectMiddleware).
# All page renders use @staff_member_required; POST mutate endpoints use @require_POST.
# ──────────────────────────────────────────────────────────────────

@staff_member_required
def multitrack_dashboard(request):
    """List view of MultitrackSessions for the current project (MTS-03).

    Also lists OWNER-SCOPED MultitrackTemplates (TPL-03, D-05) — templates
    intentionally cross all of this user's projects.

    Renders the dashboard with the session-card grid + Templates section.
    Empty state shown when no sessions / no templates exist.
    """
    current_project = getattr(request, 'current_project', None)
    sessions = (
        MultitrackSession.objects.filter(project=current_project)
        .select_related('console')
        .order_by('-updated_at')
        if current_project else MultitrackSession.objects.none()
    )
    # D-05: templates are OWNER-scoped, NOT project-scoped. They follow the
    # engineer across all their projects.
    templates = (
        MultitrackTemplate.objects.filter(created_by=request.user)
        .order_by('name')
        if request.user.is_authenticated else MultitrackTemplate.objects.none()
    )
    can_import_console_csv = (
        request.user.is_authenticated
        and not request.user.groups.filter(name='Viewer').exists()
    )
    return render(request, 'planner/multitrack/dashboard.html', {
        'sessions': sessions,
        'templates': templates,
        'current_project': current_project,
        'can_import_console_csv': can_import_console_csv,
    })


def _build_picker_data(session, existing_tracks, current_project=None):
    """Build the four channel lists for the picker, with already-added rows hidden (D-09).

    Returns a dict {inputs: [...], aux: [...], matrix: [...], stereo: [...]}
    where each list is [{id, label, channel_number, dante_number}, ...].

    Defence-in-depth (WR-07): if `current_project` is supplied, asserts that
    `session.project_id == current_project.id` so a future caller that forgets
    the IDOR check can never silently leak channel data from another project's
    console. Callers SHOULD pass `current_project=request.current_project`.
    """
    if current_project is not None:
        assert session.project_id == current_project.id, (
            'IDOR guard: session.project_id (%r) != current_project.id (%r)'
            % (session.project_id, current_project.id)
        )
    used_ids = {
        'input': {t.source_id for t in existing_tracks if t.source_type == 'input' and t.source_id},
        'aux': {t.source_id for t in existing_tracks if t.source_type == 'aux' and t.source_id},
        'matrix': {t.source_id for t in existing_tracks if t.source_type == 'matrix' and t.source_id},
        'stereo': {t.source_id for t in existing_tracks if t.source_type == 'stereo' and t.source_id},
    }
    console = session.console

    # ConsoleInput stores input_ch and dante_number as CharFields, so DB-level
    # order_by gives lexicographic order ("1", "10", "100", ..., "2", "20").
    # Sort in Python with an int cast so the picker shows 1, 2, 3, ..., 144.
    def _int_or_inf(value):
        try:
            return int(value) if value not in (None, '') else float('inf')
        except (ValueError, TypeError):
            return float('inf')

    # Sort picker channels by the session's track_order_mode so the order
    # in the picker matches the order the editor will render tracks in
    # after they're added. 'console'/'custom' → by channel number;
    # 'dante' → by dante stream number. Channels without the relevant
    # field sort to the end.
    mode = session.track_order_mode
    # Issue #15: channels with default_record=False are excluded from the
    # picker entirely. The Default Record checkbox on each channel is the
    # opt-in switch for "include this channel in multitrack sessions".
    inputs_qs = list(
        ConsoleInput.objects.filter(console=console, default_record=True).exclude(id__in=used_ids['input'])
    )
    aux_qs = list(
        ConsoleAuxOutput.objects.filter(console=console, default_record=True).exclude(id__in=used_ids['aux'])
    )
    matrix_qs = list(
        ConsoleMatrixOutput.objects.filter(console=console, default_record=True).exclude(id__in=used_ids['matrix'])
    )
    stereo_qs = list(
        ConsoleStereoOutput.objects.filter(console=console, default_record=True).exclude(id__in=used_ids['stereo'])
    )

    if mode == 'dante':
        inputs_qs.sort(key=lambda c: (_int_or_inf(c.dante_number), c.id))
        aux_qs.sort(key=lambda c: (_int_or_inf(c.dante_number), c.id))
        matrix_qs.sort(key=lambda c: (_int_or_inf(c.dante_number), c.id))
        stereo_qs.sort(key=lambda c: (_int_or_inf(c.dante_number), c.id))
    else:  # 'console', 'custom', or anything else — sort by channel number
        inputs_qs.sort(key=lambda c: (_int_or_inf(c.input_ch), c.id))
        aux_qs.sort(key=lambda c: (_int_or_inf(c.aux_number), c.id))
        matrix_qs.sort(key=lambda c: (_int_or_inf(c.matrix_number), c.id))
        stereo_qs.sort(key=lambda c: (c.stereo_type or '', c.id))

    return {
        'inputs': [
            {
                'id': c.id,
                'label': c.source or c.input_ch or (f'Input {c.dante_number}' if c.dante_number else f'Input {c.id}'),
                'channel_number': c.input_ch or '',
                'dante_number': c.dante_number or '',
            }
            for c in inputs_qs
        ],
        'aux': [
            {
                'id': c.id,
                'label': c.name or f'Aux {c.aux_number}',
                'channel_number': c.aux_number or '',
                'dante_number': c.dante_number,
            }
            for c in aux_qs
        ],
        'matrix': [
            {
                'id': c.id,
                'label': c.name or f'Matrix {c.matrix_number}',
                'channel_number': c.matrix_number or '',
                'dante_number': c.dante_number,
            }
            for c in matrix_qs
        ],
        'stereo': [
            {
                'id': c.id,
                'label': c.name or c.get_stereo_type_display(),
                'channel_number': c.stereo_type or '',
                'dante_number': c.dante_number,
            }
            for c in stereo_qs
        ],
    }


def _editor_context(session, tracks=None, current_project=None, **extras):
    """Build the canonical context dict for the multitrack editor template.

    SHARED HELPER — every render of `planner/multitrack/editor.html` MUST go
    through this function. The template binds to a fixed contract; if any
    caller forgets a key, the template silently degrades. Centralising the
    contract here closes that gap.

    Args:
      session: MultitrackSession instance (required).
      tracks: optional iterable of MultitrackTrack rows. If None, defaults
              to `list(session.tracks.all().order_by('track_number'))` so the
              normal page render path stays a one-liner. Callers that need a
              filtered set (e.g. the no-enabled-tracks export fallback) pass
              their own queryset.
      current_project: optional Project. When supplied, threaded through to
                       _build_picker_data so the IDOR-defence assertion can
                       fire (WR-07). Callers SHOULD pass
                       `current_project=request.current_project`.
      **extras: any additional context keys the caller wants to merge in
                (e.g. `export_error='...'`, `auto_open_picker=False`).
                Extras take precedence over computed defaults.

    Returns:
      dict with keys: session, tracks, picker_data_json, auto_open_picker,
                      total_count, over_count, plus any extras.

    Computed defaults:
      - tracks: session.tracks ordered by track_number (when not supplied)
      - picker_data_json: json.dumps(_build_picker_data(session, tracks))
      - auto_open_picker: True iff tracks list is empty (D-12)
      - total_count: len(tracks)
      - over_count: max(0, total_count - session.recorder_capacity) when
                    recorder_capacity is set; else 0. Used by the editor
                    template's capacity bar to render the "— N over capacity"
                    suffix without inline {% widthratio %} arithmetic.
    """
    if tracks is None:
        tracks = list(session.tracks.all())
    else:
        tracks = list(tracks)

    # Sort visible tracks according to session.track_order_mode so the editor
    # display matches what the .RPP export will produce. Reuse the exporter's
    # ordering helpers so there is one source of truth.
    from .utils.reaper_export import _source_channel_number, _SOURCE_TYPE_PRIORITY
    mode = session.track_order_mode
    if mode == 'dante':
        def _dante_key(t):
            d = t.resolved_dante_number
            if t.source_type == 'manual':
                return (2, t.track_number)
            if d is None:
                return (1, t.track_number)
            return (0, d, t.track_number)
        tracks.sort(key=_dante_key)
    elif mode == 'console':
        def _console_key(t):
            return (
                _SOURCE_TYPE_PRIORITY.get(t.source_type, 99),
                _source_channel_number(t),
                t.track_number,
            )
        tracks.sort(key=_console_key)
    else:  # 'custom' — engineer's drag order
        tracks.sort(key=lambda t: t.track_number)

    total_count = len(tracks)
    capacity = session.recorder_capacity
    over_count = (total_count - capacity) if (capacity is not None and total_count > capacity) else 0

    ctx = {
        'session': session,
        'tracks': tracks,
        'picker_data_json': json.dumps(
            _build_picker_data(session, tracks, current_project=current_project)
        ),
        'auto_open_picker': total_count == 0,   # D-12
        'total_count': total_count,
        'over_count': over_count,
    }
    ctx.update(extras)
    return ctx


@staff_member_required
def multitrack_editor(request, session_id):
    """Editor view of a single MultitrackSession (TRK-01..10, RPP-01/05).

    Page render only — Sortable.js + AJAX endpoints in Plan 04 mutate state.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    session = (
        MultitrackSession.objects
        .filter(id=session_id, project=current_project)   # IDOR-safe combined filter
        .select_related('console')
        .first()
    )
    if not session:
        return redirect('planner:multitrack_dashboard')

    return render(
        request,
        'planner/multitrack/editor.html',
        _editor_context(session, current_project=current_project),
    )


@staff_member_required
def multitrack_create_view(request):
    """GET: render new-session form. POST: create + (optionally) apply a template
    + redirect to editor (MTS-01, MTS-04, TPL-02, D-08, D-10, D-12, D-13).

    Phase 3 extension: if the form's `template` field is set, call
    template.apply_to_session(new_session) AFTER form.save() returns, and
    surface the (mapped, skipped, summary) return via messages.info so the
    editor page shows a banner explaining what happened.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    if request.method == 'POST':
        form = MultitrackSessionForm(request.POST, request=request)
        if form.is_valid():
            session = form.save()
            # TPL-02 — apply selected template if any. Owner-scoped queryset
            # in MultitrackSessionForm.__init__ guarantees the chosen template
            # belongs to request.user (IDOR closed).
            template = form.cleaned_data.get('template')
            if template is not None:
                mapped, skipped, skipped_summary = template.apply_to_session(session)
                total = mapped + skipped
                if total == 0:
                    # D-13 — empty-track-list template. Metadata seeded;
                    # picker auto-opens on Inputs per Phase 1 D-12.
                    messages.info(
                        request,
                        f"Applied template '{template.name}' — "
                        f"metadata seeded; no tracks in template.",
                    )
                elif skipped == 0:
                    # All slots mapped cleanly — short banner.
                    messages.info(
                        request,
                        f"Applied template '{template.name}' — "
                        f"{mapped} of {total} slots mapped.",
                    )
                else:
                    # D-10 — at least one slot unmappable on this console.
                    messages.info(
                        request,
                        f"Applied template '{template.name}' — "
                        f"{mapped} of {total} slots mapped; "
                        f"{skipped} skipped ({skipped_summary}).",
                    )
            return redirect('planner:multitrack_editor', session_id=session.id)
    else:
        form = MultitrackSessionForm(request=request)

    return render(request, 'planner/multitrack/new_session.html', {
        'form': form,
        'mode': 'create',
    })


@staff_member_required
def multitrack_edit_view(request, session_id):
    """GET / POST edit-metadata form (MTS-04). Tracks are NOT touched.

    On success, redirect to the editor.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    session = MultitrackSession.objects.filter(
        id=session_id, project=current_project
    ).first()
    if not session:
        return redirect('planner:multitrack_dashboard')

    if request.method == 'POST':
        form = MultitrackSessionForm(request.POST, instance=session, request=request)
        if form.is_valid():
            form.save()
            return redirect('planner:multitrack_editor', session_id=session.id)
    else:
        form = MultitrackSessionForm(instance=session, request=request)

    return render(request, 'planner/multitrack/new_session.html', {
        'form': form,
        'session': session,
        'mode': 'edit',
    })


@login_required
@require_POST
def multitrack_duplicate(request, session_id):
    """POST: duplicate the session + all tracks under a new name (MTS-06).

    Body: JSON {new_name: '...'} (UI-SPEC duplicate-modal). New session
    name is required; defaults to '{original} (copy)' if blank.
    Returns JSON {ok, redirect_url} or {error, status: 4xx}.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        source = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not source:
            return JsonResponse({'error': 'Session not found'}, status=404)

        data = json.loads(request.body or '{}')
        new_name = (data.get('new_name') or '').strip() or f'{source.name} (copy)'

        # Uniqueness check (mirrors form clean_name)
        if MultitrackSession.objects.filter(
            project=current_project, name=new_name
        ).exists():
            return JsonResponse({
                'error': f'A session named "{new_name}" already exists in this project. '
                         f'Pick a different name.',
            }, status=409)

        # Copy session
        new_session = MultitrackSession.objects.create(
            project=current_project,
            console=source.console,
            name=new_name,
            target_daw=source.target_daw,
            feed_source=source.feed_source,
            track_order_mode=source.track_order_mode,
            recorder_capacity=source.recorder_capacity,
            notes=source.notes,
        )
        # Copy tracks (bulk_create — single INSERT)
        new_tracks = [
            MultitrackTrack(
                session=new_session,
                track_number=t.track_number,
                source_type=t.source_type,
                source_id=t.source_id,
                label_override=t.label_override,
                color_override=t.color_override,
                enabled=t.enabled,
                notes=t.notes,
            )
            for t in source.tracks.all().order_by('track_number')
        ]
        MultitrackTrack.objects.bulk_create(new_tracks)

        return JsonResponse({
            'ok': True,
            'session_id': new_session.id,
            'redirect_url': reverse('planner:multitrack_editor', args=[new_session.id]),
        })
    except Exception:
        _multitrack_logger.exception('multitrack_duplicate failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_rename(request, session_id):
    """POST: rename a session (MTS-02).

    Body: JSON {name: '...'}. Returns {ok, name} or {error, status: 409} on
    unique-together conflict.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        data = json.loads(request.body or '{}')
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(new_name) > 100:
            return JsonResponse({'error': 'Name must be 100 characters or fewer.'}, status=400)

        if MultitrackSession.objects.filter(
            project=current_project, name=new_name
        ).exclude(pk=session.pk).exists():
            return JsonResponse({
                'error': f'A session named "{new_name}" already exists in this project. '
                         f'Pick a different name.',
            }, status=409)

        session.name = new_name
        session.save(update_fields=['name', 'updated_at'])
        return JsonResponse({'ok': True, 'name': new_name})
    except Exception:
        _multitrack_logger.exception('multitrack_rename failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_delete(request, session_id):
    """POST: delete a session and (via CASCADE) all its tracks (MTS-05).

    Returns JSON {ok, redirect_url} so the JS can navigate after success.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        session.delete()   # CASCADE on MultitrackTrack.session FK handles tracks
        return JsonResponse({
            'ok': True,
            'redirect_url': reverse('planner:multitrack_dashboard'),
        })
    except Exception:
        _multitrack_logger.exception('multitrack_delete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


# ──────────────────────────────────────────────────────────────────
# Multitrack — AJAX mutate endpoints (Plan 01-04, Wave 3)
# Track-level endpoints route through `_get_track_for_request` for IDOR-safe
# project-scoped lookup (T-04-01). Session-level endpoints inline the
# combined filter (T-04-02). Hex-color writes go through `_HEX_COLOR_RE`
# (T-04-04). All POST endpoints rely on Django CSRF middleware — no
# `@csrf_exempt` decorators.
# ──────────────────────────────────────────────────────────────────

import re
import logging

# Module-level logger for multitrack AJAX endpoints. Anything that bubbles
# out of the per-endpoint try blocks is logged here (with stack trace) so
# the client only ever sees a generic 500 message (WR-02).
_multitrack_logger = logging.getLogger(__name__)

# Hex color validator — REJECTS everything except '' or '#RRGGBB'.
# Closes the XSS-via-color-override surface (T-04-04 in this plan's threat model).
_HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _multitrack_viewer_block(request):
    """Return a JsonResponse 403 iff the user is in the 'Viewer' group; else None.

    Mirrors the read-only role contract enforced by BaseEquipmentAdmin and the
    `request.user.groups.filter(name='Viewer').exists()` pattern used throughout
    `planner/admin.py`. Centralised so every mutate endpoint applies the same
    check (CR-01 / CR-02).
    """
    if request.user.groups.filter(name='Viewer').exists():
        return JsonResponse({'error': 'Read-only access.'}, status=403)
    return None


def _get_track_for_request(request, track_id):
    """Return the MultitrackTrack iff its session.project == request.current_project.

    IDOR-safe lookup. Returns None when the track doesn't exist or belongs to
    a different project.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return None
    return (
        MultitrackTrack.objects
        .filter(id=track_id, session__project=current_project)
        .select_related('session')
        .first()
    )


@login_required
@require_POST
def multitrack_reorder(request, session_id):
    """POST: reassign dense track_number 1..N from a posted ordered list (TRK-05).

    Body: JSON {ordered_ids: [int, int, ...]}
    Returns: {ok: True} or {error, status: 4xx}
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        data = json.loads(request.body or '{}')
        ordered_ids = data.get('ordered_ids') or []
        if not isinstance(ordered_ids, list) or not all(isinstance(i, int) for i in ordered_ids):
            return JsonResponse({'error': 'ordered_ids must be a list of integers'}, status=400)

        # Verify the posted set EQUALS the full set of session track IDs (WR-04).
        # A subset would let a client renumber only some tracks, collapsing
        # multiple rows to the same track_number and breaking the
        # `ordering = ['track_number']` invariant.
        existing_ids = set(session.tracks.values_list('id', flat=True))
        if len(ordered_ids) != len(set(ordered_ids)):
            return JsonResponse({'error': 'Duplicate track IDs in ordered_ids.'}, status=400)
        if set(ordered_ids) != existing_ids:
            return JsonResponse({
                'error': 'ordered_ids must include every track in the session exactly once.'
            }, status=400)

        # Reassign track_number 1..N. Two-phase inside a transaction
        # because MultitrackTrack has unique_together = [('session',
        # 'track_number')]: a single-pass bulk_update would hit an
        # intermediate state where two tracks share the same number
        # (every reorder swap triggers this) and the IntegrityError
        # would roll the whole statement back.
        #
        # Phase 1 shifts every track to a unique value above the final
        # 1..N range, so phase 2 can assign 1..N without colliding.
        # track_number is a PositiveIntegerField (CHECK >= 0), so we
        # can't negate — we offset by 1_000_000 instead. Real sessions
        # have well under that many tracks, leaving the temporary
        # range collision-free.
        TRACK_NUMBER_TEMP_OFFSET = 1_000_000
        tracks_by_id = {t.id: t for t in session.tracks.all()}
        with transaction.atomic():
            phase1 = []
            for t in tracks_by_id.values():
                t.track_number = t.track_number + TRACK_NUMBER_TEMP_OFFSET
                phase1.append(t)
            MultitrackTrack.objects.bulk_update(phase1, ['track_number'])

            phase2 = []
            for idx, tid in enumerate(ordered_ids, start=1):
                t = tracks_by_id.get(tid)
                if t is not None:
                    t.track_number = idx
                    phase2.append(t)
            MultitrackTrack.objects.bulk_update(phase2, ['track_number'])

            # Flip to 'custom' so the editor render and Reaper/Nuendo exports
            # honor the engineer's drag order. Without this, _editor_context
            # and _ordered_enabled_tracks re-sort by source channel / Dante
            # number and the reorder is invisible everywhere except the row
            # numbers we just rewrote.
            if session.track_order_mode != 'custom':
                session.track_order_mode = 'custom'
                session.save(update_fields=['track_order_mode'])

        return JsonResponse({'ok': True, 'track_order_mode': session.track_order_mode})
    except Exception:
        _multitrack_logger.exception('multitrack_reorder failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


# ──────────────────────────────────────────────────────────────
# Phase 3 — Multitrack Templates (TPL-01..TPL-04)
# All endpoints are OWNER-scoped (created_by=request.user) per D-05,
# NOT project-scoped. Templates intentionally cross all of a user's projects.
# ──────────────────────────────────────────────────────────────


def _resolve_track_source_number(track):
    """Return the engineer-meaningful channel-number string for a MultitrackTrack
    so it can be stored as MultitrackTemplateSlot.source_number (D-02).

    Looks up the linked channel row via _source_model_for(source_type) and reads
    the corresponding CharField:
      input  -> ConsoleInput.input_ch
      aux    -> ConsoleAuxOutput.aux_number
      matrix -> ConsoleMatrixOutput.matrix_number
      stereo -> ConsoleStereoOutput.stereo_type
      manual -> '' (no channel; downstream apply materialises manual tracks unconditionally)

    Returns '' if the source row was deleted (D-04 post_delete converted track
    to manual) or unresolvable.
    """
    from planner.models import _source_model_for
    if track.source_type == 'manual' or track.source_id is None:
        return ''
    number_field = {
        'input': 'input_ch',
        'aux': 'aux_number',
        'matrix': 'matrix_number',
        'stereo': 'stereo_type',
    }
    field = number_field.get(track.source_type)
    model = _source_model_for(track.source_type)
    if not field or model is None:
        return ''
    row = model.objects.filter(id=track.source_id).only(field).first()
    if row is None:
        return ''
    return getattr(row, field, '') or ''


@login_required
@require_POST
def multitrack_template_save(request):
    """Save current session structure as an owner-scoped template (TPL-01).

    Body: JSON {name: str, session_id: int}
    Returns: JsonResponse {ok: True, template_id, name, slot_count}
             or {error: str} with status 400/403/404/409/500.

    D-05: OWNER-scoped via request.user, NOT project-scoped. The source SESSION
    is still IDOR-guarded against request.current_project (sessions are
    project-scoped per Phase 1).

    Pitfall 1 mitigation: name conflict returns HTTP 409 with a friendly error
    message (NOT silent overwrite). The unique_together = [('created_by', 'name')]
    constraint on MultitrackTemplate enforces this at the DB level too.

    Open Question 1 resolution: only ENABLED tracks become slots — disabled
    tracks were the engineer saying "not this time", so they don't belong in
    a reusable template (RESEARCH Pitfall 7 / Assumption A8).
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    name = ''
    try:
        data = json.loads(request.body or '{}')
        name = (data.get('name') or '').strip()
        session_id = data.get('session_id')
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)
        if session_id is None:
            return JsonResponse({'error': 'session_id is required.'}, status=400)

        # IDOR guard: the source session must belong to the user's current project.
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)
        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project,
        ).select_related('console').first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        # D-05: owner-scoped name-conflict check. Templates intentionally cross
        # all of this user's projects.
        if MultitrackTemplate.objects.filter(
            created_by=request.user, name=name,
        ).exists():
            return JsonResponse({
                'error': f'A template named "{name}" already exists. Pick a different name.',
            }, status=409)

        template = MultitrackTemplate.objects.create(
            created_by=request.user,
            name=name,
            target_daw=session.target_daw,
            feed_source=session.feed_source,
            track_order_mode=session.track_order_mode,
            recorder_capacity=session.recorder_capacity,
            notes=session.notes,
        )

        # Snapshot ENABLED tracks only (Open Question 1 resolution).
        slots = []
        enabled_tracks = session.tracks.filter(enabled=True).order_by('track_number')
        for position, track in enumerate(enabled_tracks, start=1):
            slots.append(MultitrackTemplateSlot(
                template=template,
                position=position,
                source_type=track.source_type,
                source_number=_resolve_track_source_number(track),
                label_override=track.label_override,
                color_override=track.color_override,
            ))
        if slots:
            MultitrackTemplateSlot.objects.bulk_create(slots)

        return JsonResponse({
            'ok': True,
            'template_id': template.id,
            'name': template.name,
            'slot_count': len(slots),
        })
    except IntegrityError:
        # Defensive — race condition between .exists() check and .create()
        return JsonResponse({
            'error': f'A template named "{name}" already exists. Pick a different name.',
        }, status=409)
    except Exception:
        _multitrack_logger.exception('multitrack_template_save failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_template_rename(request, template_id):
    """POST: rename an owner-scoped template (TPL-03).

    Body: JSON {new_name: '...'}. Returns {ok, name} or {error, status: 409}
    on unique_together(created_by, name) conflict.

    D-05: owner-scoped via request.user. Templates intentionally cross all
    of this user's projects.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    new_name = ''
    try:
        # D-05: owner-scoped via request.user. IDOR guard — non-owner gets 404.
        template = MultitrackTemplate.objects.filter(
            id=template_id, created_by=request.user,
        ).first()
        if not template:
            return JsonResponse({'error': 'Template not found'}, status=404)

        data = json.loads(request.body or '{}')
        new_name = (data.get('new_name') or '').strip()
        if not new_name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(new_name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)

        # D-05: owner-scoped uniqueness check.
        if MultitrackTemplate.objects.filter(
            created_by=request.user, name=new_name,
        ).exclude(pk=template.pk).exists():
            return JsonResponse({
                'error': f'A template named "{new_name}" already exists. '
                         f'Pick a different name.',
            }, status=409)

        template.name = new_name
        template.save(update_fields=['name', 'updated_at'])
        return JsonResponse({'ok': True, 'name': new_name})
    except IntegrityError:
        # Defensive — race between .exists() check and .save()
        return JsonResponse({
            'error': f'A template named "{new_name}" already exists. Pick a different name.',
        }, status=409)
    except Exception:
        _multitrack_logger.exception('multitrack_template_rename failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_template_delete(request, template_id):
    """POST: delete an owner-scoped template and (via CASCADE) all its slots (TPL-03).

    Returns JSON {ok: True}. JS reloads the dashboard — no redirect_url needed
    because the dashboard is already the right destination.

    D-05: owner-scoped via request.user. CASCADE on MultitrackTemplateSlot.template
    FK handles the child rows. Sessions previously created from this template
    are NOT affected (they were materialised at apply time — no FK back to the
    template).
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        # D-05: owner-scoped via request.user. IDOR guard — non-owner gets 404.
        template = MultitrackTemplate.objects.filter(
            id=template_id, created_by=request.user,
        ).first()
        if not template:
            return JsonResponse({'error': 'Template not found'}, status=404)

        template.delete()   # CASCADE handles MultitrackTemplateSlot rows
        return JsonResponse({'ok': True})
    except Exception:
        _multitrack_logger.exception('multitrack_template_delete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_add_tracks(request, session_id):
    """POST: create new MultitrackTrack rows for selected channels + manual queue (TRK-06, TRK-07, D-10).

    Body: JSON {
      selections: {
        inputs: [int, ...],   # ConsoleInput IDs
        aux: [int, ...],
        matrix: [int, ...],
        stereo: [int, ...],
      },
      manuals: [
        {label: str (required, max 100), color: str (optional, '' or '#RRGGBB'), notes: str (optional)},
        ...
      ]
    }

    Append rule (D-10): inserts in order Inputs -> Aux -> Matrix -> Stereo -> Manual,
    each in the order received in the request. New track_numbers continue from
    MAX(existing) + 1.

    Returns: {ok: True, created_count: N, redirect_url: '...'} or
             {error, status: 4xx}
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        data = json.loads(request.body or '{}')
        selections = data.get('selections') or {}
        manuals = data.get('manuals') or []

        # Validate manuals first — UI-SPEC error strings verbatim
        validated_manuals = []
        for m in manuals:
            label = (m.get('label') or '').strip()
            color = (m.get('color') or '').strip()
            notes = (m.get('notes') or '').strip()
            if not label:
                return JsonResponse({'error': 'Label is required for manual tracks.'}, status=400)
            if len(label) > 100:
                return JsonResponse({'error': 'Label must be 100 characters or fewer.'}, status=400)
            if color and not _HEX_COLOR_RE.match(color):
                return JsonResponse({'error': f'Color must be empty or #RRGGBB hex, got: {color!r}'}, status=400)
            if len(notes) > 200:
                return JsonResponse({'error': 'Notes must be 200 characters or fewer.'}, status=400)
            validated_manuals.append({'label': label, 'color': color, 'notes': notes})

        # Validate selections — IDs must belong to this session's console
        console = session.console
        valid_input_ids = set(
            ConsoleInput.objects.filter(console=console)
            .values_list('id', flat=True)
        ) & set(selections.get('inputs', []) or [])
        valid_aux_ids = set(
            ConsoleAuxOutput.objects.filter(console=console)
            .values_list('id', flat=True)
        ) & set(selections.get('aux', []) or [])
        valid_matrix_ids = set(
            ConsoleMatrixOutput.objects.filter(console=console)
            .values_list('id', flat=True)
        ) & set(selections.get('matrix', []) or [])
        valid_stereo_ids = set(
            ConsoleStereoOutput.objects.filter(console=console)
            .values_list('id', flat=True)
        ) & set(selections.get('stereo', []) or [])

        # POL-01 — bulk-load channel default_record so each new track can be
        # seeded with enabled = channel.default_record. One query per
        # source_type (4 total), restricted to the IDs we'll actually use.
        seed_maps = {
            'input':  dict(ConsoleInput.objects.filter(id__in=valid_input_ids).values_list('id', 'default_record')),
            'aux':    dict(ConsoleAuxOutput.objects.filter(id__in=valid_aux_ids).values_list('id', 'default_record')),
            'matrix': dict(ConsoleMatrixOutput.objects.filter(id__in=valid_matrix_ids).values_list('id', 'default_record')),
            'stereo': dict(ConsoleStereoOutput.objects.filter(id__in=valid_stereo_ids).values_list('id', 'default_record')),
        }

        # Determine starting track_number (D-10 append rule)
        # Note: `Max` is already imported top-of-file (line 9: from django.db.models import Max).
        max_n = (
            session.tracks.aggregate(m=Max('track_number'))['m'] or 0
        )

        # Build new rows in D-10 order: inputs -> aux -> matrix -> stereo -> manual
        new_rows = []

        # Preserve the order the IDs were submitted (sets lose order; re-derive)
        for src_type, valid_ids, raw_list in [
            ('input', valid_input_ids, selections.get('inputs', []) or []),
            ('aux', valid_aux_ids, selections.get('aux', []) or []),
            ('matrix', valid_matrix_ids, selections.get('matrix', []) or []),
            ('stereo', valid_stereo_ids, selections.get('stereo', []) or []),
        ]:
            for raw_id in raw_list:
                if raw_id in valid_ids:
                    max_n += 1
                    seed_record = seed_maps[src_type].get(raw_id, True)
                    new_rows.append(MultitrackTrack(
                        session=session,
                        track_number=max_n,
                        source_type=src_type,
                        source_id=raw_id,
                        enabled=bool(seed_record),
                    ))

        for m in validated_manuals:
            max_n += 1
            new_rows.append(MultitrackTrack(
                session=session,
                track_number=max_n,
                source_type='manual',
                source_id=None,
                label_override=m['label'],
                color_override=m['color'],
                notes=m['notes'],
            ))

        MultitrackTrack.objects.bulk_create(new_rows)
        # Touch session.updated_at
        session.save(update_fields=['updated_at'])

        return JsonResponse({
            'ok': True,
            'created_count': len(new_rows),
            'redirect_url': reverse('planner:multitrack_editor', args=[session.id]),
        })
    except Exception:
        _multitrack_logger.exception('multitrack_add_tracks failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_set_color(request):
    """POST: update a single track's color_override (TRK-04).

    Body: JSON {track_id: int, color: str ('' or '#RRGGBB')}
    Returns: {ok: True, color: str} or {error, status: 4xx}
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        data = json.loads(request.body or '{}')
        track_id = data.get('track_id')
        color = (data.get('color') or '').strip()

        if color and not _HEX_COLOR_RE.match(color):
            return JsonResponse({'error': f'Color must be empty or #RRGGBB hex, got: {color!r}'}, status=400)

        track = _get_track_for_request(request, track_id)
        if not track:
            return JsonResponse({'error': 'Track not found'}, status=404)

        track.color_override = color
        track.save(update_fields=['color_override'])
        return JsonResponse({'ok': True, 'color': color})
    except Exception:
        _multitrack_logger.exception('multitrack_set_color failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_set_label(request):
    """POST: update a single track's label_override (TRK-03).

    Body: JSON {track_id: int, label: str (max 100)}
    Returns: {ok: True, resolved_label: str} or {error, status: 4xx}
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        data = json.loads(request.body or '{}')
        track_id = data.get('track_id')
        label = (data.get('label') or '').strip()

        if len(label) > 100:
            return JsonResponse({'error': 'Label must be 100 characters or fewer.'}, status=400)

        track = _get_track_for_request(request, track_id)
        if not track:
            return JsonResponse({'error': 'Track not found'}, status=404)

        # Manual tracks must always have a label (D-11)
        if track.source_type == 'manual' and not label:
            return JsonResponse({'error': 'Label is required for manual tracks.'}, status=400)

        track.label_override = label
        track.save(update_fields=['label_override'])
        return JsonResponse({'ok': True, 'resolved_label': track.resolved_label})
    except Exception:
        _multitrack_logger.exception('multitrack_set_label failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_set_enabled(request):
    """POST: toggle a track's enabled flag (TRK-02).

    Body: JSON {track_id: int, enabled: bool}
    Returns: {ok: True, enabled: bool} or {error, status: 4xx}
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        data = json.loads(request.body or '{}')
        track_id = data.get('track_id')
        enabled = bool(data.get('enabled'))

        track = _get_track_for_request(request, track_id)
        if not track:
            return JsonResponse({'error': 'Track not found'}, status=404)

        track.enabled = enabled
        track.save(update_fields=['enabled'])
        return JsonResponse({'ok': True, 'enabled': enabled})
    except Exception:
        _multitrack_logger.exception('multitrack_set_enabled failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_remove_track(request):
    """POST: delete a single MultitrackTrack (TRK-08).

    Body: JSON {track_id: int}
    Returns: {ok: True} or {error, status: 4xx}

    Does NOT cascade to ConsoleChannel — MultitrackTrack has no FK there (D-01).
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        data = json.loads(request.body or '{}')
        track_id = data.get('track_id')

        track = _get_track_for_request(request, track_id)
        if not track:
            return JsonResponse({'error': 'Track not found'}, status=404)

        track.delete()
        return JsonResponse({'ok': True})
    except Exception:
        _multitrack_logger.exception('multitrack_remove_track failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@staff_member_required
def multitrack_capacity_check(request, session_id):
    """GET: return live capacity-bar state for the editor (TRK-10).

    Returns: {count: int, capacity: int|null, over: bool}
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    session = MultitrackSession.objects.filter(
        id=session_id, project=current_project
    ).first()
    if not session:
        return JsonResponse({'error': 'Session not found'}, status=404)

    count = session.tracks.count()
    capacity = session.recorder_capacity
    over = (capacity is not None) and (count > capacity)
    return JsonResponse({
        'count': count,
        'capacity': capacity,
        'over': over,
    })


# ──────────────────────────────────────────────────────────────────
# Multitrack — Reaper file-download views (Plan 01-04, Wave 3)
# Delegates RPP / RTrackTemplate body building to planner.utils.reaper_export
# (Plan 01-02). This view layer only handles HTTP response shape, filename
# sanitization (T-04-06 / T-04-12), and the no-enabled-tracks guard
# (T-04-13).
# ──────────────────────────────────────────────────────────────────

from .utils.reaper_export import build_rpp, build_rtracktemplate
from .utils.nuendo_live_export import build_nlpr, ExportTemplateError


def _safe_filename(name):
    """Slugify a session name for a Content-Disposition filename header.

    Restricts output to ASCII letters, digits, hyphen, and underscore — every
    other character is replaced with `_`. RFC 6266 requires bare `filename=`
    values to be ASCII; non-ASCII letters (which `str.isalnum()` accepts via
    Unicode) confuse some browsers into rejecting the download or producing
    mojibake (WR-06). Closes path-traversal / header-injection too.
    """
    return ''.join(
        c if ((c.isascii() and c.isalnum()) or c in '-_') else '_'
        for c in (name or '').strip()
    ) or 'session'


def _has_enabled_tracks(session):
    return session.tracks.filter(enabled=True).exists()


@staff_member_required
def multitrack_export_rpp(request, session_id):
    """GET: download a Reaper .RPP file for this session (RPP-01..04).

    Returns text/plain attachment. Filename: <safe(session.name)>.RPP.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    session = MultitrackSession.objects.filter(
        id=session_id, project=current_project
    ).select_related('console').first()
    if not session:
        return redirect('planner:multitrack_dashboard')

    if not _has_enabled_tracks(session):
        # UI-SPEC error string verbatim. Render an HTML page (not a download).
        # Route through the shared _editor_context helper (defined in Plan 03)
        # so the editor template receives the full context contract
        # (session, tracks, picker_data_json, auto_open_picker, total_count,
        # over_count, plus our export_error extra). Filtering tracks to the
        # enabled set keeps the displayed editor consistent with the export
        # logic — even though enabled is empty here, this preserves the
        # invariant that the export-fallback view shows what was attempted.
        enabled_tracks_qs = session.tracks.filter(enabled=True).order_by('track_number')
        return render(
            request,
            'planner/multitrack/editor.html',
            _editor_context(
                session,
                tracks=enabled_tracks_qs,
                current_project=current_project,
                export_error='This session has no enabled tracks. '
                             'Enable at least one track to export.',
                auto_open_picker=False,
            ),
        )

    body = build_rpp(session)
    response = HttpResponse(body, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="{_safe_filename(session.name)}.RPP"'
    )
    return response


@staff_member_required
def multitrack_export_rtracktemplate(request, session_id):
    """GET: download a Reaper .RTrackTemplate file for this session (RPP-05).

    Same body as .RPP but no <REAPER_PROJECT> wrapper. Filename:
    <safe(session.name)>.RTrackTemplate.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    session = MultitrackSession.objects.filter(
        id=session_id, project=current_project
    ).select_related('console').first()
    if not session:
        return redirect('planner:multitrack_dashboard')

    if not _has_enabled_tracks(session):
        # Route through _editor_context (Plan 03) — see multitrack_export_rpp
        # above for the rationale.
        enabled_tracks_qs = session.tracks.filter(enabled=True).order_by('track_number')
        return render(
            request,
            'planner/multitrack/editor.html',
            _editor_context(
                session,
                tracks=enabled_tracks_qs,
                current_project=current_project,
                export_error='This session has no enabled tracks. '
                             'Enable at least one track to export.',
                auto_open_picker=False,
            ),
        )

    body = build_rtracktemplate(session)
    response = HttpResponse(body, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="{_safe_filename(session.name)}.RTrackTemplate"'
    )
    return response


# ──────────────────────────────────────────────────────────────────
# Multitrack — Nuendo Live file-download view (Phase 4 / Plan 05)
# Delegates .nlpr generation to planner.utils.nuendo_live_export.
# Auth gate matches Phase 1's download views (@staff_member_required)
# per Phase 1 CR-01/CR-02 fix scope — those retightened only AJAX
# mutate endpoints, NOT downloads. Confirmed at planner/views.py:6875,
# :6923 as of 2026-05-13.
# ──────────────────────────────────────────────────────────────────


@staff_member_required
def multitrack_export_nlpr(request, session_id):
    """GET: download a Nuendo Live 3 .nlpr file for this session.

    Verifies NLP-01..06:
      - NLP-01: button-triggered download via the bundled empty-template
        injection path (delegated to build_nlpr).
      - NLP-02..05: name + Farb correctness (HUMAN-UAT — engineer opens
        the file in Nuendo Live 3 to confirm).
      - NLP-06: ID/RuntimeID uniqueness — covered by
        planner.tests.test_nuendo_live_export.

    Response shape: HttpResponse, Content-Type
    application/xml; charset=utf-8, Content-Disposition attachment with
    filename <_safe_filename(session.name)>.nlpr.

    Failure modes:
      - No current_project on the request → 302 to /.
      - session_id not in current_project → 302 to multitrack_dashboard
        (IDOR-safe combined filter).
      - Session has no enabled tracks → render editor.html with
        export_error (D-03 reused from Phase 1 pattern at :6900-6912).
      - Bundled fixture missing / malformed (build_nlpr raises
        ExportTemplateError) → render editor.html with the D-03
        banner copy.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    session = MultitrackSession.objects.filter(
        id=session_id, project=current_project
    ).select_related('console').first()
    if not session:
        return redirect('planner:multitrack_dashboard')

    if not _has_enabled_tracks(session):
        enabled_tracks_qs = session.tracks.filter(
            enabled=True,
        ).order_by('track_number')
        return render(
            request,
            'planner/multitrack/editor.html',
            _editor_context(
                session,
                tracks=enabled_tracks_qs,
                current_project=current_project,
                export_error='This session has no enabled tracks. '
                             'Enable at least one track to export.',
                auto_open_picker=False,
            ),
        )

    try:
        body = build_nlpr(session)
    except ExportTemplateError:
        # CONTEXT.md D-03: missing or malformed bundled fixture →
        # render editor with an export_error banner instead of 500.
        enabled_tracks_qs = session.tracks.filter(
            enabled=True,
        ).order_by('track_number')
        return render(
            request,
            'planner/multitrack/editor.html',
            _editor_context(
                session,
                tracks=enabled_tracks_qs,
                current_project=current_project,
                export_error='Nuendo Live export is unavailable on '
                             'this server — bundled template missing '
                             'or malformed. Contact support.',
                auto_open_picker=False,
            ),
        )

    response = HttpResponse(
        body, content_type='application/xml; charset=utf-8',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{_safe_filename(session.name)}.nlpr"'
    )
    return response


# -------------------------------------------------------------------------
# Phase 2 — Console CSV Import (CSV-01..CSV-05)
# A CSV upload creates a NEW console in the current project. One-shot flow:
# upload → parse → create Console + channel rows → redirect to dashboard.
# -------------------------------------------------------------------------

def _console_import_viewer_block(request):
    """Viewers are blocked from the upload surface (D-09)."""
    if request.user.groups.filter(name='Viewer').exists():
        return HttpResponseForbidden('Read-only access.')
    return None


def _stereo_type_for_row(section, family, row):
    """Map an in-scope stereo row to its ConsoleStereoOutput.stereo_type value.

    Returns 'L' / 'R' / 'M' for importable rows; returns None for rows that should
    be skipped (already filtered upstream, but defensive).
    """
    if section == 'StMonoName':
        return {1: 'L', 2: 'R', 3: 'M'}.get(row.get('channel_number'))
    if section == 'StName' and family == 'rivage_pm':
        return {'_AL': 'L', '_AR': 'R'}.get(row.get('key'))
    return None


def _apply_csv_to_new_console(parsed_sections, console):
    """Populate a freshly-created (empty) console from a parsed CSV payload.

    Creates one row per CSV row across the four in-scope channel models. Default
    rows ARE imported (with their CSV values, e.g. `source='ch 1'`) so the
    multitrack picker exposes the console's full inventory.

    `ConsoleInput.source` is the name field — NOT `.name` — for inputs.
    All other channel models use `.name`.

    Returns a summary dict written to ConsoleImport.summary.
    """
    summary = {
        'created_inputs': 0,
        'created_aux': 0,
        'created_matrix': 0,
        'created_stereo': 0,
        'skipped': 0,
        'errors': [],
    }

    for section_data in parsed_sections.get('sections', []):
        section = section_data.get('section')
        family = section_data.get('family')

        # Out-of-scope sections (DCAs, CL/QL StName returns, etc.) — log informational
        if not section or section in OUT_OF_SCOPE_SECTIONS:
            for err in section_data.get('errors', []):
                summary['errors'].append(err)
                summary['skipped'] += 1
            continue

        if section == 'InName':
            model_cls, lookup_field, name_field = ConsoleInput, 'input_ch', 'source'
            tally_key = 'created_inputs'
        elif section == 'MixName':
            model_cls, lookup_field, name_field = ConsoleAuxOutput, 'aux_number', 'name'
            tally_key = 'created_aux'
        elif section == 'MtxName':
            model_cls, lookup_field, name_field = ConsoleMatrixOutput, 'matrix_number', 'name'
            tally_key = 'created_matrix'
        elif section == 'StMonoName' or (section == 'StName' and family == 'rivage_pm'):
            model_cls, lookup_field, name_field = ConsoleStereoOutput, 'stereo_type', 'name'
            tally_key = 'created_stereo'
        else:
            for err in section_data.get('errors', []):
                summary['errors'].append(err)
            continue

        for row in section_data.get('rows', []):
            if model_cls is ConsoleStereoOutput:
                stereo_type = _stereo_type_for_row(section, family, row)
                if not stereo_type:
                    continue
                lookup_value = stereo_type
            else:
                lookup_value = str(row.get('channel_number') or '')
                if not lookup_value:
                    continue

            try:
                model_cls.objects.create(**{
                    'console': console,
                    lookup_field: lookup_value,
                    name_field: row.get('name', ''),
                    'color': row.get('color', 'Blue'),
                })
                summary[tally_key] += 1
            except Exception as exc:
                summary['errors'].append({
                    'code': 'E_CREATE_FAILED',
                    'detail': f'{section}:{lookup_value} — {exc}',
                })

        for err in section_data.get('errors', []):
            summary['errors'].append(err)

    return summary


@staff_member_required
def console_import_upload(request):
    """GET: render upload form. POST: create a new Console from the CSV.

    One-shot flow — no preview, no commit step:
      1. Validate form (console_name + csv_file)
      2. Parse upload (single .csv or .zip)
      3. Atomically: create Console, populate channel rows, create ConsoleImport snapshot
      4. Redirect to multitrack dashboard with success banner (D-06)

    Viewers are blocked on both GET and POST (D-09).
    """
    block = _console_import_viewer_block(request)
    if block is not None:
        return block

    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    if request.method == 'POST':
        form = ConsoleCsvUploadForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            console_name = form.cleaned_data['console_name']
            uploaded = form.cleaned_data['csv_file']
            parsed = parse_upload(uploaded, filename=uploaded.name)

            if parsed.get('fatal_error'):
                messages.error(
                    request,
                    f"Could not parse — {parsed['fatal_error']}. Verify the file is a Yamaha Editor export.",
                    extra_tags='multitrack_import',
                )
                return render(request, 'planner/multitrack/import_upload.html', {'form': form})

            try:
                uploaded.seek(0)
            except Exception:
                pass

            parsed_sections = {
                'sections': parsed['sections'],
                'family': parsed['family'],
                'is_zip': parsed['is_zip'],
            }

            with transaction.atomic():
                console = Console.objects.create(
                    project=current_project,
                    name=console_name,
                )
                summary = _apply_csv_to_new_console(parsed_sections, console)
                ConsoleImport.objects.create(
                    console=console,
                    uploaded_by=request.user,
                    original_filename=os.path.basename(uploaded.name),
                    raw_file=uploaded,
                    parsed_sections=parsed_sections,
                    summary=summary,
                    committed=True,
                )

            total = (
                summary['created_inputs']
                + summary['created_aux']
                + summary['created_matrix']
                + summary['created_stereo']
            )
            messages.success(
                request,
                f'Imported {total} channels into "{console_name}".',
                extra_tags='multitrack_import',
            )
            return redirect('planner:multitrack_dashboard')
    else:
        form = ConsoleCsvUploadForm(request=request)

    return render(request, 'planner/multitrack/import_upload.html', {'form': form})


# ──────────────────────────────────────────────────────────────────────────────
# Signal Flow Diagrammer (v2.2) — DGM-01..DGM-05 + DGM-08 stub
#
# All views follow the multitrack module pattern. See
# .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md for analogs.
#
# Helpers:
#   _signal_flow_viewer_block — 403 for Viewer group (mirrors _multitrack_viewer_block at views.py:6315)
#   _get_diagram_for_request  — IDOR-safe lookup (mirrors _get_track_for_request at views.py:6328)
# ──────────────────────────────────────────────────────────────────────────────

_signal_flow_logger = logging.getLogger(__name__)


def _signal_flow_viewer_block(request):
    """Return JsonResponse 403 iff user is in Viewer group; else None.

    Mirrors _multitrack_viewer_block (views.py:6315). Centralised so every
    signal-flow mutate endpoint applies the same check.
    """
    if request.user.groups.filter(name='Viewer').exists():
        return JsonResponse({'error': 'Read-only access.'}, status=403)
    return None


def _get_diagram_for_request(request, diagram_id):
    """Return SignalFlowDiagram iff it belongs to request.current_project.

    IDOR-safe lookup. Returns None when the diagram doesn't exist or belongs
    to a different project. Mirrors _get_track_for_request (views.py:6328).

    Enforces DGM-05: cross-project access yields None -> caller returns 404.
    """
    project = getattr(request, 'current_project', None)
    if not project:
        return None
    return SignalFlowDiagram.objects.filter(
        id=diagram_id, project=project
    ).first()


@staff_member_required
def signal_flow_list(request):
    """List view of SignalFlowDiagrams for the current project (DGM-01)."""
    current_project = getattr(request, 'current_project', None)
    diagrams = (
        SignalFlowDiagram.objects.filter(project=current_project)
        .order_by('-updated_at')
        if current_project else SignalFlowDiagram.objects.none()
    )
    return render(request, 'planner/signal_flow/list.html', {
        'diagrams': diagrams,
        'current_project': current_project,
    })


@login_required
@require_POST
def signal_flow_create(request):
    """Create a new SignalFlowDiagram in the current project (DGM-02).

    POST body: {"name": "<diagram name>"}
    Returns: {"ok": true, "redirect_url": "/audiopatch/signal-flow/<id>/"}
    """
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        project = getattr(request, 'current_project', None)
        if not project:
            return JsonResponse({'error': 'No active project'}, status=400)
        data = json.loads(request.body or '{}')
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)
        if SignalFlowDiagram.objects.filter(project=project, name=name).exists():
            return JsonResponse({
                'error': f'A diagram named "{name}" already exists in this project.',
            }, status=409)
        diagram = SignalFlowDiagram.objects.create(project=project, name=name)
        return JsonResponse({
            'ok': True,
            'redirect_url': reverse('planner:signal_flow_editor', args=[diagram.id]),
        })
    except Exception:
        _signal_flow_logger.exception('signal_flow_create failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@staff_member_required
def signal_flow_editor(request, diagram_id):
    """Render the HTML editor shell (DGM-05).

    Canvas state is fetched separately via signal_flow_state — the shell
    does not embed inline JSON. Cross-project diagram_id returns the user
    to the list page (404-equivalent for a page render — no leak).
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')
    diagram = SignalFlowDiagram.objects.filter(
        id=diagram_id, project=current_project
    ).first()
    if not diagram:
        return redirect('planner:signal_flow_list')
    return render(request, 'planner/signal_flow/editor.html', {
        'diagram': diagram,
    })


@login_required
@require_POST
def signal_flow_rename(request, diagram_id):
    """Rename a diagram (DGM-03). Enforces unique-per-project name.

    POST body: {"name": "<new name>"}
    Returns: {"ok": true, "name": "<new name>"} or {"error": ...} with
    400/404/409/500 as appropriate.
    """
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        project = getattr(request, 'current_project', None)
        if not project:
            return JsonResponse({'error': 'No active project'}, status=400)
        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)
        data = json.loads(request.body or '{}')
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(new_name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)
        if SignalFlowDiagram.objects.filter(
            project=project, name=new_name
        ).exclude(pk=diagram.pk).exists():
            return JsonResponse({
                'error': f'A diagram named "{new_name}" already exists in this project.',
            }, status=409)
        diagram.name = new_name
        diagram.save(update_fields=['name', 'updated_at'])
        return JsonResponse({'ok': True, 'name': new_name})
    except Exception:
        _signal_flow_logger.exception('signal_flow_rename failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def signal_flow_delete(request, diagram_id):
    """Delete a diagram (DGM-04). CASCADE handles single-table cleanup.

    Returns: {"ok": true, "redirect_url": "/audiopatch/signal-flow/"}
    """
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        project = getattr(request, 'current_project', None)
        if not project:
            return JsonResponse({'error': 'No active project'}, status=400)
        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)
        diagram.delete()
        return JsonResponse({
            'ok': True,
            'redirect_url': reverse('planner:signal_flow_list'),
        })
    except Exception:
        _signal_flow_logger.exception('signal_flow_delete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


# ── Stub endpoints (filled in Phase 8-10) ──────────────────────────────────

def _enrich_nodes(canvas_state, project):
    """Refresh GFK-linked cell labels and flag missing equipment as orphans.

    Phase 9 D-12: GET-only enrichment. Deep-copies the input — never mutates
    the persisted blob.
    Phase 9 D-13: One SELECT per content type. SpeakerArray scopes via
    `prediction__project`; others via `project` (same predicate as the IDOR
    walk at signal_flow_autosave).
    Phase 9 D-14: Live ref  -> isOrphan = False, savedLabel + attrs.label.text = live name
                  Missing   -> isOrphan = True,  savedLabel + label.text untouched
                  Non-linked cells (Generic, connectors) untouched.
    Never raises on missing CT -> treated as orphan.
    """
    import copy
    from collections import defaultdict
    from django.contrib.contenttypes.models import ContentType

    if not isinstance(canvas_state, dict):
        return canvas_state
    result = copy.deepcopy(canvas_state)
    cells = result.get('cells') or []

    # 1) Group (ct_id, obj_id) pairs by content_type.
    by_ct = defaultdict(set)
    for cell in cells:
        prop = cell.get('showstack') if isinstance(cell, dict) else None
        if not isinstance(prop, dict):
            continue
        ct_id, obj_id = prop.get('contentTypeId'), prop.get('objectId')
        if ct_id and obj_id:
            by_ct[ct_id].add(obj_id)

    # 2) Bulk SELECT per content type — IDOR-scoped (PITFALLS.md §4 + views.py:7587-7624).
    resolved = {}  # {(ct_id, obj_id): name}
    for ct_id, obj_ids in by_ct.items():
        ct = ContentType.objects.filter(id=ct_id).first()
        if not ct:
            continue  # unknown CT — every cell with this ct_id becomes orphan
        Model = ct.model_class()
        if Model is None:
            continue
        model_name = Model.__name__
        if model_name == 'SpeakerArray':
            qs = Model.objects.filter(id__in=obj_ids, prediction__project=project)
        elif model_name in ('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor'):
            # Phase 10 SHP-10 + SHP-11: Amp and SystemProcessor both have a
            # direct project FK and a `name` field, so the values_list('id', 'name')
            # call below works unchanged. Without this extension, Processor/Amp
            # cells would render as permanent orphans even when the record exists.
            qs = Model.objects.filter(id__in=obj_ids, project=project)
        else:
            continue  # unknown model -> orphan (safe default)
        for row_id, row_name in qs.values_list('id', 'name'):
            resolved[(ct_id, row_id)] = row_name

    # 3) Second pass — mutate each linked cell (D-14).
    for cell in cells:
        prop = cell.get('showstack') if isinstance(cell, dict) else None
        if not isinstance(prop, dict):
            continue
        ct_id, obj_id = prop.get('contentTypeId'), prop.get('objectId')
        if not ct_id or not obj_id:
            continue
        name = resolved.get((ct_id, obj_id))
        if name is not None:
            prop['isOrphan'] = False
            prop['savedLabel'] = name
            attrs = cell.setdefault('attrs', {})
            label = attrs.setdefault('label', {})
            label['text'] = name
        else:
            prop['isOrphan'] = True
            # savedLabel + attrs.label.text intentionally untouched (D-14)

    return result


@staff_member_required
@require_GET
def signal_flow_state(request, diagram_id):
    """GET — return enriched canvas_state JSON (Phase 9: SHP-06 + SHP-07).

    Phase 9 D-12: enriches linked cell labels from live equipment records
    and flags missing refs as orphans. The persisted blob is never mutated;
    callers receive a deep-copied + mutated view.
    """
    diagram = _get_diagram_for_request(request, diagram_id)
    if not diagram:
        return JsonResponse({'error': 'Not found'}, status=404)
    enriched = _enrich_nodes(diagram.canvas_state or {}, request.current_project)
    return JsonResponse({
        'canvas_state': enriched,
        'viewport': diagram.viewport,
        'version': diagram.version,
    })


@login_required
@require_POST
def signal_flow_autosave(request, diagram_id):
    """Persist canvas_state + viewport with optimistic-lock conflict detection (DGM-07).

    Body shapes:
      - Full save:        {"canvas_state": {...}, "viewport": {...}}
      - Viewport-only:    {"viewport": {...}}  with ?viewport_only=1 query param

    Phase 9 If-Match: full canvas-state saves require the client to send the
    version it loaded in the If-Match request header. Missing/stale header
    returns 409. Viewport-only writes remain last-write-wins (D-05).

    Phase 8 IDOR walk (views.py:7663-7700) stays verbatim — still rejects any
    (contentTypeId, objectId) that doesn't belong to request.current_project.
    SpeakerArray scopes via prediction__project (no direct project FK).
    """
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block

    try:
        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)

        payload = json.loads(request.body or '{}')

        # Branch: viewport-only writes (RESEARCH §10 + §19 — folded into the same URL
        # via ?viewport_only=1 to keep URL count stable).
        if request.GET.get('viewport_only') == '1':
            viewport = payload.get('viewport') or {}
            if not isinstance(viewport, dict):
                return JsonResponse({'error': 'Bad viewport payload'}, status=400)
            diagram.viewport = viewport
            diagram.save(update_fields=['viewport', 'updated_at'])
            return JsonResponse({'ok': True, 'viewport_only': True})

        # Phase 9 D-05: optimistic-lock header. FULL canvas-state saves require
        # the client to advertise the version it loaded; missing or stale
        # versions get 409. (Viewport-only writes above remain last-write-wins.)
        if_match = request.headers.get('If-Match', '').strip()
        if not if_match:
            return JsonResponse({'error': 'version_required'}, status=409)
        try:
            loaded_version = int(if_match)
        except ValueError:
            return JsonResponse({'error': 'version_required'}, status=409)

        # Full canvas_state save
        canvas_state = payload.get('canvas_state') or {}
        if not isinstance(canvas_state, dict):
            return JsonResponse({'error': 'Bad canvas_state payload'}, status=400)

        # Walk canvas JSON, validate every linked equipment ref (PITFALLS.md §4).
        # Local import keeps the global views.py import surface unchanged.
        from django.contrib.contenttypes.models import ContentType
        current_project = request.current_project
        cells = canvas_state.get('cells') or []
        for cell in cells:
            prop = cell.get('showstack') if isinstance(cell, dict) else None
            if not isinstance(prop, dict):
                continue
            ct_id = prop.get('contentTypeId')
            obj_id = prop.get('objectId')
            if not ct_id or not obj_id:
                continue
            ct = ContentType.objects.filter(id=ct_id).first()
            if not ct:
                return JsonResponse({'error': f'Unknown content type {ct_id}'}, status=422)
            Model = ct.model_class()
            if Model is None:
                return JsonResponse({'error': f'Content type {ct_id} not resolvable'}, status=422)
            # IDOR — SpeakerArray uses prediction__project; others use an explicit
            # allowlist (PATTERNS.md risk #3). hasattr() is intentionally avoided:
            # a future model with a non-FK 'project' attribute would silently pass
            # the old guard and scope incorrectly or not at all.
            model_name = Model.__name__
            if model_name == 'SpeakerArray':
                exists = Model.objects.filter(
                    id=obj_id, prediction__project=current_project,
                ).exists()
            elif model_name in ('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor'):
                # Phase 10 SHP-10 + SHP-11: Amp and SystemProcessor are valid
                # canvas GFK targets (both have a direct project FK). Without
                # this extension, every Phase 10 autosave with a new shape
                # type would return HTTP 422 — research §Pitfall 1 (the most
                # likely silent-failure bug). P1Processor/GalaxyProcessor are
                # NOT in the allowlist: the picker targets SystemProcessor.
                exists = Model.objects.filter(
                    id=obj_id, project=current_project,
                ).exists()
            else:
                return JsonResponse(
                    {'error': f'Type {ct.model} has no project scope'}, status=422,
                )
            if not exists:
                return JsonResponse(
                    {'error': 'Equipment reference out of project'}, status=422,
                )

        # Phase 9 D-06: atomic version-pinned UPDATE. Cheaper than
        # select_for_update() — single round-trip; on stale version the
        # rowcount is 0 and we return 409 without touching the blob.
        new_viewport = (
            payload['viewport']
            if 'viewport' in payload and isinstance(payload['viewport'], dict)
            else diagram.viewport
        )
        with transaction.atomic():
            rowcount = SignalFlowDiagram.objects.filter(
                id=diagram.id, version=loaded_version,
            ).update(
                canvas_state=canvas_state,
                viewport=new_viewport,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
        if rowcount == 0:
            current = (
                SignalFlowDiagram.objects.filter(id=diagram.id)
                .values_list('version', flat=True).first()
            )
            return JsonResponse(
                {'error': 'version_conflict', 'current_version': current},
                status=409,
            )
        return JsonResponse({'ok': True, 'version': loaded_version + 1})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Bad JSON'}, status=400)
    except Exception:
        _signal_flow_logger.exception('signal_flow_autosave failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@staff_member_required
def signal_flow_autocomplete(request):
    """GET: equipment picker autocomplete for the canvas sidebar shape drops.

    Returns a project-scoped list of equipment records matching ?type=X (&q=...).
    type ∈ {console, device, speakerarray, commbeltpack, processor, amp}.

    Phase 10 (SHP-10 + SHP-11): added 'processor' (-> SystemProcessor, badge from
    device_type) and 'amp' (-> Amp, badge from amp_model) so the equipment picker
    modal can serve the new Phase 10 shape types. Processor picker targets
    SystemProcessor — NOT P1Processor / GalaxyProcessor (research §Pitfall 2).

    IDOR-safe: SpeakerArray scopes via prediction__project (no direct FK);
    all others via project FK. Pattern: _get_track_for_request (views.py:6328).

    Phase 10 will add a SEPARATE signal_flow_label_autocomplete URL for
    circuit-label string completion; this view stays equipment-only.
    """
    try:
        from django.contrib.contenttypes.models import ContentType

        shape_type = (request.GET.get('type') or '').lower().strip()
        q = (request.GET.get('q') or '').strip()

        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        # Per-type config: (Model, project_filter_kwargs, search_fields, label_fn, detail_fn).
        # project_filter is a kwarg dict so SpeakerArray can use prediction__project
        # without polluting the others. label_fn returns primary text; detail_fn returns secondary.
        MODEL_MAP = {
            'console': (
                Console,
                {'project': current_project},
                ['name'],
                lambda c: c.name,
                lambda c: ('Template' if c.is_template else (c.primary_ip_address or '—')),
            ),
            'device': (
                Device,
                {'project': current_project},
                ['name'],
                lambda d: d.name,
                lambda d: f"{d.input_count} in × {d.output_count} out",
            ),
            'speakerarray': (
                SpeakerArray,
                {'prediction__project': current_project},  # PATTERNS.md risk #3 — NO direct project FK
                ['source_name', 'array_base_name'],
                lambda s: s.source_name,  # SpeakerArray has no `name` field
                lambda s: f"{s.array_base_name} · {s.get_configuration_display()}",
            ),
            'commbeltpack': (
                CommBeltPack,
                {'project': current_project},
                ['bp_number', 'manufacturer'],
                lambda b: f"BP #{b.bp_number}",
                lambda b: b.get_manufacturer_display(),
            ),
            # Phase 10 SHP-10: Processor picker -> SystemProcessor. Badge text
            # comes from device_type ("L'Acoustics P1" / "Meyer GALAXY") so the
            # picker modal can distinguish brands per D-10. NOT P1Processor /
            # GalaxyProcessor (research §Pitfall 2 — those are child config
            # models, never canvas GFK targets).
            'processor': (
                SystemProcessor,
                {'project': current_project},
                ['name'],
                lambda sp: sp.name,
                lambda sp: sp.get_device_type_display(),
            ),
            # Phase 10 SHP-11: Amp picker. Badge text is the AmpModel
            # (manufacturer/model). select_related('amp_model') added below
            # to prevent N+1 on str(a.amp_model) across the result list.
            'amp': (
                Amp,
                {'project': current_project},
                ['name'],
                lambda a: a.name,
                lambda a: str(a.amp_model) if a.amp_model else '—',
            ),
        }

        if shape_type not in MODEL_MAP:
            return JsonResponse({'error': 'Invalid type'}, status=400)

        Model, project_kw, search_fields, label_fn, detail_fn = MODEL_MAP[shape_type]

        qs = Model.objects.filter(**project_kw)
        # Phase 10 SHP-11: prevent N+1 on str(a.amp_model) across amp results
        # (lambda detail_fn dereferences amp_model for every row).
        if shape_type == 'amp':
            qs = qs.select_related('amp_model')
        if q:
            cond = Q()
            for f in search_fields:
                # bp_number is IntegerField — only match when q is purely digits
                if f == 'bp_number':
                    if q.isdigit():
                        cond |= Q(bp_number=int(q))
                else:
                    cond |= Q(**{f'{f}__icontains': q})
            # Q() is truthy/falsy by children — only apply if at least one clause was added
            if cond.children:
                qs = qs.filter(cond)

        # Order: SpeakerArray by source_name (no `name` field); CommBeltPack by bp_number; others by name.
        order_key = (
            'source_name' if shape_type == 'speakerarray'
            else ('bp_number' if shape_type == 'commbeltpack' else 'name')
        )
        qs = qs.order_by(order_key)[:50]  # hard cap (CONTEXT D-11 instant-search)

        # ContentType lookup once per request
        ct = ContentType.objects.get_for_model(Model)

        results = []
        for obj in qs:
            try:
                results.append({
                    'id': obj.pk,
                    'contentTypeId': ct.pk,
                    'name': label_fn(obj),
                    'detail': detail_fn(obj),
                })
            except Exception:
                _signal_flow_logger.exception(
                    'autocomplete row build failed for %s id=%s', shape_type, obj.pk,
                )
                continue

        return JsonResponse({'results': results})
    except Exception:
        _signal_flow_logger.exception('signal_flow_autocomplete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


# Phase 12 UAT — Amp output channel fields (CharField labels on the Amp instance).
# Defined module-level so the helper below stays readable.
_AMP_OUTPUT_FIELDS = [
    ('nl4_a_pair_1', 'NL4-A 1'),
    ('nl4_a_pair_2', 'NL4-A 2'),
    ('nl4_b_pair_1', 'NL4-B 1'),
    ('nl4_b_pair_2', 'NL4-B 2'),
    ('nl8_a_pair_1', 'NL8-A 1'),
    ('nl8_a_pair_2', 'NL8-A 2'),
    ('nl8_a_pair_3', 'NL8-A 3'),
    ('nl8_a_pair_4', 'NL8-A 4'),
    ('nl8_b_pair_1', 'NL8-B 1'),
    ('nl8_b_pair_2', 'NL8-B 2'),
    ('nl8_b_pair_3', 'NL8-B 3'),
    ('nl8_b_pair_4', 'NL8-B 4'),
    ('cacom_1_ch1', 'CaCom 1-1'),
    ('cacom_1_ch2', 'CaCom 1-2'),
    ('cacom_1_ch3', 'CaCom 1-3'),
    ('cacom_1_ch4', 'CaCom 1-4'),
    ('cacom_2_ch1', 'CaCom 2-1'),
    ('cacom_2_ch2', 'CaCom 2-2'),
    ('cacom_2_ch3', 'CaCom 2-3'),
    ('cacom_2_ch4', 'CaCom 2-4'),
    ('cacom_3_ch1', 'CaCom 3-1'),
    ('cacom_3_ch2', 'CaCom 3-2'),
    ('cacom_3_ch3', 'CaCom 3-3'),
    ('cacom_3_ch4', 'CaCom 3-4'),
    ('cacom_4_ch1', 'CaCom 4-1'),
    ('cacom_4_ch2', 'CaCom 4-2'),
    ('cacom_4_ch3', 'CaCom 4-3'),
    ('cacom_4_ch4', 'CaCom 4-4'),
    ('sc32_ch1',  'SC32-1'),  ('sc32_ch2',  'SC32-2'),
    ('sc32_ch3',  'SC32-3'),  ('sc32_ch4',  'SC32-4'),
    ('sc32_ch5',  'SC32-5'),  ('sc32_ch6',  'SC32-6'),
    ('sc32_ch7',  'SC32-7'),  ('sc32_ch8',  'SC32-8'),
    ('sc32_ch9',  'SC32-9'),  ('sc32_ch10', 'SC32-10'),
    ('sc32_ch11', 'SC32-11'), ('sc32_ch12', 'SC32-12'),
    ('sc32_ch13', 'SC32-13'), ('sc32_ch14', 'SC32-14'),
    ('sc32_ch15', 'SC32-15'), ('sc32_ch16', 'SC32-16'),
]


def _signal_flow_instance_port_labels(ct_id, oid, edge, q, current_project):
    """Return port-label suggestions for a single equipment instance.

    Returns None when the request can't be served by an instance-specific
    lookup (unknown content type, IDOR-out-of-project, unsupported model).
    The caller falls back to the project-wide autocomplete in that case.

    For Amp: top/left edges (inbound) → AmpChannel.channel_name; bottom/right
    edges (outbound) → the NL4/NL8/CaCom/SC32 char-field labels declared on
    the Amp row. Empty/blank values are skipped (Pitfall 5).

    For Console: inbound → ConsoleInput.source; outbound → ConsoleAuxOutput.name,
    then ConsoleMatrixOutput.name, then ConsoleStereoOutput.name. Same UAT
    contract as Amp — both I/O groups appear in every dropdown, inputs first.

    For SystemProcessor: branches on device_type. P1 → P1Input.label then
    P1Output.label via the OneToOne p1_config. GALAXY → GalaxyInput.label then
    GalaxyOutput.label via galaxy_config. Blank .label rows fall back to the
    positional identifier ('Analog 1', 'AES 4', 'AVB 8') — fixed 16-in/16-out
    catalog per processor means the positional fallback never floods.

    For Device: inbound → DeviceInput.signal_name; outbound → DeviceOutput.signal_name.
    Blank signal_name falls back to 'Input N' / 'Output N' so every physical port
    surfaces regardless of signal-naming completeness. Ordered by input_number /
    output_number — the engineer adds I/O in port order and the auto-numbering
    save() hook (planner/models.py:1528, 1566) keeps that intent.
    """
    from django.contrib.contenttypes.models import ContentType

    try:
        ct = ContentType.objects.filter(id=int(ct_id)).first()
    except (TypeError, ValueError):
        return None
    if ct is None:
        return None
    model_cls = ct.model_class()
    if model_cls is None:
        return None
    try:
        obj = model_cls.objects.filter(id=int(oid)).first()
    except (TypeError, ValueError):
        return None
    if obj is None:
        return None

    # IDOR — instance must belong to the requester's active project.
    if getattr(obj, 'project_id', None) != current_project.id:
        return None

    # UAT 2026-05-27 — show both inputs and outputs in every port dropdown,
    # regardless of which edge is being authored. The engineer chooses what's
    # appropriate; we don't restrict by direction.
    results = []

    if isinstance(obj, Amp):
        # Inputs — AmpChannel.channel_name (non-blank).
        ch_qs = (obj.channels
                 .exclude(channel_name='')
                 .order_by('channel_number')
                 .values_list('channel_name', flat=True))
        for name in ch_qs:
            results.append({'label': name, 'source': 'Amp Channel'})

        # Outputs — NL4/NL8/CaCom/SC32 char fields on the Amp instance.
        for field_name, source_tag in _AMP_OUTPUT_FIELDS:
            val = (getattr(obj, field_name, '') or '').strip()
            if val:
                results.append({'label': val, 'source': source_tag})
    elif isinstance(obj, Console):
        # Inputs — ConsoleInput.source (signal name). pk order = engineer's
        # entry order (typically CH1, CH2, …); ConsoleInput has no Meta
        # ordering and input_ch is a free-text CharField so a numeric sort
        # isn't safe across all consoles.
        input_qs = (ConsoleInput.objects
                    .filter(console=obj)
                    .exclude(source='')
                    .exclude(source__isnull=True)
                    .order_by('pk')
                    .values_list('source', flat=True))
        for name in input_qs:
            results.append({'label': name, 'source': 'Console Input'})

        # Outputs — Aux first, then Matrix, then Stereo. Tag strings match
        # the project-wide SOURCES list where they overlap ('Console Aux Out')
        # and add new tags for Matrix/Stereo (instance-scoped only — the
        # project-wide fallback still excludes them, by design).
        #
        # UAT 2026-05-27 — every authored output appears in the dropdown,
        # named or not. When .name is blank, fall back to the positional
        # identifier ('Aux 1', 'Matrix 3', 'Stereo Left') so the engineer
        # can still pick the bus by number. Inputs deliberately keep the
        # name-required behavior: a 72-channel console has 72 default-empty
        # ConsoleInput rows from the CSV import and surfacing them all as
        # "Input 1"…"Input 72" would flood the dropdown.
        for aux_number, name in (ConsoleAuxOutput.objects
                                 .filter(console=obj)
                                 .order_by('pk')
                                 .values_list('aux_number', 'name')):
            label = (name or '').strip() or 'Aux {0}'.format(aux_number)
            results.append({'label': label, 'source': 'Console Aux Out'})

        for matrix_number, name in (ConsoleMatrixOutput.objects
                                    .filter(console=obj)
                                    .order_by('pk')
                                    .values_list('matrix_number', 'name')):
            label = (name or '').strip() or 'Matrix {0}'.format(matrix_number)
            results.append({'label': label, 'source': 'Console Matrix Out'})

        # ConsoleStereoOutput.Meta.ordering = ['stereo_type'] → L, M, R.
        # STEREO_CHOICES: L='Stereo Left', R='Stereo Right', M='Mono'.
        STEREO_DISPLAY = dict(ConsoleStereoOutput.STEREO_CHOICES)
        for stereo_type, name in (ConsoleStereoOutput.objects
                                  .filter(console=obj)
                                  .values_list('stereo_type', 'name')):
            label = (name or '').strip() or STEREO_DISPLAY.get(stereo_type, stereo_type)
            results.append({'label': label, 'source': 'Console Stereo Out'})
    elif isinstance(obj, SystemProcessor):
        # Cells link to SystemProcessor (the GFK target — see editor.js:1058);
        # P1 vs GALAXY routing comes from device_type. Each sub-processor has
        # its own input/output table reached via the OneToOne back-relation.
        # Blank .label rows fall back to the positional identifier — fixed
        # 16-in/16-out catalog per processor (Analog 1-4, AES 1-4, AVB 1-8)
        # means the fallback never floods the dropdown (different tradeoff
        # from Console, where 72 default-empty inputs would).
        if obj.device_type == 'P1':
            p1 = getattr(obj, 'p1_config', None)
            if p1 is not None:
                P1_IN_DISPLAY = dict(P1Input.INPUT_TYPES)
                for input_type, channel_number, label in (
                    P1Input.objects
                    .filter(p1_processor=p1)
                    .order_by('input_type', 'channel_number')
                    .values_list('input_type', 'channel_number', 'label')
                ):
                    final = (label or '').strip() or '{0} {1}'.format(
                        P1_IN_DISPLAY.get(input_type, input_type), channel_number
                    )
                    results.append({'label': final, 'source': 'P1 Input'})

                P1_OUT_DISPLAY = dict(P1Output.OUTPUT_TYPES)
                for output_type, channel_number, label in (
                    P1Output.objects
                    .filter(p1_processor=p1)
                    .order_by('output_type', 'channel_number')
                    .values_list('output_type', 'channel_number', 'label')
                ):
                    final = (label or '').strip() or '{0} {1}'.format(
                        P1_OUT_DISPLAY.get(output_type, output_type), channel_number
                    )
                    results.append({'label': final, 'source': 'P1 Output'})
        elif obj.device_type == 'GALAXY':
            galaxy = getattr(obj, 'galaxy_config', None)
            if galaxy is not None:
                GX_IN_DISPLAY = dict(GalaxyInput.INPUT_TYPE_CHOICES)
                for input_type, channel_number, label in (
                    GalaxyInput.objects
                    .filter(galaxy_processor=galaxy)
                    .order_by('input_type', 'channel_number')
                    .values_list('input_type', 'channel_number', 'label')
                ):
                    final = (label or '').strip() or '{0} {1}'.format(
                        GX_IN_DISPLAY.get(input_type, input_type), channel_number
                    )
                    results.append({'label': final, 'source': 'Galaxy Input'})

                GX_OUT_DISPLAY = dict(GalaxyOutput.OUTPUT_TYPE_CHOICES)
                for output_type, channel_number, label in (
                    GalaxyOutput.objects
                    .filter(galaxy_processor=galaxy)
                    .order_by('output_type', 'channel_number')
                    .values_list('output_type', 'channel_number', 'label')
                ):
                    final = (label or '').strip() or '{0} {1}'.format(
                        GX_OUT_DISPLAY.get(output_type, output_type), channel_number
                    )
                    results.append({'label': final, 'source': 'Galaxy Output'})
        else:
            return None     # unknown device_type — fall back to project-wide
    elif isinstance(obj, Device):
        # Inputs — DeviceInputInlineForm (planner/forms.py:384-440) only
        # binds (input_number, console_input FK) and never writes signal_name,
        # so on disk signal_name stays '' and the human label lives on
        # console_input.source. UAT 2026-05-27 — surface that source as the
        # dropdown label. Precedence: explicit signal_name (legacy/direct
        # edit) → console_input.source → positional 'Input N' fallback.
        for input_number, signal_name, ci_source in (
            DeviceInput.objects
            .filter(device=obj)
            .order_by('input_number')
            .values_list('input_number', 'signal_name', 'console_input__source')
        ):
            label = (
                (signal_name or '').strip()
                or (ci_source or '').strip()
                or 'Input {0}'.format(input_number)
            )
            results.append({'label': label, 'source': 'Device Input'})

        # Outputs — DeviceOutputInlineForm.save() (planner/forms.py:546)
        # mirrors console_output.name into signal_name on every save, so
        # signal_name is the authoritative on-disk label here. Positional
        # fallback ('Output N') for rows the engineer hasn't routed yet.
        for output_number, signal_name in (DeviceOutput.objects
                                           .filter(device=obj)
                                           .order_by('output_number')
                                           .values_list('output_number', 'signal_name')):
            label = (signal_name or '').strip() or 'Output {0}'.format(output_number)
            results.append({'label': label, 'source': 'Device Output'})
    else:
        return None     # unsupported — caller falls back to project-wide list

    if q:
        q_lower = q.lower()
        results = [r for r in results if q_lower in r['label'].lower()]

    # Dedupe by (label, source). Insertion order is preserved so inputs
    # (appended first) always appear before outputs (appended second). Within
    # each section, results stay in their natural source order. Do NOT
    # alphabetical-sort here.
    #
    # UAT 2026-05-27 — no row cap. A linked Console row can carry 48-72
    # inputs PLUS aux/matrix/stereo outputs, blowing past the previous
    # [:50] cap and truncating every output off the end of the list.
    # Project-scoped + IDOR-guarded already, so there's no abuse surface.
    seen = set()
    unique = []
    for r in results:
        key = (r['label'], r['source'])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


@staff_member_required
@require_GET
def signal_flow_label_autocomplete(request):
    """GET: signal-name autocomplete for connector circuit-label and port labels.

    Returns project-scoped label suggestions from 9 signal-name fields across
    Device, Console, Amp, and Processor I/O models. Intended for the Phase 10
    autocomplete combobox on #sfd-circuit-label and the future Phase 11
    PORT-03 picker (D-04 — same endpoint, no re-implementation).

    Locked behaviour:
      - D-01: triggered after 1 char typed, 200ms debounce enforced client-side.
      - D-02: each result has {label, source} where source is a human tag.
      - D-03: max 8 results, alphabetical by label (case-insensitive).
      - D-05: SystemProcessor is EXCLUDED — SystemProcessor.name is a device
              identifier ("P1 Stage Left"), not a signal name. Signal-name data
              lives on P1Input.label / P1Output.label (via P1Processor) and
              GalaxyInput.label / GalaxyOutput.label (via GalaxyProcessor).
              See planner/models.py:1898 (SystemProcessor), 2028 (P1Input),
              2067 (P1Output), 2128 (GalaxyInput), 2163 (GalaxyOutput).
      - LBL-02 / T-10-01: all 9 source queries are filtered by the
              caller's request.current_project — cross-project labels never
              appear (IDOR guard active).

    Empty/null label values are excluded — without this, blank AmpChannel
    rows (default channel_name="") would flood the dropdown (research
    §Pitfall 5).
    """
    # Phase 11 GAP-11.1: per-shape autocomplete scoping.
    # When the engineer authors a port on a Device shape, suggestions should come
    # from Device I/O fields, NOT Amp Channel (the UAT bug). Allowlist keys are
    # cell.get('type') values defined in planner/static/planner/js/signal_flow_editor.js.
    # SpeakerArray / CommBeltPack / Generic deliberately absent → fall through to
    # the unscoped 9-source list (no catalog of their own; same as connector circuit
    # label). Unknown shape_class values also fall through (allowlist-only filter).
    # Backwards compat: callers that omit shape_class (e.g. the connector circuit-label
    # autocomplete at signal_flow_editor.js:2652) see ZERO behavior change.
    SHAPE_CLASS_SOURCES = {
        'showstack.Console':   {'Console Input', 'Console Aux Out'},
        'showstack.Device':    {'Device Input', 'Device Output'},
        'showstack.Amp':       {'Amp Channel'},
        'showstack.Processor': {'P1 Input', 'P1 Output', 'Galaxy Input', 'Galaxy Output'},
    }
    # UAT 2026-05-27 — shapes with no signal-name catalog. Port labels here
    # are pure freeform: SpeakerArray names ('KARA 1 Top', 'SUB L') are
    # physical-position descriptors, and CommBeltPack port labels are
    # channel/role assignments authored on the diagram itself, not signals
    # routed elsewhere in the project. Returning [] short-circuits both
    # the per-instance and project-wide paths; the frontend's empty-results
    # branch closes the listbox, so no dropdown ever renders.
    SHAPE_CLASS_BLOCK = {'showstack.SpeakerArray', 'showstack.CommBeltPack'}
    try:
        q = (request.GET.get('q') or '').strip()
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        shape_class = (request.GET.get('shape_class') or '').strip()
        if shape_class in SHAPE_CLASS_BLOCK:
            return JsonResponse({'results': []})

        # Phase 12 UAT — cell-instance-specific I/O lookup.
        # When the engineer is authoring a port on a specific equipment cell,
        # the dropdown should show that record's actual I/O labels, not project-wide.
        # Triggered by `ct` (content-type id) + `oid` (object id) + `edge` query params.
        # Currently implemented for showstack.Amp; other shapes fall through to the
        # project-wide list below.
        ct_id = request.GET.get('ct')
        oid = request.GET.get('oid')
        edge = (request.GET.get('edge') or '').lower()
        if ct_id and oid:
            instance_results = _signal_flow_instance_port_labels(
                ct_id, oid, edge, q, current_project
            )
            if instance_results is not None:
                return JsonResponse({'results': instance_results})

        # (Model, label_field, project-scope kwarg, human source tag).
        # SystemProcessor is intentionally NOT in this list (D-05).
        #
        # DeviceInput appears TWICE under the same 'Device Input' tag —
        # once for console_input__source, once for signal_name. The
        # DeviceInputInlineForm (planner/forms.py:384-440) binds the
        # engineer's pick to the console_input FK and never writes
        # signal_name, so the production data path leaves signal_name=''
        # and the visible label lives on the linked ConsoleInput.source.
        # The signal_name entry stays for legacy / direct-edit rows. The
        # (val, tag) dedupe below collapses any overlap.
        SOURCES = [
            (DeviceInput,      'console_input__source', 'device__project',
             'Device Input'),
            (DeviceInput,      'signal_name',  'device__project',
             'Device Input'),
            (DeviceOutput,     'signal_name',  'device__project',
             'Device Output'),
            (ConsoleInput,     'source',       'console__project',
             'Console Input'),
            (ConsoleAuxOutput, 'name',         'console__project',
             'Console Aux Out'),
            (AmpChannel,       'channel_name', 'amp__project',
             'Amp Channel'),
            (P1Input,          'label',        'p1_processor__system_processor__project',
             'P1 Input'),
            (P1Output,         'label',        'p1_processor__system_processor__project',
             'P1 Output'),
            (GalaxyInput,      'label',        'galaxy_processor__system_processor__project',
             'Galaxy Input'),
            (GalaxyOutput,     'label',        'galaxy_processor__system_processor__project',
             'Galaxy Output'),
        ]

        # Phase 11 GAP-11.1: optionally narrow SOURCES to the requesting shape's catalog.
        # Allowlist-only: unknown shape_class → fall through (no exception, no 500).
        # shape_class was parsed and SHAPE_CLASS_BLOCK already short-circuited above.
        if shape_class and shape_class in SHAPE_CLASS_SOURCES:
            allowed_tags = SHAPE_CLASS_SOURCES[shape_class]
            SOURCES = [row for row in SOURCES if row[3] in allowed_tags]

        seen = set()
        results = []
        for Model, field, scope_kwarg, tag in SOURCES:
            filter_kw = {scope_kwarg: current_project}
            if q:
                filter_kw[f'{field}__icontains'] = q
            qs = (Model.objects
                  .filter(**filter_kw)
                  .exclude(**{field: ''})
                  .exclude(**{f'{field}__isnull': True})
                  .values_list(field, flat=True)
                  .distinct()[:50])
            for val in qs:
                key = (val, tag)
                if key not in seen:
                    seen.add(key)
                    results.append({'label': val, 'source': tag})

        results.sort(key=lambda r: r['label'].lower())
        return JsonResponse({'results': results[:8]})
    except Exception:
        _signal_flow_logger.exception('signal_flow_label_autocomplete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@staff_member_required
def signal_flow_export_png(request, diagram_id):
    """GET stub for PNG export (Phase 10 fills via html-to-image).

    URL must exist now so editor.html data-export-png-url resolves.
    """
    return JsonResponse({'error': 'Not yet implemented'}, status=501)
