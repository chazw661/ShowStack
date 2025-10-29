"""
Management command to create and configure Editor and Viewer permission groups.

Run with: python manage.py setup_user_groups
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Creates Editor and Viewer permission groups for ShowStack'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up user groups...'))
        
        # Create or get groups
        editor_group, created = Group.objects.get_or_create(name='Editor')
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created Editor group'))
        else:
            self.stdout.write('  Editor group already exists')
        
        viewer_group, created = Group.objects.get_or_create(name='Viewer')
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created Viewer group'))
        else:
            self.stdout.write('  Viewer group already exists')
        
        # Get all equipment models from planner app
        equipment_models = [
            'console', 'consoleinput', 'consoleauxoutput', 'consolematrixoutput',
            'iodevice', 'deviceinput', 'deviceoutput',
            'amplifierassignment', 'ampchannel',
            'systemprocessor', 'p1processor', 'p1input', 'p1output',
            'galaxyprocessor', 'galaxyinput', 'galaxyoutput',
            'pacableschedule', 'pafanout', 'pazone',
            'commsystem', 'commdevice', 'commchannel',
            'mictracking', 'micpackage',
            'powerdistribution', 'powerchannel',
            'soundvisiondata',
            'location', 'amp',
        ]
        
        self.stdout.write('\nConfiguring permissions...')
        
        # Configure Editor permissions (full CRUD)
        editor_permissions = []
        for model_name in equipment_models:
            try:
                content_type = ContentType.objects.get(app_label='planner', model=model_name)
                
                # Add all CRUD permissions for editors
                perms = Permission.objects.filter(content_type=content_type)
                editor_permissions.extend(list(perms))
            except ContentType.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'  Model not found: {model_name}'))
        
        # Clear existing permissions and set new ones
        editor_group.permissions.clear()
        editor_group.permissions.add(*editor_permissions)
        self.stdout.write(self.style.SUCCESS(f'✓ Configured Editor group ({len(editor_permissions)} permissions)'))
        
        # Configure Viewer permissions (view only)
        viewer_permissions = []
        for model_name in equipment_models:
            try:
                content_type = ContentType.objects.get(app_label='planner', model=model_name)
                
                # Add only view permission for viewers
                view_perm = Permission.objects.get(
                    content_type=content_type,
                    codename=f'view_{model_name}'
                )
                viewer_permissions.append(view_perm)
            except (ContentType.DoesNotExist, Permission.DoesNotExist):
                self.stdout.write(self.style.WARNING(f'  View permission not found: {model_name}'))
        
        # Clear existing permissions and set new ones
        viewer_group.permissions.clear()
        viewer_group.permissions.add(*viewer_permissions)
        self.stdout.write(self.style.SUCCESS(f'✓ Configured Viewer group ({len(viewer_permissions)} permissions)'))
        
        self.stdout.write(self.style.SUCCESS('\n✅ User groups setup complete!'))
        self.stdout.write('\nNext steps:')
        self.stdout.write('1. Groups will be auto-assigned when users accept invitations')
        self.stdout.write('2. Update invitation acceptance logic to assign appropriate group')