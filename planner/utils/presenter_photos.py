"""Which photo a Mic Tracker slot shows, answered without loading any image.

Two kinds of photo, because a "presenter" is sometimes a person and
sometimes a mic position (HH13, Q&A 2, A2 OS) with a different speaker in
each session:

* a SESSION photo -- ``PresenterSlot.photo_data``, on one slot only;
* a HEADSHOT -- ``PresenterPhoto``, on the presenter, for every session.

The rule, per slot:

1. the slot's session photo, if it has one;
2. else, if the presenter is a person (``is_mic_label`` false), their headshot;
3. else nothing.

So a mic label never shows a headshot, whatever is stored, and flipping
``is_mic_label`` only changes which stored photo is shown -- it deletes none.

Two queries per project, neither of which transfers image bytes:
  * presenter id -> headshot hash, for the versioned URL (people only)
  * slot id -> byte length of its session photo. In Postgres
    ``octet_length`` and ``photo_data <> ''`` are both answered from the
    TOAST header; the value itself is not read.
"""

from django.db.models import Func, IntegerField
from django.urls import reverse


class _ByteLength(Func):
    """Byte length of a text column without reading it (Postgres). The photo
    is base64, so on SQLite, where LENGTH counts characters, it is the same."""
    function = 'OCTET_LENGTH'
    output_field = IntegerField()

    def as_sqlite(self, compiler, connection, **extra):
        return self.as_sql(compiler, connection, function='LENGTH', **extra)


def headshot_url(presenter_id, sha256):
    return reverse('planner:presenter_photo', args=[presenter_id]) + f'?v={sha256[:12]}'


def session_photo_url(slot_id, version):
    """``version`` changes when the stored photo does, so the card's <img>
    src changes and every open tracker re-fetches. It is the byte length --
    readable without reading the photo -- so two different photos of exactly
    the same length would share a URL until the next page load; the response
    is ``no-cache`` with an ETag, so a reload always gets the right one."""
    return reverse('planner:slot_photo', args=[slot_id]) + f'?v={version}'


class PhotoIndex:
    """Photo URLs for the slots of one project (optionally a subset)."""

    def __init__(self, project_id, slot_ids=None):
        from planner.models import PresenterPhoto, PresenterSlot

        self.headshots = {
            pid: headshot_url(pid, sha)
            for pid, sha in PresenterPhoto.objects.filter(
                presenter__project_id=project_id,
                presenter__is_mic_label=False,
            ).values_list('presenter_id', 'sha256')
        }
        session = (PresenterSlot.objects
                   .filter(assignment__session__day__project_id=project_id)
                   .exclude(photo_data__isnull=True).exclude(photo_data=''))
        if slot_ids is not None:
            session = session.filter(id__in=list(slot_ids))
        self.session = dict(session.annotate(n=_ByteLength('photo_data'))
                            .values_list('id', 'n'))

    def for_slot(self, slot):
        if slot is None:
            return ''
        size = self.session.get(slot.pk)
        if size:
            return session_photo_url(slot.pk, size)
        return self.headshots.get(slot.presenter_id, '')


def photo_url_for_slot(slot):
    """One slot's photo URL -- for the JSON endpoints that return a single slot."""
    if slot is None:
        return ''
    project_id = slot.assignment.session.day.project_id
    return PhotoIndex(project_id, slot_ids=[slot.pk]).for_slot(slot)
