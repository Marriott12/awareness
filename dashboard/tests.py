from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


User = get_user_model()


class AdminDashboardAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass"
        )
        self.user = User.objects.create_user(
            username="user", email="user@example.com", password="userpass"
        )

    def test_admin_sees_admin_dashboard(self):
        self.client.login(username="admin", password="adminpass")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin_dashboard.html")

    def test_regular_user_gets_user_dashboard(self):
        self.client.login(username="user", password="userpass")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard.html")


"""Additional dashboard tests can go here."""
