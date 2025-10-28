from django.apps import AppConfig


class PlannerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'planner'

    def ready(self):
        """
        Import signals when the app is ready.
        This ensures the signal receivers are registered.
        """
        import planner.signals