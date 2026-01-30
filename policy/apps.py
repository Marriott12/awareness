from django.apps import AppConfig


class PolicyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'policy'

    def ready(self):
        # Wire telemetry and signal handlers (auth, violations, optional quiz/training)
        try:
            # Importing this module registers signal receivers
            from . import telemetry_signals  # noqa: F401
        except Exception:
            # Keep app import-safe if optional apps/models are missing
            import logging

            logging.getLogger(__name__).exception('Failed to import policy.telemetry_signals')
