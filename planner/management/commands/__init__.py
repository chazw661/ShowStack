

from django.core.management.base import BaseCommand
from planner.models import AmplifierProfile

class Command(BaseCommand):
    help = 'Load L\'Acoustics amplifier profiles into the database'

    def handle(self, *args, **options):
        # L'Acoustics amplifier specifications
        # Power values based on typical measurements and manufacturer specs
        
        amplifiers = [
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA8',
                'idle_power_watts': 190,  # Idle consumption
                'rated_power_watts': 1100,  # 1/8 power (typical program)
                'peak_power_watts': 2200,  # 1/3 power (heavy program)
                'max_power_watts': 8800,  # 8 x 1100W @ 8Ω
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
                'rated_power_watts': 500,  # 1/8 power
                'peak_power_watts': 1000,  # 1/3 power
                'max_power_watts': 4000,  # 4 x 1000W @ 8Ω
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
                'rated_power_watts': 1500,  # 1/8 power
                'peak_power_watts': 3000,  # 1/3 power
                'max_power_watts': 12000,  # 4 x 3300W @ 2.7Ω
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.93,
                'channels': 4,
                'rack_units': 2,
                'weight_kg': 15.9,
                'notes': '4 channels, 3300W @ 2.7Ω per channel, flagship model'
            },
            {
                'manufacturer': "L'Acoustics",
                'model': 'LA2Xi',
                'idle_power_watts': 120,
                'rated_power_watts': 400,  # 1/8 power
                'peak_power_watts': 800,  # 1/3 power
                'max_power_watts': 3200,  # 2 x 1600W @ 8Ω
                'nominal_voltage': 208,
                'power_factor': 0.94,
                'efficiency': 0.91,
                'channels': 2,
                'rack_units': 1,
                'weight_kg': 6.0,
                'notes': '2 channels, 1600W @ 8Ω per channel, compact 1RU'
            },
            # Adding some other common pro audio amps for comparison
            {
                'manufacturer': 'Powersoft',
                'model': 'K10',
                'idle_power_watts': 150,
                'rated_power_watts': 1200,
                'peak_power_watts': 2400,
                'max_power_watts': 9600,  # 2 x 4800W @ 2Ω
                'nominal_voltage': 208,
                'power_factor': 0.99,  # With PFC
                'efficiency': 0.95,
                'channels': 2,
                'rack_units': 2,
                'weight_kg': 12.0,
                'notes': '2 channels, 4800W @ 2Ω per channel, with PFC'
            },
            {
                'manufacturer': 'Powersoft',
                'model': 'X4',
                'idle_power_watts': 100,
                'rated_power_watts': 800,
                'peak_power_watts': 1600,
                'max_power_watts': 6400,  # 4 x 1600W @ 2Ω
                'nominal_voltage': 208,
                'power_factor': 0.99,
                'efficiency': 0.94,
                'channels': 4,
                'rack_units': 1,
                'weight_kg': 8.8,
                'notes': '4 channels, 1600W @ 2Ω per channel, 1RU DSP amp'
            },
            {
                'manufacturer': 'd&b audiotechnik',
                'model': 'D80',
                'idle_power_watts': 200,
                'rated_power_watts': 1600,
                'peak_power_watts': 3200,
                'max_power_watts': 12800,  # 4 x 3200W @ 4Ω
                'nominal_voltage': 208,
                'power_factor': 0.96,
                'efficiency': 0.93,
                'channels': 4,
                'rack_units': 2,
                'weight_kg': 14.0,
                'notes': '4 channels, 3200W @ 4Ω per channel'
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