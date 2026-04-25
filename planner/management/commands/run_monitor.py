"""
ShowStack Network Monitor Agent

A standalone agent that runs on the engineer's show laptop, discovers
devices on the local network, pings them, and pushes results to the
ShowStack cloud API.

Usage:
    python manage.py run_monitor --api-key <project-agent-api-key> [--server https://showstack.io]
    python manage.py run_monitor --api-key <key> --scan          # scan + monitor
    python manage.py run_monitor --api-key <key> --scan-only     # scan only, don't poll

The agent authenticates with the project's agent_api_key (shown on the
Network Health Monitor dashboard). All network scanning and ICMP polling
happens locally on this machine. Results are POSTed to the ShowStack API.
"""
import time
import ipaddress
import subprocess
import json
import threading
import asyncio

import requests as http_requests  # renamed to avoid shadowing Django requests

from django.core.management.base import BaseCommand


# ── SNMP polling functions (module-level, called via asyncio.run) ─────────────

try:
    from pysnmp.hlapi.asyncio import (
        SnmpEngine, CommunityData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity, walk_cmd,
    )
    PYSNMP_AVAILABLE = True
except ImportError:
    PYSNMP_AVAILABLE = False

# ── Dante mDNS discovery (module-level, called via asyncio.run) ──────────────

try:
    from netaudio.dante.browser import DanteBrowser
    NETAUDIO_AVAILABLE = True
except ImportError:
    NETAUDIO_AVAILABLE = False


async def _async_discover_dante(timeout=3.0):
    """Discover Dante devices via mDNS using netaudio DanteBrowser."""
    browser = DanteBrowser(mdns_timeout=timeout)
    devices = await browser.get_devices()
    results = []
    for server_name, device in devices.items():
        # Map PTP role to clock_role per D-04 / RESEARCH.md Open Question 3:
        # "Leader" -> "master", "Follower" -> "locked", None -> "unknown"
        ptp_role = getattr(device, 'ptp_v1_role', None)
        if ptp_role == 'Leader':
            clock_role = 'master'
        elif ptp_role == 'Follower':
            clock_role = 'locked'
        else:
            clock_role = 'unknown'

        results.append({
            'name': device.name or server_name,
            'ip': str(device.ipv4) if device.ipv4 else None,
            'server_name': server_name,
            'model_id': getattr(device, 'model_id', '') or '',
            'sample_rate': getattr(device, 'sample_rate', None),
            'mac_address': getattr(device, 'mac_address', '') or '',
            'tx_count': getattr(device, 'tx_count', None),
            'rx_count': getattr(device, 'rx_count', None),
            'clock_role': clock_role,
        })
    return results

IF_MIB_ROOTS = {
    'oper_status':   '1.3.6.1.2.1.2.2.1.8',
    'high_speed':    '1.3.6.1.2.1.31.1.1.1.15',
    'hc_in_octets':  '1.3.6.1.2.1.31.1.1.1.6',
    'hc_out_octets': '1.3.6.1.2.1.31.1.1.1.10',
    'in_errors':     '1.3.6.1.2.1.2.2.1.14',
    'if_descr':      '1.3.6.1.2.1.2.2.1.2',
}


async def _async_walk_subtree(snmp_engine, community, transport, oid_root):
    """Walk one IF-MIB subtree via GETNEXT/walk_cmd.
    Returns {port_index: value_string} or None on error."""
    rows = {}
    try:
        async for (err_indication, err_status, err_index, var_binds) in walk_cmd(
            snmp_engine,
            CommunityData(community),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid_root)),
            lexicographicMode=False,
        ):
            if err_indication or err_status:
                return None
            for name, val in var_binds:
                oid_str = str(name)
                port_idx = int(oid_str.split('.')[-1])
                rows[port_idx] = val.prettyPrint()
    except Exception:
        return None
    return rows


async def _async_poll_switch(ip, community):
    """Poll all IF-MIB subtrees for a single switch.
    Returns {port_idx: {field: val}} or None if SNMP unreachable."""
    snmp_engine = SnmpEngine()
    try:
        transport = await UdpTransportTarget.create((ip, 161), timeout=5, retries=1)

        tables = {}
        for field_name, oid_root in IF_MIB_ROOTS.items():
            result = await _async_walk_subtree(snmp_engine, community, transport, oid_root)
            if result is None and field_name == 'oper_status':
                # Cannot even get port status — switch is SNMP-unreachable
                return None
            if result is not None:
                tables[field_name] = result

        # Merge tables into per-port dicts
        ports = {}
        oper_table = tables.get('oper_status', {})
        for port_idx in oper_table:
            oper_val = oper_table[port_idx]
            # ifOperStatus: '1'=up, '2'=down
            oper_status = 'up' if str(oper_val) == '1' else 'down'
            speed_raw = tables.get('high_speed', {}).get(port_idx, '0')
            speed_mbps = int(speed_raw) if str(speed_raw).isdigit() else 0
            in_octets = int(tables.get('hc_in_octets', {}).get(port_idx, '0') or '0')
            out_octets = int(tables.get('hc_out_octets', {}).get(port_idx, '0') or '0')
            in_errors = int(tables.get('in_errors', {}).get(port_idx, '0') or '0')
            port_descr = str(tables.get('if_descr', {}).get(port_idx, ''))

            ports[port_idx] = {
                'oper_status': oper_status,
                'speed_mbps': speed_mbps,
                'hc_in_octets': in_octets,
                'hc_out_octets': out_octets,
                'in_errors': in_errors,
                'port_description': port_descr,
            }
        return ports
    finally:
        snmp_engine.closeDispatcher()


async def _async_poll_all_switches(switches, community):
    """Poll all switches. Returns list of per-switch result dicts."""
    results = []
    for sw in switches:
        port_data = await _async_poll_switch(sw['ip'], community)
        results.append({
            'device_id': sw['id'],
            'ip': sw['ip'],
            'ports': port_data,  # None if SNMP unreachable
        })
    return results


def _compute_bandwidth_pct(curr_in, prev_in, curr_out, prev_out, prev_ts, curr_ts, speed_mbps):
    """RFC 2863 bandwidth utilization from counter deltas. Returns 0.0-100.0 or None."""
    interval = curr_ts - prev_ts
    if interval <= 0 or not speed_mbps:
        return None
    delta_in = (curr_in - prev_in) % (2 ** 64)
    delta_out = (curr_out - prev_out) % (2 ** 64)
    link_bps = speed_mbps * 1_000_000
    pct = (max(delta_in, delta_out) * 8 / (link_bps * interval)) * 100
    # Use 2 decimal places to preserve small values that round to 0 with 1dp
    return min(round(pct, 2), 100.0)


class Command(BaseCommand):
    help = 'Run the ShowStack network monitor agent (scans and polls locally, pushes to cloud)'

    def add_arguments(self, parser):
        parser.add_argument('--api-key', type=str, required=True,
                            help='Project agent API key (from the dashboard)')
        parser.add_argument('--server', type=str, default='http://localhost:8000',
                            help='ShowStack server URL (default: http://localhost:8000)')
        parser.add_argument('--interval', type=int, default=10,
                            help='Poll interval in seconds (default: 10)')
        parser.add_argument('--scan', action='store_true',
                            help='Run a network scan before starting polling')
        parser.add_argument('--scan-only', action='store_true',
                            help='Run a network scan and exit (no polling)')

    def handle(self, *args, **options):
        api_key = options['api_key']
        server = options['server'].rstrip('/')
        interval = options['interval']
        base_url = f'{server}/audiopatch/network-monitor/api'
        scan = options['scan'] or options['scan_only']
        scan_only = options['scan_only']

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        # ── Step 1: Authenticate with heartbeat ──
        self.stdout.write('Connecting to ShowStack...')
        try:
            resp = http_requests.post(f'{base_url}/heartbeat/', headers=headers,
                                      json={'agent_version': '1.0'}, timeout=10)
        except http_requests.ConnectionError:
            self.stderr.write(self.style.ERROR(
                f'Cannot connect to {server}. Is the server running?'
            ))
            return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Connection error: {e}'))
            return

        if resp.status_code == 403:
            self.stderr.write(self.style.ERROR('Invalid API key. Check the key on your dashboard.'))
            return
        if resp.status_code != 200:
            self.stderr.write(self.style.ERROR(f'Server error: {resp.status_code} {resp.text}'))
            return

        data = resp.json()
        project_name = data.get('project_name', 'Unknown')
        session_id = data.get('session_id')
        self.stdout.write(self.style.SUCCESS(
            f'Connected to project "{project_name}" (session {session_id})'
        ))

        # ── Step 2: Network scan (if requested) ──
        if scan:
            self.stdout.write('\nScanning local networks...')
            discovered = self._scan_all_nics()
            if discovered:
                self.stdout.write(f'Found {len(discovered)} devices:')
                for dev in discovered:
                    self.stdout.write(f'  {dev["ip"]} ({dev["domain"]}) — {dev.get("latency_ms", "?")} ms')

                # Push to API
                resp = http_requests.post(
                    f'{base_url}/scan-results/',
                    headers=headers,
                    json={'devices': discovered},
                    timeout=30,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    self.stdout.write(self.style.SUCCESS(
                        f'Pushed to ShowStack: {result.get("added", 0)} new, '
                        f'{result.get("updated", 0)} updated'
                    ))
                else:
                    self.stderr.write(self.style.WARNING(f'Push failed: {resp.text}'))
            else:
                self.stdout.write('No devices found on any interface.')

            if scan_only:
                self.stdout.write('Scan complete. Exiting (--scan-only).')
                return

        # ── Step 3: Start polling threads ──
        self.stdout.write(f'\nStarting polling. ICMP every {interval}s, SNMP every 30s, Dante every 30s. Press Ctrl+C to stop.')

        stop_event = threading.Event()

        icmp_thread = threading.Thread(
            target=self._icmp_loop,
            args=(stop_event, base_url, headers, interval),
            daemon=True, name='ICMPPoller',
        )
        snmp_thread = threading.Thread(
            target=self._snmp_loop,
            args=(stop_event, base_url, headers),
            daemon=True, name='SNMPPoller',
        )
        dante_thread = threading.Thread(
            target=self._dante_loop,
            args=(stop_event, base_url, headers),
            daemon=True, name='DantePoller',
        )

        icmp_thread.start()
        snmp_thread.start()
        dante_thread.start()

        try:
            while not stop_event.is_set():
                stop_event.wait(timeout=1)
        except KeyboardInterrupt:
            self.stdout.write('\nShutting down...')
            stop_event.set()

        icmp_thread.join(timeout=5)
        snmp_thread.join(timeout=5)
        dante_thread.join(timeout=5)

        # Shutdown
        try:
            http_requests.post(f'{base_url}/stop/', headers=headers,
                               json={}, timeout=5)
        except Exception:
            pass
        self.stdout.write(self.style.SUCCESS('Monitor agent stopped.'))

    def _icmp_loop(self, stop_event, base_url, headers, interval):
        """ICMP polling — existing logic moved from flat while-loop."""
        while not stop_event.is_set():
            poll_results = self._poll_devices(base_url, headers)
            if poll_results:
                try:
                    resp = http_requests.post(
                        f'{base_url}/poll-results/',
                        headers=headers,
                        json={'results': poll_results},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        events = result.get('events', [])
                        for ev in events:
                            etype = ev.get('type', '')
                            name = ev.get('device_name', ev.get('device_id', ''))
                            if etype == 'OFFLINE':
                                self.stderr.write(self.style.ERROR(f'  OFFLINE: {name}'))
                            elif etype == 'ONLINE':
                                self.stdout.write(self.style.SUCCESS(f'  ONLINE: {name}'))
                        if result.get('scan_requested'):
                            self.stdout.write(self.style.WARNING('\nRe-scan requested from dashboard...'))
                            discovered = self._scan_all_nics()
                            if discovered:
                                self.stdout.write(f'Found {len(discovered)} devices')
                                http_requests.post(
                                    f'{base_url}/scan-results/',
                                    headers=headers,
                                    json={'devices': discovered},
                                    timeout=30,
                                )
                    else:
                        self.stderr.write(self.style.WARNING(f'Poll push failed ({resp.status_code})'))
                except http_requests.ConnectionError:
                    self.stderr.write(self.style.WARNING('Lost connection to ShowStack. Retrying next cycle...'))
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f'Error: {e}'))

            # Wait with stop_event check
            stop_event.wait(timeout=interval)

    def _snmp_loop(self, stop_event, base_url, headers):
        """SNMP polling thread — polls switch-domain devices every 30 seconds."""
        if not PYSNMP_AVAILABLE:
            self.stderr.write(self.style.WARNING(
                'pysnmp not installed — SNMP polling disabled. Install: pip install "pysnmp>=7.1,<8.0"'
            ))
            return

        SNMP_INTERVAL = 30
        prev_counters = {}  # {(device_id, port_idx): {'in': N, 'out': N, 'ts': float}}

        while not stop_event.is_set():
            snmp_settings = self._fetch_snmp_settings(base_url, headers)
            if not snmp_settings or not snmp_settings.get('configured'):
                stop_event.wait(timeout=SNMP_INTERVAL)
                continue

            community = snmp_settings['community_string']
            switches = snmp_settings.get('switches', [])
            if not switches:
                stop_event.wait(timeout=SNMP_INTERVAL)
                continue

            # Poll all switches via asyncio.run (safe — this thread has no event loop)
            try:
                raw_results = asyncio.run(_async_poll_all_switches(switches, community))
            except Exception as e:
                self.stderr.write(self.style.WARNING(f'[SNMP] Poll error: {e}'))
                stop_event.wait(timeout=SNMP_INTERVAL)
                continue

            # Process results: compute bandwidth from deltas, build push payload
            now = time.time()
            push_results = []
            for sw_result in raw_results:
                device_id = sw_result['device_id']
                port_data = sw_result['ports']

                if port_data is None:
                    # SNMP unreachable
                    push_results.append({
                        'device_id': device_id,
                        'error': 'SNMP unreachable',
                        'ports': [],
                    })
                    self.stderr.write(self.style.WARNING(
                        f'  [SNMP] {sw_result["ip"]}: unreachable'
                    ))
                    continue

                ports_payload = []
                for port_idx, pdata in sorted(port_data.items()):
                    # Compute bandwidth from counter deltas
                    counter_key = (device_id, port_idx)
                    prev = prev_counters.get(counter_key)
                    bw_pct = None
                    if prev:
                        bw_pct = _compute_bandwidth_pct(
                            pdata['hc_in_octets'], prev['in'],
                            pdata['hc_out_octets'], prev['out'],
                            prev['ts'], now,
                            pdata['speed_mbps'],
                        )
                    # Store current counters for next cycle
                    prev_counters[counter_key] = {
                        'in': pdata['hc_in_octets'],
                        'out': pdata['hc_out_octets'],
                        'ts': now,
                    }

                    ports_payload.append({
                        'port_index': port_idx,
                        'port_description': pdata.get('port_description', ''),
                        'oper_status': pdata['oper_status'],
                        'speed_mbps': pdata['speed_mbps'],
                        'bandwidth_pct': bw_pct,
                        'error_count': pdata['in_errors'],
                    })

                push_results.append({
                    'device_id': device_id,
                    'error': None,
                    'ports': ports_payload,
                })

            # Push to Django API
            if push_results:
                self._push_snmp_results(base_url, headers, push_results)

            stop_event.wait(timeout=SNMP_INTERVAL)

    def _fetch_snmp_settings(self, base_url, headers):
        """GET /api/snmp-settings/ — returns community string + switch IP list."""
        try:
            resp = http_requests.get(
                f'{base_url}/snmp-settings/',
                headers=headers, timeout=10,
            )
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def _push_snmp_results(self, base_url, headers, results):
        """POST /api/snmp-results/ — push port data for all switches."""
        try:
            resp = http_requests.post(
                f'{base_url}/snmp-results/',
                headers=headers,
                json={'results': results},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                events = data.get('events', [])
                for ev in events:
                    etype = ev.get('type', '')
                    name = ev.get('device_name', ev.get('device_id', ''))
                    port = ev.get('details', {}).get('port_index', '')
                    if etype == 'PORT_DOWN':
                        self.stderr.write(self.style.WARNING(f'  [SNMP] {name} port {port} DOWN'))
                    elif etype == 'PORT_UP':
                        self.stdout.write(self.style.SUCCESS(f'  [SNMP] {name} port {port} UP'))
            else:
                self.stderr.write(self.style.WARNING(f'[SNMP] Push failed ({resp.status_code})'))
        except http_requests.ConnectionError:
            self.stderr.write(self.style.WARNING('[SNMP] Lost connection. Retrying next cycle...'))
        except Exception as e:
            self.stderr.write(self.style.WARNING(f'[SNMP] Push error: {e}'))

    def _dante_loop(self, stop_event, base_url, headers):
        """Dante mDNS discovery thread — discovers devices every 30 seconds."""
        if not NETAUDIO_AVAILABLE:
            self.stderr.write(self.style.WARNING(
                'netaudio not installed -- Dante discovery disabled. Install: pip install "netaudio==0.2.4"'
            ))
            return

        DANTE_INTERVAL = 30

        while not stop_event.is_set():
            try:
                devices = asyncio.run(_async_discover_dante(timeout=3.0))
            except Exception as e:
                self.stderr.write(self.style.WARNING(f'[Dante] Discovery error: {e}'))
                stop_event.wait(timeout=DANTE_INTERVAL)
                continue

            if devices:
                self._push_dante_results(base_url, headers, devices)

            stop_event.wait(timeout=DANTE_INTERVAL)

    def _push_dante_results(self, base_url, headers, results):
        """POST /api/dante-results/ — push Dante mDNS discovery data."""
        try:
            resp = http_requests.post(
                f'{base_url}/dante-results/',
                headers=headers,
                json={'results': results},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                events = data.get('events', [])
                for ev in events:
                    etype = ev.get('type', '')
                    name = ev.get('device_name', '')
                    if etype == 'DANTE_DISCOVERED':
                        self.stdout.write(self.style.SUCCESS(f'  [Dante] Discovered: {name}'))
                    elif etype == 'DANTE_LOST':
                        self.stderr.write(self.style.WARNING(f'  [Dante] Lost: {name}'))
            else:
                self.stderr.write(self.style.WARNING(f'[Dante] Push failed ({resp.status_code})'))
        except http_requests.ConnectionError:
            self.stderr.write(self.style.WARNING('[Dante] Lost connection. Retrying next cycle...'))
        except Exception as e:
            self.stderr.write(self.style.WARNING(f'[Dante] Push error: {e}'))

    def _scan_all_nics(self):
        """Scan all active NICs for responding devices."""
        import netifaces
        import icmplib

        all_devices = []
        scanned_subnets = set()

        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET not in addrs:
                continue
            for addr in addrs[netifaces.AF_INET]:
                ip = addr['addr']
                netmask = addr.get('netmask', '')
                if ip.startswith('127.') or not netmask:
                    continue

                network = ipaddress.IPv4Network(f'{ip}/{netmask}', strict=False)

                # Link-local: use ARP discovery
                if ip.startswith('169.254.'):
                    subnet_key = '169.254.0.0/16'
                    if subnet_key in scanned_subnets:
                        continue
                    scanned_subnets.add(subnet_key)
                    self.stdout.write(f'  Scanning link-local on {iface} ({ip})...')
                    devices = self._discover_link_local()
                    for d in devices:
                        d['domain'] = 'dante'
                    # Include this machine's own link-local IP (ARP doesn't list self)
                    own_ips = {d['ip'] for d in devices}
                    if ip not in own_ips:
                        devices.append({
                            'ip': ip, 'label': ip, 'domain': 'dante',
                            'latency_ms': 0.0,
                        })
                    all_devices.extend(devices)
                    continue

                # Regular subnet
                if network.prefixlen < 24:
                    network = ipaddress.IPv4Network(f'{ip}/24', strict=False)
                subnet_key = str(network)
                if subnet_key in scanned_subnets:
                    continue
                scanned_subnets.add(subnet_key)

                self.stdout.write(f'  Scanning {subnet_key} on {iface}...')
                hosts = [str(h) for h in network.hosts()]
                try:
                    results = icmplib.multiping(
                        hosts, count=1, timeout=1,
                        privileged=False, concurrent_tasks=100,
                    )
                    for r in results:
                        if r.is_alive:
                            all_devices.append({
                                'ip': r.address,
                                'label': '',
                                'domain': 'unknown',
                                'latency_ms': round(r.avg_rtt, 2),
                            })
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f'    Scan error: {e}'))

        return all_devices

    def _discover_link_local(self):
        """Discover devices on link-local (169.254.x.x) via ARP cache."""
        import icmplib

        # Multicast ping to populate ARP cache
        for target in ['224.0.0.251', '169.254.255.255']:
            try:
                subprocess.run(
                    ['ping', '-c', '2', '-W', '1', '-t', '2', target],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass

        # Parse ARP table
        link_local_ips = []
        try:
            result = subprocess.run(
                ['arp', '-an'], capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if '169.254.' in line and 'incomplete' not in line.lower():
                    start = line.find('(')
                    end = line.find(')')
                    if start != -1 and end != -1:
                        ip = line[start + 1:end]
                        if ip.startswith('169.254.') and not ip.endswith('.255'):
                            link_local_ips.append(ip)
        except Exception:
            pass

        if not link_local_ips:
            return []

        # Verify alive
        results = icmplib.multiping(
            link_local_ips, count=1, timeout=1,
            privileged=False, concurrent_tasks=50,
        )
        return [
            {'ip': r.address, 'label': '', 'domain': 'dante',
             'latency_ms': round(r.avg_rtt, 2)}
            for r in results if r.is_alive
        ]

    def _poll_devices(self, base_url, headers):
        """Fetch registered device IPs from the server, ping them locally,
        return results for the cloud to process."""
        import icmplib

        # Fetch the device list from the API
        try:
            resp = http_requests.get(
                f'{base_url}/devices/',
                headers=headers, timeout=10,
            )
            if resp.status_code != 200:
                return []
            device_ips = resp.json().get('devices', [])
        except Exception:
            return []

        if not device_ips:
            return []

        # Ping all registered devices locally
        try:
            results = icmplib.multiping(
                device_ips, count=1, timeout=2,
                privileged=False, concurrent_tasks=50,
            )
        except Exception:
            return []

        return [
            {'ip': r.address, 'is_alive': r.is_alive,
             'latency_ms': round(r.avg_rtt, 2) if r.is_alive else None}
            for r in results
        ]
