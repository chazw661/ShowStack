from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """
    Ensure UserProfile exists for every user.
    Uses try/except to handle race conditions when Django admin
    saves the User object multiple times during creation.
    """
    try:
        # Try to get existing profile
        profile = UserProfile.objects.get(user=instance)
    except UserProfile.DoesNotExist:
        # Profile doesn't exist, try to create it
        try:
            profile = UserProfile.objects.create(
                user=instance,
                account_type='free',
                can_create_projects=False
            )
        except IntegrityError:
            # Another signal fired first and created it - just fetch it
            profile = UserProfile.objects.get(user=instance)