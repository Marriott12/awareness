"""Generate synthetic endpoint interaction events for research evaluation.

This command creates realistic endpoint telemetry (USB insertions, software execution)
to support HLP-03 (Endpoint Interaction Control) evaluation as specified in the
research proposal Appendix B (Synthetic Dataset Specification).
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from policy.models import HumanLayerEvent
import random
from django.utils import timezone


class Command(BaseCommand):
    help = 'Generate synthetic endpoint interaction events for research evaluation'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=5, help='Number of users')
        parser.add_argument('--events', type=int, default=50, help='Events per user')
        parser.add_argument('--violation-rate', type=float, default=0.15, help='Violation probability (0.0-1.0)')

    def handle(self, *args, **options):
        users = list(User.objects.all()[:options['users']])
        if not users:
            self.stderr.write('No users found. Run populate_data first.')
            return

        usb_devices = [
            {'type': 'USB_MASS_STORAGE', 'vendor': 'SanDisk', 'authorized': True},
            {'type': 'USB_MASS_STORAGE', 'vendor': 'Kingston', 'authorized': True},
            {'type': 'USB_MASS_STORAGE', 'vendor': 'Unknown', 'authorized': False},
            {'type': 'USB_HID', 'vendor': 'Logitech', 'authorized': True},
            {'type': 'USB_HID', 'vendor': 'Microsoft', 'authorized': True},
        ]

        software_processes = [
            {'name': 'notepad.exe', 'prohibited': False},
            {'name': 'cmd.exe', 'prohibited': False},
            {'name': 'powershell.exe', 'prohibited': False},
            {'name': 'outlook.exe', 'prohibited': False},
            {'name': 'chrome.exe', 'prohibited': False},
            {'name': 'putty.exe', 'prohibited': True},
            {'name': 'teamviewer.exe', 'prohibited': True},
            {'name': 'torrent.exe', 'prohibited': True},
            {'name': 'wireshark.exe', 'prohibited': True},
        ]

        total_events = 0
        violation_count = 0

        for user in users:
            for i in range(options['events']):
                event_type = random.choice(['usb', 'usb', 'software'])

                if event_type == 'usb':
                    device = random.choice(usb_devices)
                    is_violation = not device['authorized'] and random.random() < options['violation_rate']
                    
                    HumanLayerEvent.objects.create(
                        user=user,
                        event_type='other',
                        source='endpoint.usb',
                        summary='usb_device_inserted',
                        details={
                            'device_type': device['type'],
                            'vendor': device['vendor'],
                            'device_id': f"VID_{random.randint(1000,9999)}_PID_{random.randint(1000,9999)}",
                            'authorized': device['authorized'],
                        },
                        timestamp=timezone.now() - timezone.timedelta(hours=random.randint(0, 168))
                    )

                    if is_violation:
                        violation_count += 1
                        self.stdout.write(self.style.WARNING(
                            f'Violation: {user.username} - Unauthorized USB ({device["vendor"]})'
                        ))
                else:
                    software = random.choice(software_processes)
                    is_violation = software['prohibited'] and random.random() < options['violation_rate']

                    HumanLayerEvent.objects.create(
                        user=user,
                        event_type='other',
                        source='endpoint.process',
                        summary='software_executed',
                        details={
                            'process_name': software['name'],
                            'prohibited': software['prohibited'],
                            'path': f"C:\\Program Files\\{software['name']}",
                        },
                        timestamp=timezone.now() - timezone.timedelta(hours=random.randint(0, 168))
                    )

                    if is_violation:
                        violation_count += 1
                        self.stdout.write(self.style.WARNING(
                            f'Violation: {user.username} - Prohibited software ({software["name"]})'
                        ))

                total_events += 1

        self.stdout.write(self.style.SUCCESS(
            f'Generated {total_events} endpoint events ({violation_count} violations, {violation_count/total_events*100:.1f}%)'
        ))
