from django.db import IntegrityError
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import (
    UserProfile,
    ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput,
    MicSession, MicAssignment,
)


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


# ──────────────────────────────────────────────────────────────────
# Multitrack orphan-conversion (CONTEXT.md D-04)
# When a channel row is deleted, every MultitrackTrack referencing it
# is converted to source_type='manual' with a snapshot of the channel's
# label/color so the engineer never silently loses a track row.
# ──────────────────────────────────────────────────────────────────

def _convert_orphans_to_manual(source_type, source_id, snapshot_label, snapshot_color=''):
    """D-04: Convert orphan MultitrackTracks to manual on channel deletion.

    Local import of MultitrackTrack avoids the circular-import path
    (signals -> models -> apps -> signals).
    """
    from .models import MultitrackTrack  # local import per RESEARCH note
    orphans = MultitrackTrack.objects.filter(
        source_type=source_type, source_id=source_id
    )
    for track in orphans:
        track.label_override = track.label_override or (snapshot_label or '')
        track.color_override = track.color_override or (snapshot_color or '')
        track.source_type = 'manual'
        track.source_id = None
        track.save(update_fields=[
            'label_override', 'color_override', 'source_type', 'source_id',
        ])


@receiver(post_delete, sender=ConsoleInput)
def consoleinput_to_manual(sender, instance, **kwargs):
    label = (
        instance.source
        or instance.input_ch
        or (f'Input {instance.dante_number}' if instance.dante_number else None)
        or '(deleted input)'
    )
    _convert_orphans_to_manual('input', instance.pk, label)


@receiver(post_delete, sender=ConsoleAuxOutput)
def consoleauxoutput_to_manual(sender, instance, **kwargs):
    # Explicit branches — `name or f'Aux {n}' or sentinel` always picked the
    # f-string (always non-empty, even when aux_number is None or 0), so the
    # sentinel fallback was unreachable (WR-05).
    if instance.name:
        label = instance.name
    elif instance.aux_number:
        label = f'Aux {instance.aux_number}'
    else:
        label = '(deleted aux)'
    _convert_orphans_to_manual('aux', instance.pk, label)


@receiver(post_delete, sender=ConsoleMatrixOutput)
def consolematrixoutput_to_manual(sender, instance, **kwargs):
    if instance.name:
        label = instance.name
    elif instance.matrix_number:
        label = f'Matrix {instance.matrix_number}'
    else:
        label = '(deleted matrix)'
    _convert_orphans_to_manual('matrix', instance.pk, label)


@receiver(post_delete, sender=MicAssignment)
def renumber_mic_assignments_after_delete(sender, instance, **kwargs):
    """Issue #36: keep MicAssignment.rf_number consecutive 1..N after any
    delete. Uses filter(...).first() so cascade-from-session deletes (where
    the session is gone) no-op silently instead of raising DoesNotExist."""
    session = MicSession.objects.filter(pk=instance.session_id).first()
    if session is not None:
        session.renumber_assignments()


@receiver(post_delete, sender=ConsoleStereoOutput)
def consolestereooutput_to_manual(sender, instance, **kwargs):
    if instance.name:
        label = instance.name
    else:
        # get_stereo_type_display() always returns a string for valid choices
        # but may be empty/None for unset stereo_type — fall back to sentinel.
        display = instance.get_stereo_type_display() if instance.stereo_type else ''
        label = display or '(deleted stereo)'
    _convert_orphans_to_manual('stereo', instance.pk, label)