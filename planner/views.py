from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.models import Max
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
from .models import CommConfig, CommConfigPartyline, CommConfigRole, CommConfigKeyset, CommConfigRoleset, CommConfigSession, CommConfigPortAssignment, CommConfigDanteChannel, CommCrewName
from .models import Amp, AmpDivider, Location
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
    Device, Device, SystemProcessor, Amp, Location, PACableSchedule, PAZone,
    ShowDay, MicSession, MicAssignment, MicShowInfo, MicGroup, PresenterSlot, PowerDistributionPlan, AmplifierProfile, 
    AmplifierAssignment
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
        writer.writerow(['Type', 'Channel', 'Label', 'Origin Device', 'Origin Output'])
        
        for inp in p1.inputs.all():
            origin_device = inp.origin_device_output.device.name if inp.origin_device_output else ''
            origin_output = f"Output {inp.origin_device_output.output_number}: {inp.origin_device_output.signal_name}" if inp.origin_device_output else ''
            writer.writerow([
                inp.get_input_type_display(),
                inp.channel_number,
                inp.label,
                origin_device,
                origin_output
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
            input_data = {
                'type': inp.input_type,
                'type_display': inp.get_input_type_display(),
                'channel': inp.channel_number,
                'label': inp.label
            }
            
            if inp.origin_device_output:
                input_data['origin'] = {
                    'device': inp.origin_device_output.device.name,
                    'output_number': inp.origin_device_output.output_number,
                    'signal_name': inp.origin_device_output.signal_name
                }
            
            export_data['inputs'].append(input_data)
        
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
        writer.writerow(['Type', 'Channel', 'Label', 'Origin Device', 'Origin Output'])
        
        for inp in galaxy.inputs.all():
            origin_device = inp.origin_device_output.device.name if inp.origin_device_output else ''
            origin_output = f"Output {inp.origin_device_output.output_number}: {inp.origin_device_output.signal_name}" if inp.origin_device_output else ''
            writer.writerow([
                inp.get_input_type_display(),
                inp.channel_number,
                inp.label,
                origin_device,
                origin_output
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
            input_data = {
                'type': inp.input_type,
                'type_display': inp.get_input_type_display(),
                'channel': inp.channel_number,
                'label': inp.label
            }
            
            if inp.origin_device_output:
                input_data['origin'] = {
                    'device': inp.origin_device_output.device.name,
                    'output_number': inp.origin_device_output.output_number,
                    'signal_name': inp.origin_device_output.signal_name
                }
            
            export_data['inputs'].append(input_data)
        
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
    'sessions__mic_assignments__presenter_slots__presenter',
    'sessions__mic_assignments__group',
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
            if field in ('presenter', 'presenter_name'):
                if value:
                    presenter, _ = Presenter.objects.get_or_create(
                        name=value.strip(), project_id=current_project_id
                    )
                    slot.presenter = presenter
                else:
                    slot.presenter = None
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
            else:
                setattr(slot, field, value)
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
    
    context = {
        'plan': plan,
        'amplifier_profiles': amplifier_profiles,
        'assignments': assignments,
        'phase_loads': phase_loads,
        'duty_cycles': AmplifierAssignment.DUTY_CYCLES,
        'service_types': PowerDistributionPlan.SERVICE_TYPES,
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
        
        # Get updated phase distribution
        phase_loads = calculate_phase_distribution(plan)
        
        return JsonResponse({
            'success': True,
            'phase_loads': phase_loads,
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
        'locations': Location.objects.count(),
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
        location = get_object_or_404(Location, id=data['location_id'])
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
    """Move a divider up or down"""
    try:
        data = request.POST
        divider = get_object_or_404(AmpDivider, id=divider_id)
        direction = data.get('direction')
        location_items = get_location_items(divider.location, divider.project)
        idx = next((i for i, item in enumerate(location_items) if item.get('type') == 'divider' and item['obj'].id == divider.id), None)
        if idx is None:
            return JsonResponse({'success': False, 'error': 'Divider not found'})
        if direction == 'up' and idx > 0:
            swap_idx = idx - 1
        elif direction == 'down' and idx < len(location_items) - 1:
            swap_idx = idx + 1
        else:
            return JsonResponse({'success': False, 'error': 'Cannot move'})
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
        location = get_object_or_404(Location, id=request.POST.get('location_id'))
        project = get_object_or_404(Project, id=request.POST.get('project_id'))
        dividers_data = json.loads(request.POST.get('dividers', '[]'))
        
        # Get existing dividers for this location
        existing = {d.id: d for d in AmpDivider.objects.filter(location=location, project=project)}
        seen_ids = set()
        
        result = []
        for i, d in enumerate(dividers_data):
            db_id = d.get('id')
            if db_id and db_id in existing:
                # Update existing
                div = existing[db_id]
                div.label = d.get('label', '')
                div.sort_order = i
                div.save()
                seen_ids.add(db_id)
            else:
                # Create new
                div = AmpDivider.objects.create(
                    location=location, project=project,
                    label=d.get('label', ''), sort_order=i
                )
                seen_ids.add(div.id)
            result.append({'db_id': div.id, 'sort_order': i})
        
        # Delete removed dividers
        for did, div in existing.items():
            if did not in seen_ids:
                div.delete()
        
        return JsonResponse({'success': True, 'dividers': result})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

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
    buf = generate_ip_address_report_pdf()
    
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
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="IP_Address_Report.csv"'
    
    writer = csv.writer(response)
    
    # ==================== MIXING CONSOLES ====================
    writer.writerow(['MIXING CONSOLES'])
    writer.writerow(['Console Name', 'Primary IP Address', 'Secondary IP Address'])
    
    consoles = Console.objects.all().order_by('name')
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
    
    devices = Device.objects.all().order_by('name')
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
    
    amps = Amp.objects.all().order_by('location__name', 'name')
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
    
    processors = SystemProcessor.objects.all().order_by('device_type', 'name')
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
    
    # ==================== COMM BELT PACKS (HARDWIRED) ====================
    writer.writerow(['COMM BELT PACKS (HARDWIRED)'])
    writer.writerow(['BP #', 'Position', 'Name', 'IP Address'])
    
    belt_packs = CommBeltPack.objects.filter(system_type='HARDWIRED').order_by('bp_number')
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

        config = CommConfig.objects.create(
            project=current_project,
            name=f"New {device_type.title()} Config",
            device_type=device_type,
        )

        # Seed factory defaults
        _seed_factory_defaults(config)

        return JsonResponse({'ok': True, 'config_id': config.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
    role_defaults = [
        (1,  'FSII-BP', 'BP 1',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (2,  'FSII-BP', 'BP 2',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (3,  'FSII-BP', 'BP 3',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (4,  'FSII-BP', 'BP 4',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (5,  'FSII-BP', 'BP 5',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (6,  'FSII-BP', 'BP 6',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (7,  'FSII-BP', 'BP 7',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (8,  'FSII-BP', 'BP 8',      False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        # V-Series
        (9,  'V12',     'V12 Panel', False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (10, 'V24',     'V24 Panel', False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (11, 'V32',     'V32 Panel', False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        (12, 'V12D',    'V12D Panel',False, [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
        # Arcadia station
        (13, 'NEP',     'Station',   True,  [(0,1,'talkforcelisten','latching'),(1,2,'talkforcelisten','latching'),(2,3,'talkforcelisten','latching'),(3,4,'talkforcelisten','latching')]),
    ]

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
            if value:
                key.partyline = CommConfigPartyline.objects.get(id=value)
                key.entity_type = 0
            else:
                key.partyline = None
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
        for i in range(role.max_keysets):
            CommConfigKeyset.objects.create(
                role=role,
                key_index=i,
                activation_state='talkforcelisten',
                talk_mode='latching',
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
    import json, os, tarfile, gzip, tempfile, shutil
    from django.http import HttpResponse
    from django.conf import settings

    config = get_object_or_404(CommConfig, id=config_id)

    # Load factory docs as base
    factory_path = os.path.join(settings.BASE_DIR, 'planner', 'static', 'comm_config', 'arcadia_factory_docs.json')
    with open(factory_path) as f:
        docs = json.load(f)

    sys_id = config.system_id or 'ShowStack'
    hw_id = config.hardware_id or 'ff080f1f'
    owner_id = f'0.02.{sys_id}.0000.0000'

    def make_rev():
        import uuid
        return f'1-{uuid.uuid4().hex}'

    # ── Remove old system_id docs (keep hardware/layer docs) ──
    old_sys_ids = set()
    for doc_id in list(docs.keys()):
        parts = doc_id.split('.')
        if len(parts) >= 3 and parts[2] not in (hw_id, '!', 'A6AMk7Ur'):
            old_sys_ids.add(parts[2])

    for doc_id in list(docs.keys()):
        parts = doc_id.split('.')
        if len(parts) >= 3 and parts[2] in old_sys_ids:
            del docs[doc_id]

    # ── Build partyline docs ──
    partylines = list(config.partylines.all().order_by('channel_number'))
    pl_id_map = {}  # channel_number -> doc_id
    for pl in partylines:
        doc_id = f'3.20.{sys_id}.0000.{pl.channel_number:04d}'
        pl_id_map[pl.channel_number] = doc_id
        docs[doc_id] = {
            '_id': doc_id,
            '_rev': make_rev(),
            'data': {
                'helixnetEnabled': pl.helixnet_enabled,
                'id': pl.channel_number,
                'label': pl.label,
                'type': 'partyline',
            },
            'owner': owner_id,
            'type': 'partyline',
        }

    # ── Build role docs ──
    roles = list(config.roles.all().order_by('role_number'))
    role_id_map = {}  # role_number -> doc_id
    for role in roles:
        doc_id = f'3.23.{sys_id}.0000.{role.role_number:04d}'
        role_id_map[role.role_number] = doc_id

        # Build keysets
        keysets = []
        for key in role.keysets.all().order_by('key_index'):
            entities = []
            if key.partyline:
                entities.append({
                    'res': f'/api/1/connections/{key.partyline.channel_number}',
                    'type': 0,
                })
            elif key.port_reference:
                entities.append({
                    'res': key.port_reference,
                    'type': 1,
                })

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

        # Build settings based on device type
        settings_obj = {
            'displayBrightness': role.display_brightness,
            'headphoneGain': role.headphone_gain,
            'headphoneLimit': role.headphone_limit,
            'keysets': keysets,
            'masterVolume': role.master_volume,
            'micType': role.mic_type,
            'sidetoneControl': role.sidetone_control,
            'sidetoneGain': role.sidetone_gain,
        }
        # Merge any extended settings
        if role.extended_settings:
            settings_obj.update(role.extended_settings)

        docs[doc_id] = {
            '_id': doc_id,
            '_rev': make_rev(),
            'data': {
                'description': role.description or '',
                'id': role.role_number,
                'isDefault': role.is_default,
                'label': role.label,
                'settings': settings_obj,
                'type': role.device_type,
            },
            'owner': owner_id,
            'type': role.device_type,
        }

    # ── Build roleset docs ──
    rolesets = list(config.rolesets.all().order_by('roleset_number'))
    rs_id_map = {}  # roleset_number -> doc_id
    for rs in rolesets:
        doc_id = f'3.88.{sys_id}.0000.{rs.roleset_number:04d}'
        rs_id_map[rs.roleset_number] = doc_id
        docs[doc_id] = {
            '_id': doc_id,
            '_rev': make_rev(),
            'data': {
                'addressable': rs.addressable,
                'dpId': rs.roleset_number,
                'id': rs.roleset_number,
                'label': rs.label,
                'name': rs.label,
                'type': 'Roleset',
            },
            'owner': owner_id,
            'type': 'Roleset',
        }

        # Dynamic port ref for this roleset
        dp_id = f'4.55.{sys_id}.0000.{rs.roleset_number:04d}'
        docs[dp_id] = {
            '_id': dp_id,
            '_rev': make_rev(),
            'data': {
                'destination': doc_id,
                'id': rs.roleset_number,
                'type': 'roleset',
            },
            'owner': owner_id,
            'type': 'roleset',
        }

    # ── Build session docs ──
    for session in config.sessions.all().order_by('session_type'):
        if session.session_type == 'A.CCM':
            doc_id = f'3.99.{sys_id}.0000.0000'
            session_data = {
                'id': 0,
                'label': session.label,
                'profile': {'role': 'admin'},
                'type': session.session_type,
            }
            owner = f'0.99.A6AMk7Ur.0000.0000'
        else:
            # Owner is the roleset doc
            rs_num = session.roleset.roleset_number if session.roleset else 0
            rs_hex = f'{rs_num:04d}'
            doc_id = f'3.99.{sys_id}.{rs_hex}.0000'
            session_data = {
                'addressable': session.addressable,
                'id': 0,
                'label': session.label,
                'settings': {
                    'defaultRole': session.default_role.role_number if session.default_role else 1,
                },
                'type': session.session_type,
            }
            rs_doc_id = rs_id_map.get(rs_num, f'3.88.{sys_id}.0000.0001')
            owner = rs_doc_id

        docs[doc_id] = {
            '_id': doc_id,
            '_rev': make_rev(),
            'data': session_data,
            'owner': owner,
            'type': session.session_type,
        }

    # ── Update physical port settings ──
    for port in config.port_assignments.all():
        # Find matching factory port doc by label
        for doc_id, doc in docs.items():
            if doc_id.startswith('3.06.') and doc.get('data', {}).get('label') == port.port_label:
                if port.port_type == '2W':
                    doc['data']['settings'].update({
                        'joinMode': port.join_mode,
                        'termination': port.termination_enabled,
                    })
                elif port.port_type == '4W':
                    doc['data']['settings'].update({
                        'joinMode': port.join_mode,
                    })
                break

    # ── Build assignment docs (port to partyline) ──
    for port in config.port_assignments.filter(partyline__isnull=False):
        # Find port doc to get its gid
        for doc_id, doc in list(docs.items()):
            if doc_id.startswith('3.06.') and doc.get('data', {}).get('label') == port.port_label:
                port_parts = doc_id.split('.')
                if len(port_parts) >= 5:
                    assign_id = f'4.44.{sys_id}.{port_parts[3]}.{port_parts[4]}'
                    pl_ch = port.partyline.channel_number
                    pl_doc_id = pl_id_map.get(pl_ch, '')
                    docs[assign_id] = {
                        '_id': assign_id,
                        '_rev': make_rev(),
                        'data': {
                            'joinMode': port.join_mode,
                            'source': doc_id,
                            'destination': pl_doc_id,
                        },
                        'owner': pl_doc_id,
                        'type': 'assignment',
                    }
                break

    # ── Write LevelDB and pack .cca ──
    tmp_dir = tempfile.mkdtemp()
    try:
        import plyvel
        db_path = os.path.join(tmp_dir, 'pouchdb')
        db = plyvel.DB(db_path, create_if_missing=True)

        seq = 0
        for doc_id, doc in sorted(docs.items()):
            seq += 1
            seq_key = f'ÿby-sequenceÿ{seq:016d}'.encode()
            content_bytes = json.dumps(doc).encode('utf-8')
            db.put(seq_key, b'' + content_bytes)
            db.put(f'ÿmeta-storeÿ{doc_id}'.encode(), str(seq).encode())

        db.put(b'\xff' + b'meta-store' + b'\xff' + b'_local_doc_count', str(len(docs)).encode())
        db.put(b'\xff' + b'meta-store' + b'\xff' + b'_local_last_update_seq', str(seq).encode())
        db.close()

        # Write support files
        with open(os.path.join(tmp_dir, 'type.txt'), 'w') as f:
            f.write('NEP-ARCADIA')
        from datetime import datetime, timezone
        with open(os.path.join(tmp_dir, 'datetime.txt'), 'w') as f:
            f.write(datetime.now(timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y'))
        with open(os.path.join(tmp_dir, 'SystemEnvironment.json'), 'w') as f:
            json.dump({'system': sys_id, 'domain': sys_id, 'context': 'device'}, f)

        # Create tar
        tar_path = os.path.join(tmp_dir, 'config.tar')
        with tarfile.open(tar_path, 'w') as tar:
            for item in ['pouchdb', 'datetime.txt', 'type.txt', 'SystemEnvironment.json']:
                tar.add(os.path.join(tmp_dir, item), arcname=item)

        # Gzip
        cca_bytes = b''
        with open(tar_path, 'rb') as f_in:
            import io
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9) as gz:
                gz.write(f_in.read())
            cca_bytes = buf.getvalue()

        filename = f'{config.name.replace(" ", "_")}_{sys_id}.cca'
        response = HttpResponse(cca_bytes, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except ImportError:
        return HttpResponse('plyvel not installed on this server.', status=501)
    except Exception as e:
        return HttpResponse(f'Export error: {str(e)}', status=500)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

  







  #----Temporaty debug




  # Add this to planner/views.py temporarily

from django.http import HttpResponse
from planner.models import Device

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
