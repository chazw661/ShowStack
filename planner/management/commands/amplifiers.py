from django.core.management.base import BaseCommand
from planner.models import AmplifierProfile

class Command(BaseCommand):
    help = 'Populate L\'Acoustics amplifier profiles'

    def handle(self, *args, **kwargs):
        profiles = [
            # L'Acoustics LA Series
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA12X',
                'channels': 4,
                'idle_power_watts': 200,
                'rated_power_watts': 3300,
                'peak_power_watts': 6600,
                'max_power_watts': 12000,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.85,
                'rack_units': 2,
                'weight_kg': 21
            },
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA8',
                'channels': 4,
                'idle_power_watts': 150,
                'rated_power_watts': 1800,
                'peak_power_watts': 3600,
                'max_power_watts': 7400,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.85,
                'rack_units': 2,
                'weight_kg': 15.5
            },
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA4X',
                'channels': 4,
                'idle_power_watts': 100,
                'rated_power_watts': 1000,
                'peak_power_watts': 2000,
                'max_power_watts': 3200,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.85,
                'rack_units': 1,
                'weight_kg': 6.7
            },
        ]
        
        for profile_data in profiles:
            profile, created = AmplifierProfile.objects.get_or_create(
                manufacturer=profile_data['manufacturer'],
                model=profile_data['model'],
                defaults=profile_data
            )
            if created:
                self.stdout.write(f"Created {profile.manufacturer} {profile.model}")
            else:
                self.stdout.write(f"{profile.manufacturer} {profile.model} already exists")