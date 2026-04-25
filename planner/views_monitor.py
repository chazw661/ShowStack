# planner/views_monitor.py
#
# Network Health Monitor — cloud-side views.
#
# Architecture:
#   - A local agent runs on the engineer's show laptop (run_monitor command)
#   - The agent scans networks, pings devices, and POSTs results here
#   - This file serves the dashboard (read-only) and receives agent data
#   - SSE pushes live updates to the browser from the database
#
# Auth:
#   - Dashboard views: Django session auth (@login_required)
#   - Agent API endpoints: Project agent_api_key (Bearer token)

import ipaddress
import json
import time

from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.utils import timezone

from .models import (
    Project, MonitorSession, DiscoveredDevice, PollResult, DeviceEvent,
    ProjectSNMPConfig, SwitchPortSnapshot,
    Console, Device, Amp,
)


# ──────────────────────────────────────────────
# Agent authentication helper
# ──────────────────────────────────────────────

def _authenticate_agent(request):
    """Authenticate agent via Bearer token (project agent_api_key).
    Returns (project, None) on success or (None, JsonResponse) on failure.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, JsonResponse({'error': 'Missing Authorization header'}, status=401)

    token = auth_header[7:].strip()
    try:
        project = Project.objects.get(agent_api_key=token)
        return project, None
    except Project.DoesNotExist:
        return None, JsonResponse({'error': 'Invalid API key'}, status=403)


# ──────────────────────────────────────────────
# Dashboard view — initial page render (read-only)
# ──────────────────────────────────────────────

@login_required
def network_monitor_view(request):
    """Main dashboard page. Renders current snapshot from DB."""
    current_project = getattr(request, 'current_project', None)

    # Get active session (if agent is running)
    active_session = None
    if current_project:
        active_session = MonitorSession.objects.filter(
            project=current_project, ended_at__isnull=True
        ).first()

    # Get all active devices grouped by domain
    devices = []
    domain_counts = {'la_network': {'online': 0, 'total': 0},
                     'dante': {'online': 0, 'total': 0},
                     'switch': {'online': 0, 'total': 0},
                     'unknown': {'online': 0, 'total': 0}}
    if current_project:
        devices = list(
            DiscoveredDevice.objects.filter(
                project=current_project, is_active=True
            ).order_by('domain', 'label', 'ip_address')
        )
        for d in devices:
            dom = d.domain if d.domain in domain_counts else 'unknown'
            domain_counts[dom]['total'] += 1
            if d.status() == 'online':
                domain_counts[dom]['online'] += 1

    # Get recent events for session history
    recent_events = []
    if active_session:
        recent_events = list(
            DeviceEvent.objects.filter(
                session=active_session
            ).select_related('device').order_by('-occurred_at')[:50]
        )

    # Active alerts: only devices that WERE online and went offline
    # Never-seen devices (last_seen=None) show as "unreachable" — no alert
    active_alerts = []
    if current_project:
        active_alerts = list(
            DiscoveredDevice.objects.filter(
                project=current_project,
                is_active=True,
                last_known_state='offline',
                last_seen__isnull=False,  # must have been online at some point
            )
        )

    context = {
        'current_project': current_project,
        'active_session': active_session,
        'devices': devices,
        'devices_json': json.dumps([d.as_status_dict() for d in devices]),
        'domain_counts': domain_counts,
        'domain_counts_json': json.dumps(domain_counts),
        'recent_events': recent_events,
        'recent_events_json': json.dumps([e.as_sse_dict() for e in recent_events]),
        'active_alerts': active_alerts,
        'has_project': current_project is not None,
        'monitor_running': active_session is not None,
        'agent_api_key': str(current_project.agent_api_key) if current_project else '',
        'snmp_configured': ProjectSNMPConfig.objects.filter(project=current_project).exists() if current_project else False,
        'show_mode': active_session.show_mode if active_session else 'show',
    }
    return render(request, 'planner/network_monitor.html', context)


# ──────────────────────────────────────────────
# Status polling endpoint — replaces SSE
# ──────────────────────────────────────────────

@login_required
def monitor_status_view(request):
    """Returns current device status + recent events as JSON.
    The browser polls this every 2 seconds via fetch().
    Much more reliable than SSE with Django's threaded dev server.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'ok': False, 'error': 'No project'})

    # Get last_event_id from query param (browser tracks this)
    last_event_id = int(request.GET.get('last_event_id', '0'))

    # Active session?
    session = MonitorSession.objects.filter(
        project=current_project, ended_at__isnull=True
    ).first()

    # All active devices with current status
    devices = list(
        DiscoveredDevice.objects.filter(
            project=current_project, is_active=True
        )
    )

    # New events since last poll
    new_events = []
    if session:
        events = DeviceEvent.objects.filter(
            session=session, id__gt=last_event_id,
        ).order_by('id').select_related('device')[:50]
        new_events = [ev.as_sse_dict() for ev in events]

    return JsonResponse({
        'ok': True,
        'monitor_running': session is not None,
        'devices': [d.as_status_dict() for d in devices],
        'events': new_events,
        'last_event_id': new_events[-1]['id'] if new_events else last_event_id,
        'show_mode': session.show_mode if session else 'show',
        'switch_ports': {
            str(device.pk): [
                {
                    'port_index': snap.port_index,
                    'port_description': snap.port_description,
                    'oper_status': snap.oper_status,
                    'speed_mbps': snap.speed_mbps,
                    'bandwidth_pct': snap.bandwidth_pct,
                    'error_count': snap.error_count,
                }
                for snap in device.port_snapshots.filter(session=session).order_by('port_index')
            ]
            for device in devices
            if device.domain == 'switch'
        } if session else {},
        'dante_data': {
            str(device.pk): {
                'dante_device_name': device.dante_device_name,
                'clock_role': device.clock_role,
                'tx_channels': device.tx_channel_count,
                'rx_channels': device.rx_channel_count,
            }
            for device in devices
            if device.domain == 'dante'
        },
        'snmp_configured': ProjectSNMPConfig.objects.filter(
            project=current_project
        ).exists() if current_project else False,
    })


# ──────────────────────────────────────────────
# Dashboard management endpoints (session auth)
# ──────────────────────────────────────────────

@login_required
@require_POST
def dashboard_remove_device(request, device_id):
    """Remove a device from monitoring (dashboard action, session auth)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    device = DiscoveredDevice.objects.filter(
        pk=device_id, project=current_project
    ).first()
    if not device:
        return JsonResponse({'error': 'Device not found'}, status=404)

    device.is_active = False
    device.save(update_fields=['is_active'])
    return JsonResponse({'ok': True, 'device_id': device_id})


@login_required
@require_POST
def dashboard_reassign_device(request, device_id):
    """Change a device's domain assignment (e.g., unknown → switch)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    device = DiscoveredDevice.objects.filter(
        pk=device_id, project=current_project
    ).first()
    if not device:
        return JsonResponse({'error': 'Device not found'}, status=404)

    data = json.loads(request.body)
    new_domain = data.get('domain', '')
    valid_domains = ['la_network', 'dante', 'switch', 'unknown']
    if new_domain not in valid_domains:
        return JsonResponse({'error': f'Invalid domain. Use: {valid_domains}'}, status=400)

    device.domain = new_domain
    device.save(update_fields=['domain'])
    return JsonResponse({'ok': True, 'device_id': device_id, 'domain': new_domain})


@login_required
@require_POST
def dashboard_request_scan(request):
    """Set a scan-requested flag that the agent picks up on its next poll cycle."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    session = MonitorSession.objects.filter(
        project=current_project, ended_at__isnull=True
    ).first()

    if not session:
        return JsonResponse({'error': 'No active agent session. Start the agent first.'}, status=400)

    # Store the scan request in the session notes field as a simple flag
    session.notes = 'SCAN_REQUESTED'
    session.save(update_fields=['notes'])

    return JsonResponse({'ok': True, 'status': 'scan_requested'})


# ──────────────────────────────────────────────
# Agent API — receives data from local agent
# All endpoints use Bearer token auth (agent_api_key)
# ──────────────────────────────────────────────

@csrf_exempt
@require_POST
def agent_heartbeat(request):
    """Agent calls this to start/resume a session and report it's alive.
    POST /audiopatch/network-monitor/api/heartbeat/
    Body: {"agent_version": "1.0"}
    Returns: session_id, project_name
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    # Find existing open session or create new one
    session = MonitorSession.objects.filter(
        project=project, ended_at__isnull=True
    ).first()
    created = False
    if not session:
        session = MonitorSession.objects.create(project=project)
        created = True
        DeviceEvent.objects.create(
            session=session, event_type='MONITOR_STARTED',
            details={'source': 'agent'},
        )

    return JsonResponse({
        'ok': True,
        'session_id': session.pk,
        'project_name': project.name,
        'created': created,
    })


@csrf_exempt
@require_POST
def agent_stop(request):
    """Agent calls this when shutting down to close the session.
    POST /audiopatch/network-monitor/api/stop/
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    session = MonitorSession.objects.filter(
        project=project, ended_at__isnull=True
    ).first()
    if session:
        session.ended_at = timezone.now()
        session.save(update_fields=['ended_at'])

    return JsonResponse({'ok': True, 'status': 'stopped'})


@csrf_exempt
@require_POST
def agent_scan_results(request):
    """Agent pushes discovered devices from a network scan.
    POST /audiopatch/network-monitor/api/scan-results/
    Body: {"devices": [{"ip": "...", "label": "...", "domain": "dante", "latency_ms": 1.2}]}
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    data = json.loads(request.body)
    devices_data = data.get('devices', [])
    added = 0
    updated = 0

    for dev in devices_data:
        ip = dev.get('ip', '').strip()
        if not ip:
            continue
        obj, created = DiscoveredDevice.objects.get_or_create(
            project=project,
            ip_address=ip,
            defaults={
                'label': dev.get('label', ''),
                'domain': dev.get('domain', 'unknown'),
                'is_active': True,
            }
        )
        if created:
            added += 1
        else:
            # Update label/domain if provided and device exists
            changed = False
            if dev.get('label') and dev['label'] != obj.label:
                obj.label = dev['label']
                changed = True
            if dev.get('domain') and dev['domain'] != obj.domain:
                obj.domain = dev['domain']
                changed = True
            if not obj.is_active:
                obj.is_active = True
                obj.consecutive_failures = 0
                obj.last_known_state = 'unknown'
                changed = True
            if changed:
                obj.save()
                updated += 1

    # Log scan event
    session = MonitorSession.objects.filter(
        project=project, ended_at__isnull=True
    ).first()
    if session:
        DeviceEvent.objects.create(
            session=session, event_type='SCAN_STARTED',
            details={'device_count': len(devices_data), 'added': added},
        )

    return JsonResponse({'ok': True, 'added': added, 'updated': updated})


@csrf_exempt
@require_POST
def agent_poll_results(request):
    """Agent pushes poll results for all monitored devices.
    POST /audiopatch/network-monitor/api/poll-results/
    Body: {"results": [{"ip": "...", "is_alive": true, "latency_ms": 1.2}, ...]}

    The cloud handles N=3 state machine logic — the agent just reports raw results.
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    session = MonitorSession.objects.filter(
        project=project, ended_at__isnull=True
    ).first()
    if not session:
        return JsonResponse({'error': 'No active session. Call /api/heartbeat/ first.'}, status=400)

    data = json.loads(request.body)
    results = data.get('results', [])

    # Build IP → device map for this project
    active_devices = {
        d.ip_address: d
        for d in DiscoveredDevice.objects.filter(project=project, is_active=True)
    }

    events_created = []

    for r in results:
        ip = r.get('ip', '').strip()
        device = active_devices.get(ip)
        if not device:
            continue

        is_up = r.get('is_alive', False)
        latency = r.get('latency_ms')

        # Write poll result
        PollResult.objects.create(
            device=device, session=session,
            is_reachable=is_up, latency_ms=latency,
        )

        # N=3 state machine — runs on the cloud side
        prev_state = device.last_known_state

        if is_up:
            if prev_state != 'online':
                ev = DeviceEvent.objects.create(
                    device=device, session=session,
                    event_type='ONLINE',
                    details={'latency_ms': latency},
                )
                events_created.append(ev.as_sse_dict())
            device.consecutive_failures = 0
            device.last_known_state = 'online'
            device.last_seen = timezone.now()
        else:
            device.consecutive_failures = (device.consecutive_failures or 0) + 1
            if device.consecutive_failures == 3:
                device.last_known_state = 'offline'
                # Only fire OFFLINE alert if device was previously online
                # Never-seen devices (last_seen=None) stay "unreachable" — no alert
                if device.last_seen is not None:
                    ev = DeviceEvent.objects.create(
                        device=device, session=session,
                        event_type='OFFLINE',
                        details={'consecutive_failures': device.consecutive_failures},
                    )
                    events_created.append(ev.as_sse_dict())

        device.save(update_fields=['consecutive_failures', 'last_known_state', 'last_seen'])

    # Check if dashboard requested a re-scan
    scan_requested = False
    if session.notes == 'SCAN_REQUESTED':
        scan_requested = True
        session.notes = ''
        session.save(update_fields=['notes'])

    return JsonResponse({
        'ok': True,
        'processed': len(results),
        'events': events_created,
        'scan_requested': scan_requested,
    })


@csrf_exempt
@require_POST
def agent_remove_device(request):
    """Agent removes a device from monitoring.
    POST /audiopatch/network-monitor/api/remove-device/
    Body: {"ip": "..."}
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    data = json.loads(request.body)
    ip = data.get('ip', '').strip()

    device = DiscoveredDevice.objects.filter(
        project=project, ip_address=ip
    ).first()
    if not device:
        return JsonResponse({'error': 'Device not found'}, status=404)

    device.is_active = False
    device.save(update_fields=['is_active'])

    return JsonResponse({'ok': True, 'ip': ip})


@csrf_exempt
def agent_device_list(request):
    """Agent fetches the list of active devices to poll.
    GET /audiopatch/network-monitor/api/devices/
    Returns: list of IPs the agent should ping each cycle.
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    devices = DiscoveredDevice.objects.filter(
        project=project, is_active=True
    ).values_list('ip_address', flat=True)

    return JsonResponse({
        'ok': True,
        'devices': list(devices),
    })


# ──────────────────────────────────────────────
# Phase 2: SNMP endpoints
# ──────────────────────────────────────────────

@csrf_exempt
def agent_snmp_settings(request):
    """Agent fetches SNMP community string and switch IPs.
    GET /audiopatch/network-monitor/api/snmp-settings/
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    try:
        config = ProjectSNMPConfig.objects.get(project=project)
        community_string = config.community_string
    except ProjectSNMPConfig.DoesNotExist:
        return JsonResponse({'ok': True, 'configured': False, 'community_string': None, 'switches': []})

    switches = list(
        DiscoveredDevice.objects.filter(
            project=project, domain='switch', is_active=True
        ).values('pk', 'ip_address', 'label')
    )
    return JsonResponse({
        'ok': True,
        'configured': True,
        'community_string': community_string,
        'switches': [{'id': s['pk'], 'ip': s['ip_address'], 'label': s['label']} for s in switches],
    })


@csrf_exempt
@require_POST
def agent_snmp_results(request):
    """Agent pushes SNMP port data for switches.
    POST /audiopatch/network-monitor/api/snmp-results/
    Body: {"results": [{"device_id": N, "error": null|"string", "ports": [{"port_index": N,
           "port_description": "...", "oper_status": "up"|"down", "speed_mbps": N,
           "bandwidth_pct": N.N, "error_count": N}, ...]}]}
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    session = MonitorSession.objects.filter(project=project, ended_at__isnull=True).first()
    if not session:
        return JsonResponse({'error': 'No active session.'}, status=400)

    data = json.loads(request.body)
    results = data.get('results', [])
    suppress_non_critical = session.show_mode in ('setup', 'wrap')
    events_created = []

    for switch_data in results:
        device_id = switch_data.get('device_id')
        device = DiscoveredDevice.objects.filter(pk=device_id, project=project, is_active=True).first()
        if not device:
            continue

        snmp_error = switch_data.get('error')
        if snmp_error:
            # SNMP unreachable — skip port snapshots
            continue

        ports = switch_data.get('ports', [])
        for port_data in ports:
            port_idx = port_data.get('port_index')
            if port_idx is None:
                continue

            oper_status = port_data.get('oper_status', 'unknown')
            speed = port_data.get('speed_mbps')
            bw_pct = port_data.get('bandwidth_pct')
            err_count = port_data.get('error_count', 0)
            port_desc = port_data.get('port_description', '')

            # Get previous snapshot for change detection
            prev = SwitchPortSnapshot.objects.filter(
                device=device, session=session, port_index=port_idx
            ).first()
            prev_status = prev.oper_status if prev else None

            SwitchPortSnapshot.objects.update_or_create(
                device=device, session=session, port_index=port_idx,
                defaults={
                    'port_description': port_desc,
                    'oper_status': oper_status,
                    'speed_mbps': speed,
                    'bandwidth_pct': bw_pct,
                    'error_count': err_count,
                },
            )

            # Non-critical events — suppressed in setup/wrap per D-08
            if not suppress_non_critical:
                if prev_status and prev_status != oper_status:
                    event_type = 'PORT_UP' if oper_status == 'up' else 'PORT_DOWN'
                    ev = DeviceEvent.objects.create(
                        device=device, session=session,
                        event_type=event_type,
                        details={'port_index': port_idx, 'port_description': port_desc},
                    )
                    events_created.append(ev.as_sse_dict())
                if bw_pct is not None and bw_pct > 90:
                    ev = DeviceEvent.objects.create(
                        device=device, session=session,
                        event_type='BW_CRITICAL',
                        details={'port_index': port_idx, 'bandwidth_pct': bw_pct},
                    )
                    events_created.append(ev.as_sse_dict())
                elif bw_pct is not None and bw_pct > 70:
                    ev = DeviceEvent.objects.create(
                        device=device, session=session,
                        event_type='BW_WARNING',
                        details={'port_index': port_idx, 'bandwidth_pct': bw_pct},
                    )
                    events_created.append(ev.as_sse_dict())

    return JsonResponse({'ok': True, 'events': events_created})


# ──────────────────────────────────────────────
# Phase 3: Dante endpoints
# ──────────────────────────────────────────────

@csrf_exempt
@require_POST
def agent_dante_results(request):
    """Agent pushes Dante mDNS discovery data.
    POST /audiopatch/network-monitor/api/dante-results/
    Body: {"results": [{"name": "...", "ip": "...", "clock_role": "...", ...}, ...]}
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    session = MonitorSession.objects.filter(project=project, ended_at__isnull=True).first()
    if not session:
        return JsonResponse({'error': 'No active session.'}, status=400)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    results = data.get('results', [])
    if not isinstance(results, list):
        return JsonResponse({'error': 'results must be a list'}, status=400)

    events_created = []
    seen_ips = set()

    for entry in results:
        ip = entry.get('ip')
        name = entry.get('name', '')
        if not ip:
            continue

        seen_ips.add(ip)

        # Validate clock_role value
        clock_role = entry.get('clock_role', 'unknown')
        if clock_role not in ('master', 'locked', 'unlocked', 'unknown'):
            clock_role = 'unknown'

        device, created = DiscoveredDevice.objects.update_or_create(
            project=project,
            ip_address=ip,
            defaults={
                'domain': 'dante',
                'label': name,
                'dante_device_name': name,
                'clock_role': clock_role,
                'tx_channel_count': entry.get('tx_count'),
                'rx_channel_count': entry.get('rx_count'),
                'dante_model_id': entry.get('model_id', ''),
                'dante_mac_address': entry.get('mac_address', ''),
                'is_active': True,
                'last_seen': timezone.now(),
                'last_known_state': 'online',
                'consecutive_failures': 0,
            },
        )

        if created:
            ev = DeviceEvent.objects.create(
                device=device,
                session=session,
                event_type='DANTE_DISCOVERED',
                details={'name': name, 'ip': ip, 'clock_role': clock_role},
            )
            events_created.append(ev.as_sse_dict())

    # Clean up duplicate Dante records: same device name but different IP.
    # Keeps the record matching the current discovery IP, removes stale duplicates.
    seen_names = {}  # name -> current ip
    for entry in results:
        name = entry.get('name', '')
        ip = entry.get('ip')
        if name and ip:
            seen_names[name] = ip
    for name, current_ip in seen_names.items():
        DiscoveredDevice.objects.filter(
            project=project, domain='dante', dante_device_name=name,
        ).exclude(ip_address=current_ip).delete()

    # Deactivate Dante devices NOT in this discovery cycle
    stale_dante = DiscoveredDevice.objects.filter(
        project=project, domain='dante', is_active=True,
    ).exclude(ip_address__in=seen_ips)

    for device in stale_dante:
        device.is_active = False
        device.save(update_fields=['is_active'])

    return JsonResponse({'ok': True, 'events': events_created})


@login_required
def health_check_view(request):
    """GET /audiopatch/network-monitor/api/health-check/
    Compares discovered Dante devices against project device records.
    Returns missing (expected but not found) and unexpected (found but not in project).
    Per D-09: presence-based matching using case-insensitive name comparison.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'ok': False, 'error': 'No project'})

    # Discovered Dante devices (active, domain='dante')
    discovered_names = set(
        DiscoveredDevice.objects.filter(
            project=current_project, domain='dante', is_active=True,
        ).values_list('dante_device_name', flat=True)
    )
    # Remove empty strings
    discovered_names.discard('')

    # Expected project devices — check Console, Device, and Amp names.
    # Per D-09, any name match counts; per RESEARCH.md A4, we match against
    # all project device names (not just Dante-flagged ones).
    expected_names = set()
    for Model in [Console, Device, Amp]:
        expected_names.update(
            Model.objects.filter(project=current_project)
            .values_list('name', flat=True)
        )
    # Remove empty strings
    expected_names.discard('')

    # Case-insensitive matching per D-09 / RESEARCH.md Pitfall 5
    discovered_lower = {n.lower(): n for n in discovered_names}
    expected_lower = {n.lower(): n for n in expected_names}

    missing = [expected_lower[n] for n in expected_lower if n not in discovered_lower]
    unexpected = [discovered_lower[n] for n in discovered_lower if n not in expected_lower]

    return JsonResponse({
        'ok': True,
        'status': 'ok' if not missing and not unexpected else 'issues',
        'missing': sorted(missing),
        'unexpected': sorted(unexpected),
        'total_expected': len(expected_names),
        'total_found': len(discovered_names),
    })


@login_required
@require_POST
def dashboard_snmp_settings(request):
    """Save SNMP community string for the project (per D-01, D-02)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    data = json.loads(request.body)
    community_string = data.get('community_string', '').strip()
    if not community_string:
        return JsonResponse({'error': 'Community string cannot be empty'}, status=400)
    if len(community_string) > 255:
        return JsonResponse({'error': 'Community string too long (max 255 chars)'}, status=400)

    config, _ = ProjectSNMPConfig.objects.get_or_create(project=current_project)
    config.community_string = community_string
    config.save(update_fields=['community_string', 'updated_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def dashboard_add_switch(request):
    """Manually add a switch IP to monitoring (per D-04)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    data = json.loads(request.body)
    ip = data.get('ip', '').strip()
    label = data.get('label', '').strip()

    # Validate IP
    try:
        ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Enter a valid IP address.'}, status=400)

    # Check duplicate
    existing = DiscoveredDevice.objects.filter(project=current_project, ip_address=ip).first()
    if existing:
        if existing.is_active and existing.domain == 'switch':
            return JsonResponse({'error': f'{ip} is already being monitored.'}, status=400)
        # Reactivate and reassign to switch domain
        existing.domain = 'switch'
        existing.is_active = True
        existing.label = label or existing.label
        existing.save(update_fields=['domain', 'is_active', 'label'])
        return JsonResponse({'ok': True, 'device_id': existing.pk, 'ip': ip, 'label': existing.label})

    device = DiscoveredDevice.objects.create(
        project=current_project, ip_address=ip, label=label,
        domain='switch', is_active=True,
    )
    return JsonResponse({'ok': True, 'device_id': device.pk, 'ip': ip, 'label': device.label})


@login_required
@require_POST
def dashboard_set_show_mode(request):
    """Set the show mode (Setup/Show/Wrap) on the active MonitorSession (per D-07, D-08)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    data = json.loads(request.body)
    mode = data.get('mode', '').strip().lower()
    if mode not in ('setup', 'show', 'wrap'):
        return JsonResponse({'error': 'Invalid mode. Use: setup, show, wrap'}, status=400)

    session = MonitorSession.objects.filter(project=current_project, ended_at__isnull=True).first()
    if not session:
        return JsonResponse({'error': 'No active monitor session.'}, status=400)

    session.show_mode = mode
    session.save(update_fields=['show_mode'])
    return JsonResponse({'ok': True, 'show_mode': mode})
