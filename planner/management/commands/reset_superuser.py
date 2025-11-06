from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Create or reset superuser account'

    def handle(self, *args, **options):
        User = get_user_model()
        
        username = 'charlielawson'
        email = 'lawsonsounddesign@gmail.com'
        password = 'NewPassword2025!'  # CHANGE THIS!
        
        try:
            user = User.objects.get(username=username)
            user.set_password(password)
            user.email = email
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" password reset'))
        except User.DoesNotExist:
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created'))
