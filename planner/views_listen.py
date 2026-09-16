# planner/views_listen.py
#
# A2 Listen — companion-app API (Issue #74).
#
# Architecture:
#   - A local companion app runs on a wired Mac at the A2 rack. It captures a
#     Core Audio multichannel device (Dante Virtual Soundcard / Axient Dante
#     outputs) and streams a single selected channel to a phone browser over
#     the LAN via WebRTC/Opus. ShowStack never receives or relays audio.
#   - ShowStack's role: authenticate the companion to a show and hand it the
#     slot -> audio-channel mapping plus presenter names / mic types so the
#     companion can label its channel switcher. The A2 web view renders the
#     Listen controls and links out to the companion.
#
# Auth:
#   - Companion authenticates with the per-project listen_token (a UUID that
#     mirrors invite_token / agent_api_key). Accepted either as a Bearer token
#     in the Authorization header or as a ?token= query param, since the
#     companion also embeds it in the browser Listen URL.

import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Project, MicAssignment


def _authenticate_listen(request):
    """Resolve the project from the listen_token.

    Looks in the Authorization: Bearer <token> header first, then a ?token=
    query param. Returns (project, None) on success or (None, JsonResponse)
    on failure.
    """
    token = ''
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    if not token:
        token = (request.GET.get('token') or '').strip()
    if not token:
        return None, JsonResponse({'error': 'Missing listen token'}, status=401)
    try:
        project = Project.objects.get(listen_token=token)
        return project, None
    except (Project.DoesNotExist, ValueError, ValidationError):
        return None, JsonResponse({'error': 'Invalid listen token'}, status=403)


@csrf_exempt
@require_http_methods(["GET"])
def listen_session(request):
    """Return the show name and the slot -> audio-channel mapping.

    The companion calls this at startup (and may poll it) to authenticate and
    to label its channel switcher. Response shape:

        {
          "show": "Acme Keynote",
          "channels": [
            {"channel": 1, "rf_number": 1, "presenter": "Jane Doe",
             "mic_type": "LAV", "session": "Rehearsal", "day": "2026-09-16",
             "is_micd": true},
            ...
          ]
        }

    Channels are ordered by effective audio channel. Where more than one
    assignment maps to the same channel (e.g. the same RF reused across
    sessions), the most recently modified assignment wins the label so the
    companion shows whoever is currently on that channel.
    """
    project, error = _authenticate_listen(request)
    if error:
        return error

    # `presenter` is a property backed by the active PresenterSlot, not a
    # concrete FK, so prefetch the slots rather than select_related it.
    assignments = (
        MicAssignment.objects
        .filter(session__day__project=project)
        .select_related('session', 'session__day')
        .prefetch_related('presenter_slots__presenter')
        .order_by('-last_modified')
    )

    by_channel = {}
    for a in assignments:
        ch = a.effective_input_channel
        if ch in by_channel:
            # Most-recently-modified assignment already claimed this channel
            # (queryset is ordered newest-first), so keep it.
            continue
        session = a.session
        day = getattr(session, 'day', None)
        by_channel[ch] = {
            'channel': ch,
            'rf_number': a.rf_number,
            'presenter': a.presenter.name if a.presenter else '',
            'mic_type': a.mic_type or '',
            'session': getattr(session, 'name', '') or '',
            'day': day.date.isoformat() if day and getattr(day, 'date', None) else '',
            'is_micd': a.is_micd,
        }

    channels = [by_channel[ch] for ch in sorted(by_channel)]
    return JsonResponse({'show': project.name, 'channels': channels})
