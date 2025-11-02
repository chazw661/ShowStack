from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Create initial superuser if none exists'

    def handle(self, *args, **options):
        User = get_user_model()
        
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(self.style.WARNING('Superuser already exists'))
            return
        
        # Create superuser - CHANGE THESE VALUES!
        User.objects.create_superuser(
            username='charlielaw',
            email='lawsonsounddesign@gmail.com',
            password='AudioPatch123!'  # CHANGE THIS!
        )
        
        self.stdout.write(self.style.SUCCESS('Superuser created successfully'))
