# Save this as: planner/management/commands/populate_device_numbers.py

from django.core.management.base import BaseCommand
from planner.models import Device, DeviceInput, DeviceOutput


class Command(BaseCommand):
    help = 'Populate input_number and output_number for all devices where they are None'

    def handle(self, *args, **options):
        self.stdout.write('Starting to populate device input/output numbers...\n')
        
        devices = Device.objects.all()
        total_devices = devices.count()
        
        for idx, device in enumerate(devices, 1):
            self.stdout.write(f'[{idx}/{total_devices}] Processing: {device.name}')
            self.stdout.write(f'  Device expects {device.input_count} inputs, {device.output_count} outputs')
            
            # Fix inputs - number them 1 through input_count (by ID order = creation order)
            inputs = device.inputs.all().order_by('id')
            actual_input_count = inputs.count()
            
            if actual_input_count != device.input_count:
                self.stdout.write(
                    self.style.WARNING(
                        f'  ⚠ WARNING: Device has {actual_input_count} input records but input_count={device.input_count}'
                    )
                )
            
            fixed_inputs = 0
            for position, inp in enumerate(inputs, 1):
                if inp.input_number is None:
                    inp.input_number = position
                    inp.save()
                    fixed_inputs += 1
            
            # Fix outputs - number them 1 through output_count (by ID order = creation order)
            outputs = device.outputs.all().order_by('id')
            actual_output_count = outputs.count()
            
            if actual_output_count != device.output_count:
                self.stdout.write(
                    self.style.WARNING(
                        f'  ⚠ WARNING: Device has {actual_output_count} output records but output_count={device.output_count}'
                    )
                )
            
            fixed_outputs = 0
            for position, out in enumerate(outputs, 1):
                if out.output_number is None:
                    out.output_number = position
                    out.save()
                    fixed_outputs += 1
            
            if fixed_inputs > 0 or fixed_outputs > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Fixed {fixed_inputs} inputs, {fixed_outputs} outputs'
                    )
                )
            else:
                self.stdout.write('  - Already numbered')
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ Successfully processed {total_devices} devices!'))