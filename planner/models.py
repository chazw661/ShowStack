from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Console(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class ConsoleInput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    dante_number = models.CharField(max_length=3, blank=True, null=True)
    input_ch = models.CharField(max_length=10, blank=True, null=True)
    source = models.CharField(max_length=100, blank=True, null=True)
    group = models.CharField(max_length=100, blank=True, null=True)
    dca = models.CharField(max_length=100, blank=True, null=True)
    mute = models.CharField(max_length=100, blank=True, null=True)
    direct_out = models.CharField(max_length=100, blank=True, null=True)
    omni_in = models.CharField(max_length=100, blank=True, null=True)
    omni_out = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        if self.dante_number:
            return f"Input {self.dante_number}"
        elif self.input_ch:
            return f"Input {self.input_ch}"
        else:
            return f"Input {self.pk or 'New'}"
        


class ConsoleAuxOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    aux_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100, blank=True, null=True)
    mono_stereo = models.CharField(
        max_length=10,
        choices=[("Mono", "Mono"), ("Stereo", "Stereo")],
        blank=True,
        null=True
    )
    bus_type = models.CharField(
        max_length=10,
        choices=[("Fixed", "Fixed"), ("Variable", "Variable")],
        blank=True,
        null=True
    )
    omni_in = models.CharField(max_length=100, blank=True)
    omni_out = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Aux {self.aux_number} - {self.name}"


class ConsoleMatrixOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    matrix_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100, blank=True, null=True)
    mono_stereo = models.CharField(
    max_length=10,
    choices=[("Mono", "Mono"), ("Stereo", "Stereo")],
    blank=True,
    null=True
)
    destination = models.CharField(max_length=100, blank=True, null=True)
    omni_out = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Matrix {self.matrix_number} - {self.name}"
    


    # planner/models.py

from django.db import models

class Device(models.Model):
    name = models.CharField(max_length=200)
    input_count = models.PositiveIntegerField(default=0)
    output_count = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "I/O Device"
        verbose_name_plural = "I/O Devices"
    

class DeviceInput(models.Model):
    device = models.ForeignKey(Device, related_name="inputs", on_delete=models.CASCADE)
    input_number = models.IntegerField(blank=True, null=True)
    signal_name = models.CharField(max_length=100)  # e.g. "Wless 1 Analogue"
    console_input = models.ForeignKey(
        'ConsoleInput', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        related_name='device_inputs'
    )

    def __str__(self):
     return f"Input {self.input_number or 'N/A'}: {self.signal_name or 'No signal'}"
    
    class Meta:
        verbose_name = "I/O Device Input"
        verbose_name_plural = "I/O Device Inputs"
    
class DeviceOutput(models.Model):
    device = models.ForeignKey(Device, related_name="outputs", on_delete=models.CASCADE)
    output_number = models.IntegerField(blank=True, null=True) 
    signal_name = models.CharField(max_length=100, blank=True, null=True)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'model__in': ('consoleauxoutput', 'consolematrixoutput')}
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    console_output = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return f"Output {self.output_number or 'N/A'}: {self.signal_name or 'No signal'}"
    
    class Meta:
        verbose_name = "I/O Device Output"
        verbose_name_plural = "I/O Device Outputs"
    




    #-------Amps--------


# Updated models based on spreadsheet analysis
# Add these models to your existing models.py file

class Location(models.Model):
    """Physical locations where amplifiers are deployed"""
    name = models.CharField(max_length=100, help_text="e.g., HL LA Racks, HR LA Racks, Monitor World")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        ordering = ['name']


class AmpModel(models.Model):
    """Predefined amplifier models with specifications"""
    manufacturer = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    channel_count = models.IntegerField()
    
    # Input types available
    has_analog_inputs = models.BooleanField(default=True)
    has_aes_inputs = models.BooleanField(default=False)
    has_avb_inputs = models.BooleanField(default=False)
    
    # NL4 Configuration
    nl4_connector_count = models.IntegerField(
        default=0, 
        choices=[(0, 'None'), (1, '1 NL4'), (2, '2 NL4')]
    )
    
    # Cacom configuration  
    cacom_output_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['manufacturer', 'model_name']
        unique_together = ['manufacturer', 'model_name']
        verbose_name = "Amplifier Model"
        verbose_name_plural = "Amplifier Models"
    
    def __str__(self):
        return f"{self.manufacturer} {self.model_name}"


class Amp(models.Model):
    """Individual amplifier instance"""
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='amps')
    amp_model = models.ForeignKey(AmpModel, on_delete=models.PROTECT, 
        null=True,  
        blank=True )
       
    name = models.CharField(
        max_length=100, 
        help_text="Unique identifier (e.g., 'LA12X-1', 'Stage Left 1')"
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    # NL4 Connector A (if present)
    nl4_a_pair_1 = models.CharField(
        max_length=50, blank=True, 
        verbose_name="NL4-A Pair 1 +/-",
        help_text="e.g., 'Ch1/Ch2' or 'Left/Right'"
    )
    nl4_a_pair_2 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL4-A Pair 2 +/-", 
        help_text="e.g., 'Ch3/Ch4' or 'Sub L/Sub R'"
    )
    
    # NL4 Connector B (if present)
    nl4_b_pair_1 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL4-B Pair 1 +/-",
        help_text="e.g., 'Ch5/Ch6'"
    )
    nl4_b_pair_2 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL4-B Pair 2 +/-",
        help_text="e.g., 'Ch7/Ch8'"
    )
    
    # Cacom outputs (if present)
    cacom_1_assignment = models.CharField(max_length=100, blank=True, verbose_name="Cacom 1")
    cacom_2_assignment = models.CharField(max_length=100, blank=True, verbose_name="Cacom 2")
    cacom_3_assignment = models.CharField(max_length=100, blank=True, verbose_name="Cacom 3")
    cacom_4_assignment = models.CharField(max_length=100, blank=True, verbose_name="Cacom 4")
    
    class Meta:
        ordering = ['location', 'ip_address', 'name']
        verbose_name = "Amplifier"
        verbose_name_plural = "Amplifiers"
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_model = None
        
        if not is_new:
            try:
                old_amp = Amp.objects.get(pk=self.pk)
                old_model = old_amp.amp_model
            except Amp.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Auto-create/update channels when amp is created or model changes
        if is_new or (old_model and old_model != self.amp_model):
            self.setup_channels()
    
    def setup_channels(self):
        """Create or adjust channels based on amp model"""
        current_count = self.channels.count()
        target_count = self.amp_model.channel_count
        
        if current_count < target_count:
            # Add missing channels
            for i in range(current_count + 1, target_count + 1):
                AmpChannel.objects.create(
                    amp=self,
                    channel_number=i,
                    channel_name=f"Ch {i}"
                )
        elif current_count > target_count:
            # Remove extra channels
            self.channels.filter(channel_number__gt=target_count).delete()
    
    def __str__(self):
        return f"{self.name} - {self.amp_model}"


class AmpChannel(models.Model):
    """Individual channel within an amplifier"""
    amp = models.ForeignKey(Amp, on_delete=models.CASCADE, related_name='channels')
    channel_number = models.IntegerField()
    channel_name = models.CharField(max_length=100, default="")
    
    # Input source (only show relevant options based on amp model)
    avb_stream = models.ForeignKey(
        'P1Output',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'output_type': 'AVB'},
        verbose_name="AVB Stream",
        related_name='amp_channels'
    )
    aes_input = models.CharField(
        max_length=50, blank=True,
        verbose_name="AES Input",
        help_text="AES input assignment"
    )
    analog_input = models.CharField(
        max_length=50, blank=True,
        verbose_name="Analog Input",
        help_text="Analog input assignment"
    )
    
    class Meta:
        ordering = ['amp', 'channel_number']
        unique_together = ['amp', 'channel_number']
        verbose_name = "Amp Channel"
        verbose_name_plural = "Amp Channels"
    
    def __str__(self):
        return f"{self.amp.name} - Ch{self.channel_number}"



        # -------System Processors--------

# -------System Processors--------

class SystemProcessor(models.Model):
    """System processor devices for audio systems"""
    
    DEVICE_TYPE_CHOICES = [
        ('P1', "L'Acoustics P1"),
        ('GALAXY', 'Meyer GALAXY'),
    ]
    
    name = models.CharField(max_length=200, help_text="Device name/identifier")
    device_type = models.CharField(
        max_length=20,
        choices=DEVICE_TYPE_CHOICES,
        help_text="Type of system processor"
    )
    location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE, 
        related_name='system_processors',
        help_text="Physical location of device"
    )
    ip_address = models.GenericIPAddressField(
        blank=True, 
        null=True,
        help_text="Network IP address"
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_device_type_display()})"
    
    class Meta:
        verbose_name = "System Processor"
        verbose_name_plural = "System Processors"


# -------P1 Processor Models--------

# Update the P1Processor model in models.py
# -------P1 Processor Models--------

# -------P1 Processor Models--------

class P1Processor(models.Model):
    """L'Acoustics P1 Processor configuration tracking"""
    system_processor = models.OneToOneField(
        SystemProcessor,
        on_delete=models.CASCADE,
        related_name='p1_config'
    )
    
    notes = models.TextField(blank=True, null=True, help_text="Additional configuration notes")
    
    def __str__(self):
        return f"P1 Config - {self.system_processor.name}"
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Only create channels if this is a new P1 processor AND no channels exist yet
        if is_new and not self.inputs.exists() and not self.outputs.exists():
            self._create_default_channels()
    
    def _create_default_channels(self):
        """Create default P1 channels based on standard configuration"""
        # Create Inputs
        # 4 Analog inputs
        for i in range(1, 5):
            P1Input.objects.get_or_create(
                p1_processor=self,
                input_type='ANALOG',
                channel_number=i,
                defaults={'label': ''}  # Blank label
            )
        
        # 4 AES inputs  
        for i in range(1, 5):
            P1Input.objects.get_or_create(
                p1_processor=self,
                input_type='AES',
                channel_number=i,
                defaults={'label': ''}  # Blank label
            )
        
        # 8 AVB inputs
        for i in range(1, 9):
            P1Input.objects.get_or_create(
                p1_processor=self,
                input_type='AVB',
                channel_number=i,
                defaults={'label': ''}  # Blank label
            )
        
        # Create Outputs
        # 4 Analog outputs
        for i in range(1, 5):
            P1Output.objects.get_or_create(
                p1_processor=self,
                output_type='ANALOG',
                channel_number=i,
                defaults={'label': ''}  # Blank label
            )
        
        # 4 AES outputs
        for i in range(1, 5):
            P1Output.objects.get_or_create(
                p1_processor=self,
                output_type='AES',
                channel_number=i,
                defaults={'label': ''}  # Blank label
            )
        
        # 8 AVB outputs
        for i in range(1, 9):
            P1Output.objects.get_or_create(
                p1_processor=self,
                output_type='AVB',
                channel_number=i,
                defaults={'label': ''}  # Blank label
            )
    
    class Meta:
        verbose_name = "P1 Processor"
        verbose_name_plural = "P1 Processors"


class P1Input(models.Model):
    """P1 Input channel configuration"""
    INPUT_TYPES = [
        ('ANALOG', 'Analog'),
        ('AES', 'AES/EBU'),
        ('AVB', 'AVB'),
    ]
    
    p1_processor = models.ForeignKey(P1Processor, on_delete=models.CASCADE, related_name='inputs')
    input_type = models.CharField(max_length=10, choices=INPUT_TYPES)
    channel_number = models.PositiveIntegerField()
    label = models.CharField(max_length=100, blank=True, null=True, help_text="Channel label/name")
    
    # Origin for Analog and AES inputs only
    origin_device_output = models.ForeignKey(
        'DeviceOutput',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Source device output (for Analog/AES only)",
        related_name='p1_inputs'
    )
    
    class Meta:
        unique_together = ['p1_processor', 'input_type', 'channel_number']
        ordering = ['input_type', 'channel_number']
        verbose_name = "P1 Input"
        verbose_name_plural = "P1 Inputs"
    
    def __str__(self):
        return f"{self.get_input_type_display()} {self.channel_number} - {self.label or 'Unlabeled'}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        # AVB inputs should not have origin_device_output
        if self.input_type == 'AVB' and self.origin_device_output:
            raise ValidationError("AVB inputs should not have an origin device output")


class P1Output(models.Model):
    """P1 Output channel configuration"""
    OUTPUT_TYPES = [
        ('ANALOG', 'Analog'),
        ('AES', 'AES/EBU'),
        ('AVB', 'AVB'),
    ]
    
    BUS_CHOICES = [(i, f'Bus {i}') for i in range(1, 9)]  # Bus 1-8
    
    p1_processor = models.ForeignKey(P1Processor, on_delete=models.CASCADE, related_name='outputs')
    output_type = models.CharField(max_length=10, choices=OUTPUT_TYPES)
    channel_number = models.PositiveIntegerField()
    label = models.CharField(max_length=100, blank=True, null=True, help_text="Channel label/name")
    assigned_bus = models.IntegerField(choices=BUS_CHOICES, blank=True, null=True, help_text="Assigned bus (1-8)")
    
    class Meta:
        unique_together = ['p1_processor', 'output_type', 'channel_number']
        ordering = ['output_type', 'channel_number']
        verbose_name = "P1 Output"
        verbose_name_plural = "P1 Outputs"
    
    def __str__(self):
        bus_str = f" → Bus {self.assigned_bus}" if self.assigned_bus else ""
        return f"{self.get_output_type_display()} {self.channel_number} - {self.label or 'Unlabeled'}{bus_str}"
    

    #-------Galaxy Processor
# Add these to your models.py file after the P1Processor models

class GalaxyProcessor(models.Model):
    """Meyer GALAXY processor configuration"""
    system_processor = models.OneToOneField(
        SystemProcessor,
        on_delete=models.CASCADE,
        related_name='galaxy_config'
    )
    notes = models.TextField(blank=True, help_text="Configuration notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "GALAXY Processor"
        verbose_name_plural = "GALAXY Processors"
    
    def __str__(self):
        return f"GALAXY - {self.system_processor.name}"
    
    def save(self, *args, **kwargs):
        """Ensure this is only attached to GALAXY type processors"""
        if self.system_processor.device_type != 'GALAXY':
            self.system_processor.device_type = 'GALAXY'
            self.system_processor.save()
        super().save(*args, **kwargs)


class GalaxyInput(models.Model):
    """Input channel for Meyer GALAXY processor"""
    INPUT_TYPE_CHOICES = [
        ('ANALOG', 'Analog'),
        ('AES', 'AES/EBU'),
        ('AVB', 'AVB/Milan'),
    ]
    
    galaxy_processor = models.ForeignKey(
        GalaxyProcessor,
        on_delete=models.CASCADE,
        related_name='inputs'
    )
    input_type = models.CharField(max_length=10, choices=INPUT_TYPE_CHOICES)
    channel_number = models.PositiveIntegerField()
    label = models.CharField(max_length=100, blank=True, help_text="Channel label")
    origin_device_output = models.ForeignKey(
        'DeviceOutput',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='galaxy_inputs',
        help_text="Source device output for this input"
    )
    
    class Meta:
        ordering = ['input_type', 'channel_number']
        unique_together = [['galaxy_processor', 'input_type', 'channel_number']]
        verbose_name = "GALAXY Input"
        verbose_name_plural = "GALAXY Inputs"
    
    def __str__(self):
        return f"{self.get_input_type_display()} {self.channel_number}"


class GalaxyOutput(models.Model):
    """Output channel for Meyer GALAXY processor"""
    OUTPUT_TYPE_CHOICES = [
        ('ANALOG', 'Analog'),
        ('AES', 'AES/EBU'),
        ('AVB', 'AVB/Milan'),
    ]
    
    galaxy_processor = models.ForeignKey(
        GalaxyProcessor,
        on_delete=models.CASCADE,
        related_name='outputs'
    )
    output_type = models.CharField(max_length=10, choices=OUTPUT_TYPE_CHOICES)
    channel_number = models.PositiveIntegerField()
    label = models.CharField(max_length=100, blank=True, help_text="Channel label")
    assigned_bus = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Assigned bus number"
    )
    destination = models.CharField(
        max_length=100,
        blank=True,
        help_text="Output destination (e.g., amp name, speaker zone)"
    )
    
    class Meta:
        ordering = ['output_type', 'channel_number']
        unique_together = [['galaxy_processor', 'output_type', 'channel_number']]
        verbose_name = "GALAXY Output"
        verbose_name_plural = "GALAXY Outputs"
    
    def __str__(self):
        return f"{self.get_output_type_display()} {self.channel_number}"
            

#-----------PA Cable-------

     # Add these to your models.py file

# Add these models to your models.py file

class PAZone(models.Model):
    """User-defined PA zones"""
    name = models.CharField(
        max_length=20, 
        unique=True,
        help_text="Short zone code (e.g., HL, HR, FF1)"
    )
    description = models.CharField(
        max_length=100,
        help_text="Full description (e.g., House Left, Front Fill 1)"
    )
    location = models.ForeignKey(
        Location, 
        on_delete=models.CASCADE, 
        related_name='pa_zones',
        blank=True,
        null=True
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        help_text="Order in dropdown (lower numbers appear first)"
    )
    
    # Default zone types for reference
    ZONE_TYPE_CHOICES = [
        ('MAIN', 'Main Array'),
        ('SUB', 'Subwoofer'),
        ('FILL', 'Fill'),
        ('DELAY', 'Delay'),
        ('MONITOR', 'Monitor'),
        ('CUSTOM', 'Custom'),
    ]
    zone_type = models.CharField(
        max_length=20,
        choices=ZONE_TYPE_CHOICES,
        default='CUSTOM',
        help_text="Category of zone"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "PA Zone"
        verbose_name_plural = "PA Zones"
    
    def __str__(self):
        return f"{self.name} - {self.description}"
    
    @classmethod
    def create_default_zones(cls):
        """Create standard L'Acoustics zones - can be called from migration or admin"""
        default_zones = [
            ('HL', 'House Left', 'MAIN', 10),
            ('HR', 'House Right', 'MAIN', 20),
            ('HC', 'House Center', 'MAIN', 30),
            ('SL', 'Sub Left', 'SUB', 40),
            ('SR', 'Sub Right', 'SUB', 50),
            ('SC', 'Sub Center', 'SUB', 60),
            ('FF', 'Front Fill', 'FILL', 70),
            ('FF1', 'Front Fill 1', 'FILL', 71),
            ('FF2', 'Front Fill 2', 'FILL', 72),
            ('OFL', 'Out Fill Left', 'FILL', 80),
            ('OFR', 'Out Fill Right', 'FILL', 90),
            ('D1', 'Delay 1', 'DELAY', 100),
            ('D2', 'Delay 2', 'DELAY', 110),
            ('D3', 'Delay 3', 'DELAY', 120),
            ('LF', 'Lip Fill', 'FILL', 130),
            ('UB', 'Under Balcony', 'FILL', 140),
            ('BAL', 'Balcony', 'FILL', 150),
        ]
        
        for name, desc, zone_type, order in default_zones:
            cls.objects.get_or_create(
                name=name,
                defaults={
                    'description': desc,
                    'zone_type': zone_type,
                    'sort_order': order
                }
            )


class PACableSchedule(models.Model):
    """Simple PA Cable Schedule for L'Acoustics systems"""
    
    # Standard L'Acoustics cable types - matching spreadsheet with 150' added
    CABLE_TYPE_CHOICES = [
        ('NL4_JUMPER', 'NL4 Jumper'),
        ('NL_4' , 'NL 4'),
        ('CA-COM', 'CA-COM'),
        ('NL_8' , 'NL 8'),
        ('XLR' , 'XLR'),
        ('XLR_FAN' , 'XLR Fan'),
        ('AES_XLR', 'AES/EBU XLR'),
        ('L21-30', 'L21-30 Power'),
        ('EDISON_20_AMP' , 'Edison 20amp'),
    ]
    
    # Fan Out options
    FAN_OUT_CHOICES = [
        ('', 'None'),
        ('NL4_Y', 'NL4 Y'),
        ('NL4_COUPLER', 'NL4 Coupler'),
        ('DOFILL' , 'DOFill'),
        ('DOSUB' , 'DOSub'),
        ('CACOM COUPLER' , 'CACOM Coupler'),
        ('NL8_Y', 'NL8 Y'),
        ('NL8_COUPLER', 'NL8 Coupler'),
        ('NL4_TO_NL8', 'NL4 to NL8'),
        
    ]
    
    # Fields matching spreadsheet columns
    label = models.ForeignKey(
        PAZone,
        on_delete=models.PROTECT,
        verbose_name="Label",
        help_text="Zone label",
        related_name='cables',
        null=True,  # Add this temporarily
        blank=True,  # Add this temporarily
    )
    
    destination = models.CharField(
        max_length=50,
        verbose_name="Destination",
        help_text="e.g., 'KIVA - 1', 'K2 - Top'",
        null=True,  # Add this temporarily
        default="",  # Add this
        
    )
    
    count = models.PositiveIntegerField(
        default=1, 
        verbose_name="Count",
        help_text="Number of cable runs"
    )
    
    cable = models.CharField(
        max_length=20, 
        choices=CABLE_TYPE_CHOICES,
        verbose_name="Cable",
        default='100_NL4',
    )
    
    
    notes = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        verbose_name="Notes",
        help_text="e.g., 'Clr. 1 Top 2'"
    )
    
    drawing_ref = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name="Drawing Ref",
        help_text="VWX drawing dimension reference"
    )

    length = models.IntegerField(
        default=0,
        verbose_name="Length (ft)",
        help_text="Cable length per run in feet"
    )
    
    # Hidden compatibility fields (can be removed later)
    zone = models.CharField(max_length=20, blank=True, null=True, editable=False)
    cable_type = models.CharField(max_length=20, blank=True, null=True, editable=False)
    quantity = models.PositiveIntegerField(default=1, editable=False)
    length_per_run = models.DecimalField(max_digits=6, decimal_places=1, default=0, editable=False)
    service_loop = models.DecimalField(max_digits=4, decimal_places=1, default=10.0, editable=False)
    from_location = models.CharField(max_length=50, default="AMP RACK", editable=False)
    to_location = models.CharField(max_length=50, blank=True, editable=False)
    amp_location = models.ForeignKey(Location, on_delete=models.SET_NULL, blank=True, null=True, editable=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['label__sort_order', 'label__name', 'cable']
        verbose_name = "PA Cable Entry"
        verbose_name_plural = "PA Cable Entries"
    
    def save(self, *args, **kwargs):
        # Auto-populate hidden fields for compatibility
        if self.label:
            self.zone = self.label.name
        self.cable_type = self.cable
        self.quantity = self.count
        self.to_location = self.destination
        
        # Extract length from cable choice if it's a standard length
        if self.cable:
            if '150_' in self.cable:
                self.length_per_run = 150
            elif '100_' in self.cable:
                self.length_per_run = 100
            elif '75_' in self.cable:
                self.length_per_run = 75
            elif '50_' in self.cable:
                self.length_per_run = 50
            elif '25_' in self.cable:
                self.length_per_run = 25
            elif '15_' in self.cable:
                self.length_per_run = 15
            elif '10_' in self.cable:
                self.length_per_run = 10
            elif '5_' in self.cable:
                self.length_per_run = 5
            elif 'JUMPER' in self.cable:
                self.length_per_run = 3  # Standard jumper length
            else:
                self.length_per_run = 0
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        label_str = self.label.name if self.label else "No Zone"
        return f"{label_str} - {self.destination} - {self.get_cable_display()}"
        
    @property
    def total_length_per_run(self):
        """Length including service loop"""
        return float(self.length_per_run) + float(self.service_loop)
    
    @property
    def total_cable_length(self):
        """Total cable needed for all runs"""
        return self.total_length_per_run * self.quantity
        
    @property
    def total_fan_out_count(self):
        """Total number of fan out items needed"""
        total = 0
        for fan_out in self.fan_outs.all():
            total += fan_out.quantity
        return total
    
    @property
    def fan_out_summary(self):
        """Get a summary of all fan outs for display"""
        fan_outs = self.fan_outs.all()
        if not fan_outs:
            return ""
        return ", ".join([f"{fo.get_fan_out_type_display()} x{fo.quantity}" 
                        for fo in fan_outs])
    
    @property
    def total_cable_length(self):
        """Calculate total cable length needed"""
        return self.count * self.length
    

    @property
    def cable_weight_estimate(self):
        """Rough weight estimate based on cable type (lbs)"""
        weight_per_foot = {
            'NL4_JUMPER': 0.15,
            '150_NL4': 0.22,
            '100_NL4': 0.22,
            '75_NL4': 0.22,
            '50_NL4': 0.22,
            '25_NL4': 0.22,
            '15_NL4': 0.22,
            '10_NL4': 0.22,
            '5_NL4': 0.22,
            '150_NL8': 0.38,
            '100_NL8': 0.38,
            '50_NL8': 0.38,
            '25_NL8': 0.38,
            'CA-COM': 0.45,
            'AES_XLR': 0.05,
            'L14-30': 0.75,
        }
        return self.total_cable_length * weight_per_foot.get(self.cable, 0.2)   


class PAFanOut(models.Model):
            """Individual fan out entry for a cable run"""
            cable_schedule = models.ForeignKey(
                'PACableSchedule',
                on_delete=models.CASCADE,
                related_name='fan_outs'
            )
            fan_out_type = models.CharField(
                max_length=20,
                choices=PACableSchedule.FAN_OUT_CHOICES,  # Reuse existing choices
                blank=True
            )
            quantity = models.IntegerField(
                default=1,
                validators=[MinValueValidator(1)]
            )
            
            class Meta:
                ordering = ['id']
            
            def __str__(self):
                return f"{self.get_fan_out_type_display()} x{self.quantity}"
            


            #--------COMMS Sheet--------

            

class CommChannel(models.Model):
    """Defines available communication channels"""
    CHANNEL_TYPE_CHOICES = [
        ('4W', '4-Wire'),
        ('2W', '2-Wire'),
    ]
    
    input_designation = models.CharField(
        max_length=10,
        help_text="e.g., '1 4W', '2 4W', 'A 2W', 'B 2W'"
    )
    channel_type = models.CharField(max_length=2, choices=CHANNEL_TYPE_CHOICES)
    channel_number = models.CharField(
        max_length=20,
        help_text="e.g., 'FS II - 1'"
    )
    name = models.CharField(
        max_length=50,
        help_text="Full channel name (e.g., 'Production', 'Audio')"
    )
    abbreviation = models.CharField(
        max_length=10,
        help_text="Short name (e.g., 'PROD', 'AUDIO')"
    )
    order = models.IntegerField(default=0, help_text="Display order")
    
    class Meta:
        ordering = ['order', 'channel_number']
        verbose_name = "Comm Channel"
        verbose_name_plural = "Comm Channels"
    
    def __str__(self):
        return f"{self.channel_number} - {self.name} ({self.abbreviation})"
    
    def save(self, *args, **kwargs):
        # Auto-set channel type based on input designation
        if '4W' in self.input_designation:
            self.channel_type = '4W'
        elif '2W' in self.input_designation:
            self.channel_type = '2W'
        super().save(*args, **kwargs)


class CommPosition(models.Model):
    """Predefined positions for crew members"""
    name = models.CharField(max_length=100, unique=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Comm Position"
        verbose_name_plural = "Comm Positions"
    
    def __str__(self):
        return self.name


class CommCrewName(models.Model):
    """Predefined crew names for quick selection"""
    name = models.CharField(max_length=100, unique=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Comm Crew Name"
        verbose_name_plural = "Comm Crew Names"
    
    def __str__(self):
        return self.name


# Update the CommBeltPack model in your planner/models.py file

class CommBeltPack(models.Model):
    """Belt pack assignment and configuration"""
    SYSTEM_TYPE_CHOICES = [
        ('WIRELESS', 'Wireless'),
        ('HARDWIRED', 'Hardwired'),
    ]
    
    HEADSET_CHOICES = [
        ('SM', 'Single Muff'),
        ('DM', 'Double Muff'),
        ('IE', 'In-Ear'),
        ('SS', 'Speaker Station'),
        ('HM', 'Handmic'),
        ('', 'None'),
    ]
    
    GROUP_CHOICES = [
        ('PROD', 'Production'),
        ('AUDIO', 'Audio'),
        ('VIDEO', 'Video'),
        ('LIGHTS', 'Lighting'),
        ('STAGE', 'Stage'),
        ('', 'None'),
    ]
    
    # System type field - NEW
    system_type = models.CharField(
        max_length=10,
        choices=SYSTEM_TYPE_CHOICES,
        default='WIRELESS',
        verbose_name="System Type"
    )
    
    # Unit location for wireless systems - NEW
    unit_location = models.CharField(
        max_length=100,
        blank=True,
        help_text="Location of wireless unit (e.g., 'Unit #1 - FOH Rack')"
    )
    
    bp_number = models.IntegerField(verbose_name="BP #")
    
    # Position and Name can be either selected from dropdown or custom text
    position = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Select from dropdown or enter custom"
    )
    name = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Crew member name"
    )
    
    headset = models.CharField(
        max_length=2, 
        choices=HEADSET_CHOICES, 
        blank=True,
        verbose_name="Headset Type"
    )
    
    # Channel assignments
    channel_a = models.ForeignKey(
        CommChannel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='beltpack_channel_a',
        verbose_name="CH A"
    )
    channel_b = models.ForeignKey(
        CommChannel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='beltpack_channel_b',
        verbose_name="CH B"
    )
    channel_c = models.ForeignKey(
        CommChannel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='beltpack_channel_c',
        verbose_name="CH C"
    )
    channel_d = models.ForeignKey(
        CommChannel, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='beltpack_channel_d',
        verbose_name="CH D"
    )
    
    audio_pgm = models.BooleanField(
        default=False, 
        verbose_name="AUDIO PGM",
        help_text="Receives audio program feed"
    )
    
    group = models.CharField(
        max_length=10, 
        choices=GROUP_CHOICES, 
        blank=True,
        help_text="Department/Group assignment"
    )
    
    checked_out = models.BooleanField(
        default=False,
        verbose_name="Checked Out"
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['system_type', 'bp_number']  # Order by system type first
        verbose_name = "Comm Belt Pack"
        verbose_name_plural = "Comm Belt Packs"
        unique_together = ['system_type', 'bp_number']  # BP numbers can repeat across systems
    
    def __str__(self):
        system_prefix = "W" if self.system_type == "WIRELESS" else "H"
        if self.name:
            return f"{system_prefix}-BP {self.bp_number}: {self.name}"
        return f"{system_prefix}-BP {self.bp_number}"