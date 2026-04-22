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
import signal
import ipaddress
import subprocess
import json

import requests as http_requests  # renamed to avoid shadowing Django requests

from django.core.management.base import BaseCommand


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

        # ── Step 3: Polling loop ──
        self.stdout.write(f'\nStarting ICMP polling (interval={interval}s). Press Ctrl+C to stop.')

        running = True

        def handle_signal(sig, frame):
            nonlocal running
            running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while running:
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
                        # Print state changes
                        for ev in events:
                            etype = ev.get('type', '')
                            name = ev.get('device_name', ev.get('device_id', ''))
                            if etype == 'OFFLINE':
                                self.stderr.write(self.style.ERROR(f'  ✗ {name} OFFLINE'))
                            elif etype == 'ONLINE':
                                self.stdout.write(self.style.SUCCESS(f'  ✓ {name} ONLINE'))
                    else:
                        self.stderr.write(self.style.WARNING(
                            f'Poll push failed ({resp.status_code})'
                        ))
                except http_requests.ConnectionError:
                    self.stderr.write(self.style.WARNING(
                        'Lost connection to ShowStack. Retrying next cycle...'
                    ))
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f'Error: {e}'))

            # Wait for next cycle
            for _ in range(interval * 10):  # check running every 0.1s
                if not running:
                    break
                time.sleep(0.1)

        # ── Shutdown ──
        self.stdout.write('\nShutting down...')
        try:
            http_requests.post(f'{base_url}/stop/', headers=headers,
                               json={}, timeout=5)
        except Exception:
            pass
        self.stdout.write(self.style.SUCCESS('Monitor agent stopped.'))

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
                        d['domain'] = 'dante'  # link-local devices are typically Dante
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
        """Ping all active devices for this project and return results."""
        import icmplib

        # Get device list from the server
        # We could cache this, but for now query every cycle is fine
        try:
            # Use the scan-results endpoint's GET behavior... actually we need
            # a device list. For now, we'll keep a local cache updated on scan.
            # The agent maintains its own device list from the last scan.
            pass
        except Exception:
            pass

        # For now, ping all IPs we know about from the local ARP/scan cache
        # In production, we'd fetch the device list from the API
        # For the MVP, re-scan to get current device list
        all_ips = []
        import netifaces

        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET not in addrs:
                continue
            for addr in addrs[netifaces.AF_INET]:
                ip = addr['addr']
                if ip.startswith('127.'):
                    continue
                # For link-local, use ARP discovery
                if ip.startswith('169.254.'):
                    discovered = self._discover_link_local()
                    all_ips.extend([d['ip'] for d in discovered])

        # Also get the known device list from the last scan results
        # by querying what we've already registered
        # For now, use ARP-discovered IPs
        if not all_ips:
            return []

        # Deduplicate
        all_ips = list(set(all_ips))

        try:
            results = icmplib.multiping(
                all_ips, count=1, timeout=2,
                privileged=False, concurrent_tasks=50,
            )
        except Exception:
            return []

        return [
            {'ip': r.address, 'is_alive': r.is_alive,
             'latency_ms': round(r.avg_rtt, 2) if r.is_alive else None}
            for r in results
        ]
