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
    input_count  = models.PositiveIntegerField(default=0)
    output_count = models.PositiveIntegerField(default=0)
    # …any other fields…
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Custom model save logic
        super().save(*args, **kwargs)
    

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
    avb_stream_input = models.CharField(max_length=50, blank=True, null=True, help_text="AVB stream source")
    xlr_input_count = models.PositiveIntegerField(default=0, help_text="Number of XLR inputs")
    analogue_input_count = models.PositiveIntegerField(default=0, help_text="Number of analogue inputs")
    aes_input_count = models.PositiveIntegerField(default=0, help_text="Number of AES inputs")
    
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
    
    cacom_1 = models.CharField(max_length=50, blank=True, null=True, verbose_name="Cacom 1")
    cacom_2 = models.CharField(max_length=50, blank=True, null=True, verbose_name="Cacom 2")
    cacom_3 = models.CharField(max_length=50, blank=True, null=True, verbose_name="Cacom 3")
    cacom_4 = models.CharField(max_length=50, blank=True, null=True, verbose_name="Cacom 4")
    
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