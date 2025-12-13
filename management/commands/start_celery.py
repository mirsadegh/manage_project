# management/commands/start_celery.py

from django.core.management.base import BaseCommand
import subprocess
import sys

class Command(BaseCommand):
    help = 'Start Celery worker and beat scheduler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--worker-only',
            action='store_true',
            help='Start only the worker (no beat scheduler)',
        )
        parser.add_argument(
            '--beat-only',
            action='store_true',
            help='Start only the beat scheduler',
        )

    def handle(self, *args, **options):
        if options['worker_only']:
            self.stdout.write('Starting Celery worker...')
            subprocess.run([
                'celery', '-A', 'project_management',
                'worker', '-l', 'info'
            ])
        elif options['beat_only']:
            self.stdout.write('Starting Celery beat...')
            subprocess.run([
                'celery', '-A', 'project_management',
                'beat', '-l', 'info',
                '--scheduler', 'django_celery_beat.schedulers:DatabaseScheduler'
            ])
        else:
            self.stdout.write('Starting Celery worker with beat...')
            subprocess.run([
                'celery', '-A', 'project_management',
                'worker', '-B', '-l', 'info'
            ])