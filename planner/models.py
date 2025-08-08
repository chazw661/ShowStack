from django.db import models

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
    console_output = models.ForeignKey(
        'ConsoleAuxOutput',  # You might need to create a base ConsoleOutput model
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='device_outputs'
    )

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


class Amp(models.Model):
    """Individual amplifier units"""
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='amps')
    name = models.CharField(max_length=100, help_text="Amp identifier or model name")
    
    # Network configuration
    ip_address = models.GenericIPAddressField(help_text="Network IP address")
    
    # Hardware details
    manufacturer = models.CharField(max_length=50, blank=True, null=True)
    model_number = models.CharField(max_length=50, blank=True, null=True)
    channel_count = models.PositiveIntegerField(default=4, help_text="Number of output channels")
    
    
   # Audio routing
    avb_stream = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="AVB Stream",
        help_text="AVB stream source"
    )
    analogue_input = models.ForeignKey(
        'Device',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Analogue Input",
        related_name='amps_using_as_analogue',
        help_text="Analogue input source device"
    )
    aes_input = models.ForeignKey(
        'Device',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="AES Input",
        related_name='amps_using_as_aes',
        help_text="AES input source device"
    )
    
    # Output configuration
    cacom_output = models.BooleanField(default=False, help_text="Has Cacom output")
    
    # Additional settings
    preset_name = models.CharField(max_length=100, blank=True, null=True, help_text="Active preset")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.ip_address}) - {self.location.name}"
    
    @property
    def ip_last_octet(self):
        """Extract last octet of IP address for sorting"""
        try:
            return int(self.ip_address.split('.')[-1])
        except (ValueError, IndexError):
            return 999
    
    class Meta:
        verbose_name = "Amp"
        verbose_name_plural = "Amps"
        ordering = ['location', 'ip_address']
        unique_together = ['location', 'ip_address']


class AmpChannel(models.Model):
    """Individual channels within an amplifier"""
    amp = models.ForeignKey(Amp, on_delete=models.CASCADE, related_name='channels')
    channel_number = models.PositiveIntegerField()
    
    # Channel configuration
    channel_name = models.CharField(max_length=100, blank=True, null=True, 
                                   help_text="e.g., Left, Right, Center, Sub, Front Fill, Delay, Foldback")
    
    # Signal routing
    avb_stream = models.CharField(max_length=50, blank=True, null=True)
    analogue_input = models.CharField(max_length=50, blank=True, null=True)
    aes_input = models.CharField(max_length=50, blank=True, null=True)
    
    # Output configuration  
    # Output configuration
    nl4_pair_1 = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="1 +/-",
        help_text="NL4 connector pair 1 +/- assignment"
    )
    nl4_pair_2 = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name="2 +/-", 
        help_text="NL4 connector pair 2 +/- assignment"
    )
    
    cacom_pair = models.CharField(
    max_length=50, 
    blank=True, 
    null=True,
    verbose_name="CA-COM Pair",
    help_text="Which CA-COM pair (1-8) this channel routes to"
)
    
    # Settings
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        channel_display = self.channel_name or f"Channel {self.channel_number}"
        return f"{self.amp.name} - {channel_display}"
    
    class Meta:
        verbose_name = "Amp Channel"
        verbose_name_plural = "Amp Channels"
        ordering = ['amp', 'channel_number']
        unique_together = ['amp', 'channel_number']



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

            



           