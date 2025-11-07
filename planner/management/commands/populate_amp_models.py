from django.core.management.base import BaseCommand
from planner.models import AmpModel


class Command(BaseCommand):
    help = 'Populate standard amplifier models'

    def handle(self, *args, **kwargs):
        amp_models = [
            # L'Acoustics
            {
                'manufacturer': 'L-Acoustics',
                'model_name': 'LA12X',
                'channel_count': 4,
                'has_analog_inputs': False,
                'has_aes_inputs': True,
                'has_avb_inputs': True,
                'nl4_connector_count': 2,
                'cacom_output_count': 0,
            },
            {
                'manufacturer': 'L-Acoustics',
                'model_name': 'LA8',
                'channel_count': 4,
                'has_analog_inputs': False,
                'has_aes_inputs': True,
                'has_avb_inputs': True,
                'nl4_connector_count': 2,
                'cacom_output_count': 0,
            },
            {
                'manufacturer': 'L-Acoustics',
                'model_name': 'LA4X',
                'channel_count': 4,
                'has_analog_inputs': False,
                'has_aes_inputs': True,
                'has_avb_inputs': True,
                'nl4_connector_count': 1,
                'cacom_output_count': 0,
            },
            {
                'manufacturer': 'L-Acoustics',
                'model_name': 'LA2Xi',
                'channel_count': 2,
                'has_analog_inputs': False,
                'has_aes_inputs': True,
                'has_avb_inputs': True,
                'nl4_connector_count': 1,
                'cacom_output_count': 0,
            },
            # Powersoft
            {
                'manufacturer': 'Powersoft',
                'model_name': 'X4',
                'channel_count': 4,
                'has_analog_inputs': True,
                'has_aes_inputs': True,
                'has_avb_inputs': False,
                'nl4_connector_count': 2,
                'cacom_output_count': 0,
            },
            {
                'manufacturer': 'Powersoft',
                'model_name': 'X8',
                'channel_count': 8,
                'has_analog_inputs': True,
                'has_aes_inputs': True,
                'has_avb_inputs': False,
                'nl4_connector_count': 2,
                'cacom_output_count': 0,
            },
            {
                'manufacturer': 'Powersoft',
                'model_name': 'K10',
                'channel_count': 2,
                'has_analog_inputs': True,
                'has_aes_inputs': True,
                'has_avb_inputs': False,
                'nl4_connector_count': 2,
                'cacom_output_count': 0,
            },
            # Meyer Sound
            {
                'manufacturer': 'Meyer Sound',
                'model_name': 'Galileo 616',
                'channel_count': 16,
                'has_analog_inputs': True,
                'has_aes_inputs': True,
                'has_avb_inputs': False,
                'nl4_connector_count': 0,
                'cacom_output_count': 0,
            },
            # d&b audiotechnik
            {
                'manufacturer': 'd&b audiotechnik',
                'model_name': 'D80',
                'channel_count': 4,
                'has_analog_inputs': True,
                'has_aes_inputs': True,
                'has_avb_inputs': False,
                'nl4_connector_count': 2,
                'cacom_output_count': 0,
            },
            {
                'manufacturer': 'd&b audiotechnik',
                'model_name': 'D20',
                'channel_count': 4,
                'has_analog_inputs': True,
                'has_aes_inputs': True,
                'has_avb_inputs': False,
                'nl4_connector_count': 2,
                'cacom_output_count': 0,
            },
        ]

        created_count = 0
        skipped_count = 0

        for amp_data in amp_models:
            obj, created = AmpModel.objects.get_or_create(
                manufacturer=amp_data['manufacturer'],
                model_name=amp_data['model_name'],
                defaults=amp_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Created {amp_data["manufacturer"]} {amp_data["model_name"]}'
                    )
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'- Skipped {amp_data["manufacturer"]} {amp_data["model_name"]} (already exists)'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone! Created {created_count} amp models, skipped {skipped_count} existing.'
            )
        )