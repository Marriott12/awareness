from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


class Command(BaseCommand):
    help = 'Debug helper: create admin, login via client, and fetch dashboard home to show response and redirect location'

    def handle(self, *args, **options):
        User = get_user_model()
        admin, created = User.objects.get_or_create(username='__debug_admin__', defaults={'email': 'x@x.com'})
        admin.set_password('adminpass')
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

        c = Client()
        ok = c.login(username='__debug_admin__', password='adminpass')
        print('login ok', ok)
        resp = c.get(reverse('dashboard:home'))
        print('status_code', resp.status_code)
        print('redirect:', resp.get('Location'))
        print('cookies:', c.cookies.items())