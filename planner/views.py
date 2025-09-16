from django.shortcuts import render, get_object_or_404
from django.forms import modelformset_factory
from .models import Console, ConsoleInput

from .models import GalaxyProcessor, GalaxyInput, GalaxyOutput

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

from django.shortcuts import render, get_object_or_404
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
import json
import csv

from .models import Console, ConsoleInput, P1Processor, P1Input, P1Output


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

from django.http import JsonResponse, HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Max
import csv
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