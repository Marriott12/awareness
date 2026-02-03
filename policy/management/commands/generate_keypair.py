"""Management command to generate RSA or Ed25519 keypair for signing.

Usage:
    python manage.py generate_keypair [--key-type rsa|ed25519] [--output-dir /path]
"""
from django.core.management.base import BaseCommand
from policy.crypto_utils import generate_keypair
import os


class Command(BaseCommand):
    help = 'Generate RSA or Ed25519 keypair for cryptographic signing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--key-type',
            default='rsa',
            choices=['rsa', 'ed25519'],
            help='Type of key to generate (default: rsa)'
        )
        parser.add_argument(
            '--output-dir',
            default='.',
            help='Directory to save keys (default: current directory)'
        )

    def handle(self, *args, **options):
        key_type = options['key_type']
        output_dir = options['output_dir']

        if not os.path.exists(output_dir):
            self.stdout.write(self.style.ERROR(f'Output directory does not exist: {output_dir}'))
            return

        self.stdout.write(f'Generating {key_type.upper()} keypair...')
        
        try:
            generate_keypair(output_dir=output_dir, key_type=key_type)
            self.stdout.write(self.style.SUCCESS(f'✓ Keypair generated successfully in {output_dir}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to generate keypair: {e}'))
            raise
