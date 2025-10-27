from django.core.management.base import BaseCommand
from planner.models import AmplifierProfile

class Command(BaseCommand):
    help = 'Load L\'Acoustics amplifier profiles into the database'

    def handle(self, *args, **options):
        amplifiers = [
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA8',
                'idle_power_watts': 190,
                'rated_power_watts': 1100,
                'peak_power_watts': 2200,
                'max_power_watts': 8800,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.92,
                'channels': 4,
                'rack_units': 2,
                'weight_kg': 11.5,
                'notes': '4 channels, 2200W @ 8Ω per channel pair'
            },
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA4X',
                'idle_power_watts': 140,
                'rated_power_watts': 500,
                'peak_power_watts': 1000,
                'max_power_watts': 4000,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.93,
                'channels': 4,
                'rack_units': 1,
                'weight_kg': 6.6,
                'notes': '4 channels, 1000W @ 8Ω per channel, 1RU'
            },
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA12X',
                'idle_power_watts': 240,
                'rated_power_watts': 1500,
                'peak_power_watts': 3000,
                'max_power_watts': 12000,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.93,
                'channels': 4,
                'rack_units': 2,
                'weight_kg': 15.9,
                'notes': '4 channels, 3300W @ 2.7Ω per channel, flagship model'
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for amp_data in amplifiers:
            amp, created = AmplifierProfile.objects.update_or_create(
                manufacturer=amp_data['manufacturer'],
                model=amp_data['model'],
                defaults=amp_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created: {amp.manufacturer} {amp.model}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated: {amp.manufacturer} {amp.model}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: {created_count} created, {updated_count} updated'
            )
        )