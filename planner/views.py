from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
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


# Model imports - all together
from .models import (
    Console, ConsoleInput,
    GalaxyProcessor, GalaxyInput, GalaxyOutput,
    P1Processor, P1Input, P1Output,
    CommBeltPack, CommChannel, CommPosition, CommCrewName,
    Device, Device, SystemProcessor, Amp, Location, PACableSchedule, PAZone,
    ShowDay, MicSession, MicAssignment, MicShowInfo, PowerDistributionPlan, AmplifierProfile, 
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

    consoles = Console.objects.all()

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

    from .models import ShowDay, MicSession, MicAssignment, MicShowInfo

@staff_member_required
def mic_tracker_view(request):
    """Main mic tracker view with spreadsheet-like interface"""
    
    # Get filter parameters
    day_id = request.GET.get('day')
    session_id = request.GET.get('session')
    date_filter = request.GET.get('date')
    
    # Get show info
    show_info = MicShowInfo.get_instance()
    
    # Build queryset
    if day_id:
        days = ShowDay.objects.filter(id=day_id)
    elif date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            days = ShowDay.objects.filter(date=filter_date)
        except ValueError:
            days = ShowDay.objects.all()
    else:
        days = ShowDay.objects.all()
    
    days = days.prefetch_related(
    'sessions__mic_assignments__presenter',
    'sessions__mic_assignments__shared_presenters'
    ).order_by('date')
    

    # Organize sessions by columns for display

    days_data = []
    for day in days:
        all_sessions = list(day.sessions.all().order_by('order', 'start_time'))
        
        days_data.append({
            'day': day,
            'sessions': all_sessions,  # Just pass all sessions as a flat list
        })

        # This is inside the mic_tracker_view function
        context = {
            'show_info': show_info,
            'days_data': days_data,
            'current_date': date.today(),
            'mic_types': MicAssignment.MIC_TYPES,
            'session_types': MicSession.SESSION_TYPES,
    }   # <-- This closing brace needs to be indented with 4 spaces, not at column 0
            
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
    show_info = MicShowInfo.get_instance()
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
        
        # Handle different field types
        if field == 'presenter' or field == 'presenter_name':  # Support both for compatibility
            # Value should be a presenter ID or name
            if value:
                # Try to get existing presenter or create new one
                presenter, created = Presenter.objects.get_or_create(name=value.strip())
                assignment.presenter = presenter
            else:
                assignment.presenter = None
                
        elif field == 'mic_type':
            assignment.mic_type = value
            
        elif field == 'is_micd':
            assignment.is_micd = value if isinstance(value, bool) else value == 'true'
            
        elif field == 'is_d_mic':
            assignment.is_d_mic = value if isinstance(value, bool) else value == 'true'
            
        elif field == 'notes':
            assignment.notes = value
            
        else:
            return JsonResponse({
                'success': False,
                'error': f'Unknown field: {field}'
            }, status=400)
        
        assignment.save()
        
        # Get updated stats
        session = assignment.session
        session_stats = {
            'micd': session.mic_assignments.filter(is_micd=True).count(),
            'total': session.mic_assignments.count(),
            'shared': session.mic_assignments.filter(shared_presenters__isnull=False).distinct().count()
        }
        
        return JsonResponse({
            'success': True,
            'session_stats': session_stats,
            'presenter_display': assignment.display_presenters,
            'presenter_count': assignment.presenter_count,
            'day_stats': {}
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


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
        
        # Get or create the presenter
        presenter, created = Presenter.objects.get_or_create(name=presenter_name)
        
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
        
        # Find the presenter by name
        try:
            presenter = Presenter.objects.get(name__iexact=presenter_name)
        except Presenter.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Presenter "{presenter_name}" not found'
            })
        
        # Check if presenter is in shared list
        if not assignment.shared_presenters.filter(id=presenter.id).exists():
            return JsonResponse({
                'success': False,
                'error': f'"{presenter_name}" is not in the shared presenters list'
            })
        
        # Remove the presenter
        assignment.shared_presenters.remove(presenter)
        
        # Adjust active_presenter_index if needed
        if assignment.active_presenter_index > assignment.shared_presenters.count():
            assignment.active_presenter_index = 0
            assignment.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Removed {presenter_name} from shared presenters',
            'shared_count': assignment.shared_presenters.count(),
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
    
 # ============================================
# Shared Presenter Management Views
# ============================================


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
        
        # Ensure shared_presenters is a list
        if not isinstance(assignment.shared_presenters, list):
            return JsonResponse({
                'success': False,
                'error': 'No shared presenters to remove'
            })
        
        if len(assignment.shared_presenters) == 0:
            return JsonResponse({
                'success': False,
                'error': 'Shared presenters list is empty'
            })
        
        # Find matching presenter (case-insensitive)
        presenter_to_remove = None
        for presenter in assignment.shared_presenters:
            if presenter.lower() == presenter_name.lower():
                presenter_to_remove = presenter
                break
        
        if presenter_to_remove is None:
            return JsonResponse({
                'success': False,
                'error': f'"{presenter_name}" not found in shared presenters list'
            })
        
        # Remove the presenter (using the exact match from the list)
        assignment.shared_presenters.remove(presenter_to_remove)
        
        # Adjust active_presenter_index if needed
        if assignment.active_presenter_index > len(assignment.shared_presenters):
            assignment.active_presenter_index = 0
        
        assignment.save()
        
        # Get the current presenter - try as property first, then as method
        try:
            current_pres = assignment.current_presenter() if callable(assignment.current_presenter) else assignment.current_presenter
        except:
            current_pres = assignment.presenter_name  # Fallback to main presenter
        
        return JsonResponse({
            'success': True,
            'message': f'Removed {presenter_to_remove} from shared presenters',
            'shared_count': len(assignment.shared_presenters),
            'shared_presenters': assignment.shared_presenters,
            'current_presenter': current_pres  # FIXED: no longer assumes it's a method
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
    
    #---Dropdown for presenters---
@staff_member_required
def get_presenters_list(request):
    """Return all presenters for autocomplete"""
    presenters = Presenter.objects.all().order_by('name').values('id', 'name')
    return JsonResponse({'presenters': list(presenters)})



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
    
    # Balance auto assignments
    for assignment in sorted(auto_assignments, 
                           key=lambda x: x.calculated_total_current or 0, 
                           reverse=True):
        # Find phase with lowest load
        min_phase = min(phases.keys(), key=lambda x: phases[x]['total_current'])
        
        # Assign to that phase
        assignment.phase_assignment = min_phase
        assignment.save(update_fields=['phase_assignment'])
        
        phases[min_phase]['assignments'].append(assignment)
        phases[min_phase]['total_current'] += float(
            assignment.calculated_total_current or 0
        )
    
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

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
import json

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

def prediction_detail(request, pk):
    """Display detailed prediction with collapsible arrays grouped by base name"""
    prediction = get_object_or_404(SoundvisionPrediction, pk=pk)
    
    # Group arrays by their base name
    grouped_arrays = defaultdict(list)
    total_weight = Decimal('0')
    total_arrays = 0
    
    for array in prediction.speaker_arrays.all().order_by('array_base_name', 'position_x'):
        grouped_arrays[array.array_base_name].append(array)
        if array.total_weight_lb:
            total_weight += array.total_weight_lb
        total_arrays += 1
    
    # Sort the groups by name
    grouped_arrays = dict(sorted(grouped_arrays.items()))
    
    context = {
        'prediction': prediction,
        'grouped_arrays': grouped_arrays,
        'total_weight': total_weight,
        'total_arrays': total_arrays,
        'array_count': len(grouped_arrays),
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
                if cab.angle_to_next:
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
    
    # Get all records with IP addresses
    consoles = Console.objects.all().order_by('name')
    devices = Device.objects.all().order_by('name')
    amps = Amp.objects.all().order_by('location__name', 'name')
    processors = SystemProcessor.objects.all().order_by('device_type', 'name')
    belt_packs = CommBeltPack.objects.filter(system_type='HARDWIRED').order_by('bp_number')
    
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
def device_pdf_export(request, device_id):
    """Export a single Device as PDF"""
    from planner.models import Device
    from planner.utils.pdf_exports.device_pdf import export_device_pdf
    
    device = Device.objects.get(id=device_id)
    return export_device_pdf(device)


def all_devices_pdf_export(request):
    """Export ALL Devices as PDF (one device per page)"""
    from planner.utils.pdf_exports.device_pdf import export_all_devices_pdf
    
    return export_all_devices_pdf()





#-------Amplifier PDF Export----

# Amplifier PDF Export
def all_amps_pdf_export(request):
    """Export ALL Amplifiers as PDF (grouped by location, ordered by IP)"""
    from planner.utils.pdf_exports.amplifier_pdf import export_all_amps_pdf
    
    return export_all_amps_pdf()




#-------PA Schedule PDF-------


def all_pa_cables_pdf_export(request):
    """Export all PA cables to PDF."""
    from .models import PACableSchedule
    from .utils.pdf_exports.pa_cable_pdf import generate_pa_cable_pdf
    
    queryset = PACableSchedule.objects.all()
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
    from planner.models import CommCrewName  # Move import to top
    import csv
    from io import TextIOWrapper
    
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
                    CommCrewName.objects.get_or_create(name=name)
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

"""
Add this function to planner/views.py
"""

def export_system_processor_pdf(request):
    """Export system processors as PDF."""
    from planner.utils.pdf_exports.system_processor_pdf import generate_system_processor_pdf
    
    pdf = generate_system_processor_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="system_processors.pdf"'
    return response



#-------<Mic Tracker Presenters .CSV Import---

@staff_member_required
def import_presenters_csv(request):
    """Import presenters from CSV file"""
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
                    
                    # Get or create presenter
                    presenter, created = Presenter.objects.get_or_create(name=name)
                    
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

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .models import SoundvisionPrediction

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




