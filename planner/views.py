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
