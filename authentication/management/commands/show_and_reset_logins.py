from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = "List all users and reset passwords for admin and normal user accounts."

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.all()
        if not users:
            self.stdout.write(self.style.ERROR("No users found in the database."))
            return
        self.stdout.write("\nUsers in the database:")
        for u in users:
            self.stdout.write(f"- username: {u.username}, email: {u.email}, is_active: {u.is_active}, is_staff: {u.is_staff}, is_superuser: {u.is_superuser}")
        # Reset password for first admin and first normal user
        admin = users.filter(is_staff=True, is_superuser=True).first()
        user = users.filter(is_staff=False, is_superuser=False).first()
        if admin:
            admin.set_password("Admin2025!")
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Admin user '{admin.username}' password reset to: Admin2025!"))
        if user:
            user.set_password("User2025!")
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Normal user '{user.username}' password reset to: User2025!"))
        if not admin and not user:
            self.stdout.write(self.style.WARNING("No admin or normal user found to reset password."))
