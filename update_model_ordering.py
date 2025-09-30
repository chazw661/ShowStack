# planner/management/commands/update_model_ordering.py
# 
# First create the directories if they don't exist:
#   mkdir -p planner/management/commands
#   touch planner/management/__init__.py
#   touch planner/management/commands/__init__.py
#
# Then save this file and run:
#   python manage.py update_model_ordering

from django.core.management.base import BaseCommand
from django.apps import apps
import re
import os
from pathlib import Path

class Command(BaseCommand):
    help = 'Updates model verbose_name_plural with invisible Unicode ordering'

    # Zero-width space character for invisible ordering
    ZWSP = '\u200B'

    # Define the model ordering
    MODEL_CONFIGS = [
        ('Console', '🎛️ Consoles', 1),
        ('Device', '🔌 I/O Devices', 2),
        ('ShowDay', '📅 Show Days', 3),
        ('MicSession', '  ├─ Mic Sessions', 4),
        ('MicAssignment', '  ├─ Mic Assignments', 5),
        ('MicShowInfo', '  └─ Mic Show Information', 6),
        ('CommBeltPack', '📡 Comm Beltpacks', 7),
        ('Location', '  ├─ Comm Locations', 8),
        ('CommPosition', '  ├─ Comm Positions', 9),
        ('CommChannel', '  └─ Comm Channels', 10),
        ('AmplifierAssignment', '🔊 Amplifier Assignments', 11),
        ('PAZone', '  ├─ PA Zones', 12),
        ('AmplifierProfile', '  ├─ Amplifier Profiles', 13),
        ('AmpModel', '  └─ Amp Model Templates', 14),
        ('SystemProcessor', '⚙️ System Processors', 15),
        ('PACableSchedule', '🔌 PA Cable Entries', 16),
        ('PAZonesForCables', '  └─ PA Zones', 17),
        ('SoundvisionPrediction', '🎵 Soundvision Predictions', 18),
        ('SpeakerArray', '  ├─ Speaker Arrays', 19),
        ('SpeakerCabinet', '  └─ Speaker Cabinets', 20),
        ('PowerDistributionPlan', '⚡ Power Distribution Plans', 21),
        ('PowerDistributionDetail', '  └─ Power Distribution Plan', 22),
        ('AudioChecklist', '✅ Audio Checklist', 23),
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )
        parser.add_argument(
            '--file-only',
            action='store_true',
            help='Only update the models.py file, not the running models',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('🎵 Audio Patch System - Model Ordering Updater'))
        self.stdout.write(self.style.SUCCESS('=' * 70))

        dry_run = options['dry_run']
        file_only = options['file_only']

        # First, update the running models in memory (unless file-only mode)
        if not file_only:
            self.update_running_models(dry_run)

        # Then update the models.py file
        self.update_models_file(dry_run)

        if not dry_run:
            self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
            self.stdout.write(self.style.SUCCESS('✅ SUCCESS!'))
            self.stdout.write(self.style.SUCCESS('=' * 70))
            self.stdout.write(self.style.WARNING('\n📋 Next steps:'))
            self.stdout.write('   1. Review the changes in planner/models.py')
            self.stdout.write('   2. Run: python manage.py makemigrations')
            self.stdout.write('   3. Run: python manage.py migrate')
            self.stdout.write('   4. Clear browser cache (Ctrl+F5)')
            self.stdout.write('   5. Restart server: python manage.py runserver')
        else:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes made'))
            self.stdout.write('   Run without --dry-run to apply changes')

    def create_verbose_name_plural(self, text, position):
        """Add invisible Unicode prefix for ordering"""
        prefix = self.ZWSP * position
        return prefix + text

    def update_running_models(self, dry_run):
        """Update the models currently loaded in memory"""
        self.stdout.write('\n📝 Updating running models...')
        
        # Get the planner app
        try:
            planner_app = apps.get_app_config('planner')
        except LookupError:
            self.stdout.write(self.style.ERROR('   ❌ Could not find planner app'))
            return

        updated = []
        for model_name, display_name, position in self.MODEL_CONFIGS:
            try:
                model = planner_app.get_model(model_name)
                new_plural = self.create_verbose_name_plural(display_name, position)
                
                if dry_run:
                    current = model._meta.verbose_name_plural
                    self.stdout.write(f'   Would update {model_name}:')
                    self.stdout.write(f'      From: "{current}"')
                    self.stdout.write(f'      To:   "{display_name}" (with {position} invisible chars)')
                else:
                    model._meta.verbose_name_plural = new_plural
                    updated.append(model_name)
                    self.stdout.write(self.style.SUCCESS(f'   ✅ Updated {model_name}'))
                    
            except LookupError:
                self.stdout.write(f'   ⚠️  Model {model_name} not found')
        
        if updated and not dry_run:
            self.stdout.write(self.style.SUCCESS(f'\n   Updated {len(updated)} models in memory'))

    def update_models_file(self, dry_run):
        """Update the models.py file"""
        self.stdout.write('\n📝 Updating models.py file...')
        
        # Find the models.py file
        models_path = Path('planner/models.py')
        if not models_path.exists():
            self.stdout.write(self.style.ERROR('   ❌ Could not find planner/models.py'))
            return

        # Read the file
        with open(models_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes_made = []

        for model_name, display_name, position in self.MODEL_CONFIGS:
            new_verbose_plural = self.create_verbose_name_plural(display_name, position)
            
            # Pattern to find and update verbose_name_plural
            pattern = rf'(class {model_name}\([^)]+\):.*?class Meta:.*?)(verbose_name_plural\s*=\s*["\'][^"\']*["\'])'
            replacement = rf'\1verbose_name_plural = "{new_verbose_plural}"'
            
            new_content, count = re.subn(
                pattern,
                replacement,
                content,
                count=1,
                flags=re.DOTALL
            )
            
            if count > 0:
                content = new_content
                changes_made.append(f'{model_name}: "{display_name}"')
                if not dry_run:
                    self.stdout.write(self.style.SUCCESS(f'   ✅ Updated {model_name}'))
                else:
                    self.stdout.write(f'   Would update {model_name}')

        if changes_made and not dry_run:
            # Make a backup
            backup_path = models_path.with_suffix('.py.backup')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            self.stdout.write(self.style.SUCCESS(f'\n💾 Backup saved to: {backup_path}'))
            
            # Write the updated content
            with open(models_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.stdout.write(self.style.SUCCESS(f'✅ Updated: {models_path}'))
        elif not changes_made:
            self.stdout.write(self.style.WARNING('   No changes needed in models.py'))