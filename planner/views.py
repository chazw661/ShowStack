from django.shortcuts import render, get_object_or_404
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
from .models import MicAssignment
import json
import csv


# Model imports - all together
from .models import (
    Console, ConsoleInput,
    GalaxyProcessor, GalaxyInput, GalaxyOutput,
    P1Processor, P1Input, P1Output,
    CommBeltPack, CommChannel, CommPosition, CommCrewName,
    Device, SystemProcessor, Amp, PACableSchedule,
    ShowDay, MicSession, MicAssignment, MicShowInfo
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
    




    # Add to your views.py









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
    from django.shortcuts import render
    
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
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import (Console, Device, SystemProcessor, CommBeltPack, 
                     CommPosition, Amp, PACableSchedule)

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
        'sessions__mic_assignments'
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

@staff_member_required
@require_POST
def toggle_day_collapse(request):
    """AJAX endpoint to toggle day collapse state"""
    try:
        data = json.loads(request.body)
        day_id = data.get('day_id')
        
        day = get_object_or_404(ShowDay, id=day_id)
        day.is_collapsed = not day.is_collapsed
        day.save()
        
        return JsonResponse({
            'success': True,
            'is_collapsed': day.is_collapsed
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

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
                writer.writerow([
                    assignment.rf_number,
                    assignment.mic_type,
                    assignment.display_presenters,
                    'Yes' if assignment.is_micd else 'No',
                    'Yes' if assignment.is_d_mic else 'No',
                    assignment.notes
                ])
            
            writer.writerow([])
    
    return response



@staff_member_required
def dashboard_view(request):
    """Simple dashboard view function"""
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





@csrf_exempt  # Add this decorator
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
        if field == 'presenter_name':
            assignment.presenter_name = value
        elif field == 'mic_type':
            assignment.mic_type = value
        elif field == 'is_micd':
            assignment.is_micd = value if isinstance(value, bool) else value == 'true'
        elif field == 'is_d_mic':
            assignment.is_d_mic = value if isinstance(value, bool) else value == 'true'
        elif field == 'shared_presenters':
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except:
                    pass
            assignment.shared_presenters = value
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
            'shared': session.mic_assignments.exclude(shared_presenters__isnull=True).exclude(shared_presenters=[]).count()
        }
        
        return JsonResponse({
            'success': True,
            'session_stats': session_stats,
            'presenter_display': assignment.display_presenters,
            'presenter_count': assignment.presenter_count,
            'day_stats': {}  # Add day stats if needed
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

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

