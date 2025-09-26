# ...existing code... (no unused imports)
from django.contrib.auth.views import LoginView
from django.urls import reverse
from django.conf import settings
from django.contrib.auth.models import Group


class RoleLoginView(LoginView):
    """Custom login view that redirects users to different dashboards based on role.

    - Admins (is_staff or is_superuser) -> admin dashboard
    - Regular users -> user dashboard
    """

    def get_success_url(self):
        user = self.request.user
        # Configurable targets via settings
        admin_target = getattr(settings, "AWARENESS_ADMIN_DASHBOARD", "dashboard:admin")
        soldier_target = getattr(
            settings, "AWARENESS_SOLDIER_DASHBOARD", "dashboard:home"
        )

        # admin/staff -> admin dashboard
        if user.is_active and (user.is_staff or user.is_superuser):
            return reverse(admin_target)

        # If the user is in a 'Soldier' group, send to soldier target
        try:
            if Group.objects.filter(name="Soldier", user=user).exists():
                return reverse(soldier_target)
        except Exception:
            # If group checks fail for some reason, fall back to default
            pass

        # default -> user dashboard
        return reverse("dashboard:home")


# Create your views here.
