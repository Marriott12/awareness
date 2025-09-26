from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse


class LoginRedirectTests(TestCase):
    def setUp(self):
        User = get_user_model()
        # create admin user
        self.admin = User.objects.create_user("admin", "admin@example.com", "password")
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()

        # create soldier user and add to Soldier group
        self.soldier = User.objects.create_user(
            "soldier", "soldier@example.com", "password"
        )
        soldier_group, _ = Group.objects.get_or_create(name="Soldier")
        self.soldier.groups.add(soldier_group)

    def test_admin_redirects_to_admin_dashboard(self):
        resp = self.client.post(
            reverse("login"), {"username": "admin", "password": "password"}
        )
        # login should redirect (302)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("dashboard:admin"), resp["Location"])

    def test_soldier_redirects_to_user_dashboard(self):
        resp = self.client.post(
            reverse("login"), {"username": "soldier", "password": "password"}
        )
        self.assertEqual(resp.status_code, 302)
        # default user dashboard is dashboard:home
        self.assertIn(reverse("dashboard:home"), resp["Location"])
