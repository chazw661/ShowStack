import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audiopatch.settings')
django.setup()

from planner.models import GalaxyProcessor, GalaxyInput, GalaxyOutput

galaxy = GalaxyProcessor.objects.first()

if galaxy:
    # Clear any partial data first
    galaxy.inputs.all().delete()
    galaxy.outputs.all().delete()
    
    print(f"Creating channels for: {galaxy}")
    
    # Create ALL inputs
    # 8 Analog
    for i in range(1, 9):
        GalaxyInput.objects.create(
            galaxy_processor=galaxy,
            input_type='ANALOG',
            channel_number=i,
            label=''
        )
    print("Created 8 Analog inputs")
    
    # 8 AES
    for i in range(1, 9):
        GalaxyInput.objects.create(
            galaxy_processor=galaxy,
            input_type='AES',
            channel_number=i,
            label=''
        )
    print("Created 8 AES inputs")
    
    # 16 AVB
    for i in range(1, 17):
        GalaxyInput.objects.create(
            galaxy_processor=galaxy,
            input_type='AVB',
            channel_number=i,
            label=''
        )
    print("Created 16 AVB inputs")
    
    # Create ALL outputs
    # 8 Analog
    for i in range(1, 9):
        GalaxyOutput.objects.create(
            galaxy_processor=galaxy,
            output_type='ANALOG',
            channel_number=i,
            label='',
            destination=''
        )
    print("Created 8 Analog outputs")
    
    # 8 AES
    for i in range(1, 9):
        GalaxyOutput.objects.create(
            galaxy_processor=galaxy,
            output_type='AES',
            channel_number=i,
            label='',
            destination=''
        )
    print("Created 8 AES outputs")
    
    # 16 AVB
    for i in range(1, 17):
        GalaxyOutput.objects.create(
            galaxy_processor=galaxy,
            output_type='AVB',
            channel_number=i,
            label='',
            destination=''
        )
    print("Created 16 AVB outputs")
    
    print("\nFinal totals:")
    print(f"Inputs: {galaxy.inputs.count()} (should be 32)")
    print(f"Outputs: {galaxy.outputs.count()} (should be 32)")
else:
    print("No GALAXY processor found!")
