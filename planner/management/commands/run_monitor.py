"""
Network Health Monitor polling engine.

Run with: python manage.py run_monitor --project-id <N> [--interval <seconds>]

The command creates or resumes a MonitorSession, then spawns a daemon thread
that pings all active DiscoveredDevice records via ICMP every --interval seconds.
State transitions are recorded as DeviceEvent rows (OFFLINE at N=3 failures,
ONLINE on recovery). Press Ctrl+C to stop cleanly.
"""
import threading
import time
import signal

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone


class Command(BaseCommand):
    help = 'Run the network health monitor polling engine'

    def add_arguments(self, parser):
        parser.add_argument('--project-id', type=int, required=True,
                            help='Project ID to monitor')
        parser.add_argument('--interval', type=int, default=10,
                            help='Poll interval in seconds (default: 10)')

    def handle(self, *args, **options):
        project_id = options['project_id']
        interval = options['interval']
        stop_event = threading.Event()

        # Validate project exists
        from planner.models import Project
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Project {project_id} does not exist'))
            return

        # Create or resume monitor session
        from planner.models import MonitorSession, DeviceEvent
        session, created = MonitorSession.objects.get_or_create(
            project=project, ended_at__isnull=True,
            defaults={'started_at': timezone.now()}
        )
        if created:
            DeviceEvent.objects.create(
                session=session,
                event_type='MONITOR_STARTED',
                details={'project_id': project_id, 'interval': interval},
            )
            self.stdout.write(self.style.SUCCESS(
                f'Monitor session {session.pk} started for project "{project.name}" '
                f'(interval={interval}s)'
            ))
        else:
            self.stdout.write(
                f'Resuming existing session {session.pk} for project "{project.name}"'
            )

        def _record_poll(target, is_up, latency_ms, sess):
            """Write PollResult and update consecutive_failures. Fire alert at N=3."""
            from planner.models import PollResult, DeviceEvent as DE

            PollResult.objects.create(
                device=target,
                session=sess,
                is_reachable=is_up,
                latency_ms=latency_ms,
            )

            prev_state = target.last_known_state

            if is_up:
                if prev_state != 'online':
                    DE.objects.create(
                        device=target, session=sess,
                        event_type='ONLINE',
                        details={'latency_ms': latency_ms},
                    )
                target.consecutive_failures = 0
                target.last_known_state = 'online'
                target.last_seen = timezone.now()
            else:
                target.consecutive_failures = (target.consecutive_failures or 0) + 1
                if target.consecutive_failures == 3:
                    target.last_known_state = 'offline'
                    DE.objects.create(
                        device=target, session=sess,
                        event_type='OFFLINE',
                        details={'consecutive_failures': target.consecutive_failures},
                    )

            target.save(update_fields=['consecutive_failures', 'last_known_state', 'last_seen'])

        def icmp_poller():
            import icmplib
            from planner.models import DiscoveredDevice

            while not stop_event.is_set():
                close_old_connections()

                targets = list(
                    DiscoveredDevice.objects.filter(
                        project_id=project_id, is_active=True
                    )
                )

                if targets:
                    ips = [t.ip_address for t in targets]
                    try:
                        results = icmplib.multiping(
                            ips, count=1, timeout=2,
                            privileged=False, concurrent_tasks=50
                        )
                    except Exception as e:
                        self.stderr.write(self.style.WARNING(
                            f'ICMP poll error: {e}'
                        ))
                        stop_event.wait(timeout=interval)
                        continue

                    ip_map = {r.address: r for r in results}
                    for target in targets:
                        result = ip_map.get(target.ip_address)
                        is_up = result.is_alive if result else False
                        latency = result.avg_rtt if result and result.is_alive else None
                        _record_poll(target, is_up, latency, session)

                stop_event.wait(timeout=interval)

        from planner.models import DiscoveredDevice
        active_count = DiscoveredDevice.objects.filter(
            project_id=project_id, is_active=True
        ).count()

        t = threading.Thread(target=icmp_poller, daemon=True, name='ICMPPoller')
        t.start()
        self.stdout.write(self.style.SUCCESS(
            f'ICMP poller thread started. Polling {active_count} active devices.'
        ))
        self.stdout.write('Press Ctrl+C to stop.')

        try:
            stop_event.wait()
        except KeyboardInterrupt:
            self.stdout.write('\nShutting down...')
            stop_event.set()
            session.ended_at = timezone.now()
            session.save(update_fields=['ended_at'])
            self.stdout.write(self.style.SUCCESS('Monitor stopped. Session ended.'))
