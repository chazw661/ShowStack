# planner/views_monitor.py

import json
import time
import ipaddress

from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from .models import (
    MonitorSession, DiscoveredDevice, PollResult, DeviceEvent,
)


# ──────────────────────────────────────────────
# Utility functions — NIC detection and sweep
# ──────────────────────────────────────────────

def get_scannable_nics():
    """Return list of NIC options for the scan UI dropdown.
    Each entry: {'interface': str, 'ip': str, 'subnet': str, 'display': str}
    """
    import netifaces

    result = []
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET not in addrs:
            continue
        for addr in addrs[netifaces.AF_INET]:
            ip = addr['addr']
            netmask = addr.get('netmask', '')
            if ip.startswith('127.') or ip.startswith('169.254.') or not netmask:
                continue
            network = ipaddress.IPv4Network(f'{ip}/{netmask}', strict=False)
            # Cap sweep at /24 to avoid enormous subnets on corporate networks
            if network.prefixlen < 24:
                network = ipaddress.IPv4Network(f'{ip}/24', strict=False)
            result.append({
                'interface': iface,
                'ip': ip,
                'subnet': str(network),
                'display': f'{iface} ({ip} — {network})',
            })
    return result


def sweep_subnet(subnet_cidr):
    """Ping all hosts in a subnet. Returns list of responding hosts.
    Each entry: {'ip': str, 'latency_ms': float}
    """
    import icmplib

    network = ipaddress.IPv4Network(subnet_cidr, strict=False)
    hosts = [str(h) for h in network.hosts()]
    results = icmplib.multiping(
        hosts,
        count=1,
        timeout=1,
        privileged=False,
        concurrent_tasks=100,
    )
    return [
        {'ip': r.address, 'latency_ms': round(r.avg_rtt, 2)}
        for r in results
        if r.is_alive
    ]


# ──────────────────────────────────────────────
# Dashboard view — initial page render
# ──────────────────────────────────────────────

@login_required
def network_monitor_view(request):
    """Main dashboard page. Renders current snapshot from DB."""
    current_project = getattr(request, 'current_project', None)

    # Get active session (if monitor is running)
    active_session = None
    if current_project:
        active_session = MonitorSession.objects.filter(
            project=current_project, ended_at__isnull=True
        ).first()

    # Get all active devices grouped by domain
    devices = []
    domain_counts = {'la_network': {'online': 0, 'total': 0},
                     'dante': {'online': 0, 'total': 0},
                     'switch': {'online': 0, 'total': 0}}
    if current_project:
        devices = list(
            DiscoveredDevice.objects.filter(
                project=current_project, is_active=True
            ).order_by('domain', 'label', 'ip_address')
        )
        for d in devices:
            dom = d.domain if d.domain in domain_counts else 'la_network'
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

    # Active alerts: devices offline in current session that haven't come back
    active_alerts = []
    if current_project:
        active_alerts = list(
            DiscoveredDevice.objects.filter(
                project=current_project,
                is_active=True,
                last_known_state='offline',
            )
        )

    # NIC list for scan dropdown
    try:
        nics = get_scannable_nics()
    except Exception:
        nics = []

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
        'nics': nics,
        'nics_json': json.dumps(nics),
        'has_project': current_project is not None,
        'monitor_running': active_session is not None,
    }
    return render(request, 'planner/network_monitor.html', context)


# ──────────────────────────────────────────────
# SSE stream — live status updates
# ──────────────────────────────────────────────

@login_required
def monitor_stream_view(request):
    """SSE endpoint. Streams DeviceEvent rows and periodic status snapshots."""
    current_project = getattr(request, 'current_project', None)

    def event_generator():
        last_event_id = 0

        # Find active session
        session = None
        if current_project:
            session = MonitorSession.objects.filter(
                project=current_project, ended_at__isnull=True
            ).first()

        while True:
            if session and current_project:
                # Stream new events
                events = DeviceEvent.objects.filter(
                    session=session,
                    id__gt=last_event_id,
                ).order_by('id').select_related('device')[:50]
                for ev in events:
                    last_event_id = ev.id
                    yield f"data: {json.dumps(ev.as_sse_dict())}\n\n"

                # Also send periodic status snapshot for all devices
                devices = DiscoveredDevice.objects.filter(
                    project=current_project, is_active=True
                )
                snapshot = {
                    'type': 'STATUS_SNAPSHOT',
                    'devices': [d.as_status_dict() for d in devices],
                }
                yield f"data: {json.dumps(snapshot)}\n\n"

            # Heartbeat to keep connection alive
            yield ": heartbeat\n\n"
            time.sleep(2)

    response = StreamingHttpResponse(
        event_generator(), content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ──────────────────────────────────────────────
# Scan endpoint — NIC-based subnet sweep
# ──────────────────────────────────────────────

@login_required
@require_POST
def trigger_scan_view(request):
    """Scan a subnet for responding hosts. Returns JSON list of discovered IPs."""
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        data = json.loads(request.body)
        selected_interface = data.get('interface', '')
        selected_subnet = data.get('subnet', '')

        # Validate: interface must be from our detected NIC list (per D-07)
        valid_nics = get_scannable_nics()
        valid_subnets = {n['subnet'] for n in valid_nics}
        if selected_subnet not in valid_subnets:
            return JsonResponse(
                {'error': 'Invalid subnet. Select a detected network interface.'},
                status=400
            )

        # Log scan event if session exists
        active_session = MonitorSession.objects.filter(
            project=current_project, ended_at__isnull=True
        ).first()
        if active_session:
            DeviceEvent.objects.create(
                session=active_session,
                event_type='SCAN_STARTED',
                details={'subnet': selected_subnet, 'interface': selected_interface},
            )

        # Perform sweep
        results = sweep_subnet(selected_subnet)

        # Annotate results with "already monitored" flag
        existing_ips = set(
            DiscoveredDevice.objects.filter(
                project=current_project, is_active=True
            ).values_list('ip_address', flat=True)
        )
        for r in results:
            r['already_monitored'] = r['ip'] in existing_ips

        return JsonResponse({
            'ok': True,
            'subnet': selected_subnet,
            'devices': results,
            'count': len(results),
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ──────────────────────────────────────────────
# Device management — add and remove
# ──────────────────────────────────────────────

@login_required
@require_POST
def add_monitor_devices_view(request):
    """Add discovered devices to monitoring. Expects JSON: {devices: [{ip, label, domain}]}"""
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        data = json.loads(request.body)
        devices_to_add = data.get('devices', [])
        added = 0

        for dev in devices_to_add:
            ip = dev.get('ip', '').strip()
            if not ip:
                continue
            obj, created = DiscoveredDevice.objects.get_or_create(
                project=current_project,
                ip_address=ip,
                defaults={
                    'label': dev.get('label', ''),
                    'domain': dev.get('domain', 'unknown'),
                    'is_active': True,
                }
            )
            if not created and not obj.is_active:
                # Re-activate previously removed device
                obj.is_active = True
                obj.label = dev.get('label', obj.label)
                obj.domain = dev.get('domain', obj.domain)
                obj.consecutive_failures = 0
                obj.last_known_state = 'unknown'
                obj.save()
            if created:
                added += 1

        return JsonResponse({'ok': True, 'added': added})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def remove_monitor_device_view(request, device_id):
    """Deactivate a device from monitoring. Does not delete — can be re-added via scan."""
    try:
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

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
