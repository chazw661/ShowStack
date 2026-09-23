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

import ipaddress
import json
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from django.db.models import Prefetch

from .models import Project, MicAssignment, MicSession


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

    The same RF slot carries a different presenter in each session, so a flat
    channel list can only ever be right for one of them. `sessions` is the real
    answer — every session with its own channel labels, in show order:

        "sessions": [
          {"id": 12, "name": "AM Keynote", "day": "2026-09-16",
           "channels": [{"channel": 1, "rf_number": 1, "presenter": "David Wong",
                         "mic_type": "LAV", "is_micd": true}, ...]},
          ...
        ]

    `channels` stays for companion builds that predate the sessions key: it is
    one entry per channel, the most recently modified assignment winning the
    label.
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

    # Per-session lists: what the Listen page's pickers actually use.
    sessions = (
        MicSession.objects
        .filter(day__project=project)
        .select_related('day')
        .prefetch_related(Prefetch(
            'mic_assignments',
            queryset=MicAssignment.objects.order_by('rf_number')
                     .prefetch_related('presenter_slots__presenter')))
        .order_by('day__date', 'order', 'id')
    )

    session_rows = []
    for s in sessions:
        rows, seen = [], set()
        for a in s.mic_assignments.all():
            ch = a.effective_input_channel
            if ch in seen:
                # Two slots overriding onto one channel: lowest RF labels it.
                continue
            seen.add(ch)
            rows.append({
                'channel': ch,
                'rf_number': a.rf_number,
                'presenter': a.presenter.name if a.presenter else '',
                'mic_type': a.mic_type or '',
                'is_micd': a.is_micd,
            })
        if not rows:
            continue
        day = getattr(s, 'day', None)
        session_rows.append({
            'id': s.id,
            'name': s.name or '',
            'day': day.date.isoformat() if day and getattr(day, 'date', None) else '',
            'channels': sorted(rows, key=lambda r: r['channel']),
        })

    return JsonResponse({'show': project.name, 'channels': channels,
                         'sessions': session_rows})


# A heartbeat older than this means the app isn't running (it sends every ~5 s).
LISTEN_STATUS_STALE_SECONDS = 20
# Apps that stopped reporting are kept in the blob this long before being
# dropped, so a brief network stall doesn't erase a rack from the list.
LISTEN_STATUS_KEEP_SECONDS = 600


def _private_https_url(value):
    """Keep only https://<private IPv4 or .local>:<port> addresses."""
    try:
        u = urlparse(str(value or ''))
        if u.scheme != 'https' or not u.hostname or u.path not in ('', '/') or u.query:
            return None
        host = u.hostname
        if not host.endswith('.local'):
            if not ipaddress.ip_address(host).is_private:
                return None
        return 'https://%s:%d' % (host, u.port or 443)
    except ValueError:
        return None


def _clean_status(data):
    def text(key, limit=120):
        v = data.get(key)
        return str(v)[:limit] if v is not None else None

    def number(key):
        try:
            return max(0, int(data.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    return {
        'running': bool(data.get('running', True)),
        'version': text('version', 20),
        'device': text('device'),
        'source': text('source', 160),
        'channels': number('channels'),
        'sample_rate': number('sample_rate'),
        'listeners': number('listeners'),
        # Seconds the app has been stuck opening its audio device (0 = healthy).
        'device_stuck': number('device_stuck'),
        'lan_url': _private_https_url(data.get('lan_url')),
        # Which Mac this is. `instance` is stable per Mac; `client_id` is the
        # browser that pressed "Start on this Mac", so a page can tell its own
        # rack apart from someone else's at the same show.
        'instance': text('instance', 64),
        'host': text('host', 60),
        'client_id': text('client_id', 64),
    }


def _apps_from_blob(blob, fallback_at):
    """Normalise stored status into {instance: status-with-'at'}.

    Older apps posted a single flat status with no instance; it is carried
    forward under the 'legacy' key so one old rack still shows up.
    """
    if not isinstance(blob, dict):
        return {}
    apps = blob.get('apps')
    if isinstance(apps, dict):
        return {k: v for k, v in apps.items() if isinstance(v, dict)}
    if blob:
        legacy = dict(blob)
        legacy.setdefault('at', fallback_at.isoformat() if fallback_at else None)
        return {'legacy': legacy}
    return {}


def _app_age(app, now):
    at = app.get('at')
    if not at:
        return None
    parsed = parse_datetime(at) if isinstance(at, str) else None
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.utc)
    return (now - parsed).total_seconds()


@csrf_exempt
@require_http_methods(["POST"])
def listen_heartbeat(request):
    """The Listen app reports what it's doing (every few seconds, and on stop).

    Several Macs can run Listen for one show — a rack Mac plus an A2's laptop —
    so each app's status is stored under its own instance id rather than
    overwriting a single field.
    """
    project, error = _authenticate_listen(request)
    if error:
        return error
    try:
        data = json.loads(request.body or b'{}')
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    status = _clean_status(data)
    instance = status.get('instance') or 'legacy'
    now = timezone.now()

    with transaction.atomic():
        row = (Project.objects.select_for_update()
               .only('listen_status', 'listen_status_at').get(pk=project.pk))
        apps = _apps_from_blob(row.listen_status, row.listen_status_at)
        if status['running']:
            apps[instance] = dict(status, at=now.isoformat())
        else:
            apps.pop(instance, None)
        # Drop racks that have been silent for a long time.
        apps = {k: v for k, v in apps.items()
                if (_app_age(v, now) or 0) <= LISTEN_STATUS_KEEP_SECONDS}
        # queryset.update() so the project's updated_at / signals aren't touched.
        Project.objects.filter(pk=project.pk).update(
            listen_status={'apps': apps}, listen_status_at=now)
    return JsonResponse({'ok': True, 'show': project.name})


@login_required
@require_http_methods(["GET"])
def listen_app_status(request):
    """Listen app status for the current project, for the Mic Tracker page.

    `?client=<id>` identifies the browser that started an app, so the page can
    be told about its OWN Mac ("mine") rather than any rack at the show.
    """
    project = getattr(request, 'current_project', None)
    if project is None:
        return JsonResponse({'running': False, 'reason': 'no_project'})
    project = Project.objects.only('listen_status', 'listen_status_at').get(pk=project.pk)
    now = timezone.now()
    client = (request.GET.get('client') or '').strip()[:64]

    fresh = []
    for app in _apps_from_blob(project.listen_status, project.listen_status_at).values():
        age = _app_age(app, now)
        if age is None or age > LISTEN_STATUS_STALE_SECONDS:
            continue
        if not app.get('running', True):
            continue
        fresh.append(dict(app, age=age))
    fresh.sort(key=lambda a: a.get('age') or 0)

    mine = None
    if client:
        mine = next((a for a in fresh if a.get('client_id') == client), None)
    if mine is None:
        # An app launched from Finder or the Dock never learned a client id.
        # If exactly one such rack is running there is nothing to confuse it
        # with, so treat it as this device's.
        unclaimed = [a for a in fresh if not a.get('client_id')]
        if len(unclaimed) == 1:
            mine = unclaimed[0]
    if mine is None and not client and len(fresh) == 1:
        mine = fresh[0]

    primary = mine or (fresh[0] if fresh else {})
    others = [a for a in fresh if a is not mine]
    response = JsonResponse({
        **primary,
        'running': bool(mine) if client else bool(fresh),
        'age': primary.get('age'),
        'mine': mine,
        'apps': fresh,
        'others': [{'host': a.get('host'), 'source': a.get('source'),
                    'listeners': a.get('listeners')} for a in others],
    })
    response['Cache-Control'] = 'no-store'
    return response
