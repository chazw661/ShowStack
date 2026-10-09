"""Which photo a Mic Tracker slot shows, answered without loading any image.

The photo belongs to the Presenter (PresenterPhoto), so a slot shows its
presenter's headshot -- in every session that presenter is in.

Until ``manage.py migrate_slot_photos_to_presenters --apply`` has run, most
headshots still live only in the old per-slot ``PresenterSlot.photo_data``
column. So a slot whose presenter has no headshot falls back to its own legacy
photo, served from a scoped URL rather than inlined. That fallback, the legacy
endpoint and the column all go in the follow-up that drops ``photo_data``.

Two queries per project, neither of which transfers image bytes:
  * presenter id -> headshot hash, for the versioned URL
  * ids of slots holding a legacy photo (``photo_data <> ''`` is answered from
    the TOAST length header in Postgres; the value is not read)
"""

from django.urls import reverse


def headshot_url(presenter_id, sha256):
    return reverse('planner:presenter_photo', args=[presenter_id]) + f'?v={sha256[:12]}'


def legacy_slot_photo_url(slot_id):
    return reverse('planner:legacy_slot_photo', args=[slot_id])


class PhotoIndex:
    """Photo URLs for the slots of one project (optionally a subset)."""

    def __init__(self, project_id, slot_ids=None):
        from planner.models import PresenterPhoto, PresenterSlot

        self.urls = {
            pid: headshot_url(pid, sha)
            for pid, sha in PresenterPhoto.objects.filter(
                presenter__project_id=project_id,
            ).values_list('presenter_id', 'sha256')
        }
        legacy = (PresenterSlot.objects
                  .filter(assignment__session__day__project_id=project_id)
                  .exclude(photo_data__isnull=True).exclude(photo_data=''))
        if slot_ids is not None:
            legacy = legacy.filter(id__in=list(slot_ids))
        self.legacy = set(legacy.values_list('id', flat=True))

    def for_slot(self, slot):
        if slot is None:
            return ''
        url = self.urls.get(slot.presenter_id)
        if url:
            return url
        if slot.pk in self.legacy:
            return legacy_slot_photo_url(slot.pk)
        return ''


def photo_url_for_slot(slot):
    """One slot's photo URL -- for the JSON endpoints that return a single slot."""
    if slot is None:
        return ''
    project_id = slot.assignment.session.day.project_id
    return PhotoIndex(project_id, slot_ids=[slot.pk]).for_slot(slot)
