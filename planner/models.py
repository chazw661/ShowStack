from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from decimal import Decimal
import math
from django import forms
from django.db import models, transaction



from django.contrib.auth.models import User
from django.db import models
import uuid 


# ==================== PROJECT SYSTEM MODELS ====================

class Project(models.Model):
    """Container for all show data - allows multi-tenancy"""
    name = models.CharField(max_length=200, help_text="Show/Event name")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Show details
    show_date = models.DateField(blank=True, null=True)
    venue = models.CharField(max_length=200, blank=True)
    client = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    
    # Status
    is_archived = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-updated_at']
        
    def __str__(self):
        return self.name
    
    def get_member_count(self):
        return self.projectmember_set.count() + 1  # +1 for owner
    
    
    def duplicate(self, new_name=None, duplicate_for_user=None):
        """
        Create a complete copy of this project and all related data.
        """
        
        
        from django.db import transaction
        
        # Set defaults
        if new_name is None:
            new_name = f"Copy of {self.name}"
        if duplicate_for_user is None:
            duplicate_for_user = self.owner
        
        try:
            with transaction.atomic():
               
                # Create new project
                new_project = Project.objects.create(
                    name=new_name,
                    owner=duplicate_for_user,
                    show_date=self.show_date,
                    venue=self.venue,
                    client=self.client,
                    notes=self.notes,
                    is_archived=False
                )
               
                
               
               
                
                return new_project
                
        except Exception as e:
            
            raise  # Re-raise the exception
    
    # ... rest of your duplicate method
        
        with transaction.atomic():
            # Create new project
            new_project = Project.objects.create(
                name=new_name,
                owner=duplicate_for_user,
                show_date=self.show_date,
                venue=self.venue,
                client=self.client,
                notes=self.notes,
                is_archived=False  # Always create as active
            )
            
            # Track old_id -> new_object mappings for relationships
            location_map = {}
            console_map = {}
            amp_map = {}
            
            # 1. Duplicate Locations (needed for other models)
            for location in self.location_set.all():
                new_location = Location.objects.create(
                    project=new_project,
                    name=location.name,
                    description=location.description
                )
                location_map[location.id] = new_location
            
            # 2. Duplicate Consoles and their related objects
            for console in self.console_set.all():
                # Get the location if it exists
                new_location = location_map.get(console.location_id) if console.location_id else None
                
                new_console = Console.objects.create(
                    project=new_project,
                    location=new_location,
                    name=console.name,
                    is_template=console.is_template,
                    primary_ip_address=console.primary_ip_address,
                    secondary_ip_address=console.secondary_ip_address
                )
                console_map[console.id] = new_console
                
                # Duplicate Console Inputs
                for input_obj in console.consoleinput_set.all():
                    ConsoleInput.objects.create(
                        console=new_console,
                        dante_number=input_obj.dante_number,
                        input_ch=input_obj.input_ch,
                        source=input_obj.source,
                        group=input_obj.group,
                        dca=input_obj.dca,
                        mute=input_obj.mute,
                        direct_out=input_obj.direct_out,
                        omni_in=input_obj.omni_in
                    )
                
                # Duplicate Console Aux Outputs
                for aux in console.consoleauxoutput_set.all():
                    ConsoleAuxOutput.objects.create(
                        console=new_console,
                        dante_number=aux.dante_number,
                        aux_number=aux.aux_number,
                        name=aux.name,
                        mono_stereo=aux.mono_stereo,
                        bus_type=aux.bus_type,
                        omni_in=aux.omni_in,
                        omni_out=aux.omni_out
                    )
                
                # Duplicate Console Matrix Outputs
                for matrix in console.consolematrixoutput_set.all():
                    ConsoleMatrixOutput.objects.create(
                        console=new_console,
                        dante_number=matrix.dante_number,
                        matrix_number=matrix.matrix_number,
                        name=matrix.name,
                        mono_stereo=matrix.mono_stereo,
                        destination=matrix.destination,
                        omni_out=matrix.omni_out
                    )
                
                # Duplicate Console Stereo Outputs
                for stereo in console.consolestereooutput_set.all():
                    ConsoleStereoOutput.objects.create(
                        console=new_console,
                        stereo_type=stereo.stereo_type,
                        name=stereo.name,
                        dante_number=stereo.dante_number,
                        omni_out=stereo.omni_out
                    )
            
            # 3. Duplicate Devices (I/O Devices)
            for device in self.device_set.all():
                new_location = location_map.get(device.location_id) if device.location_id else None
                
                new_device = Device.objects.create(
                    project=new_project,
                    location=new_location,
                    name=device.name,
                    input_count=device.input_count,
                    output_count=device.output_count,
                    rio_card_count=device.rio_card_count,
                    notes=device.notes,
                    ip_address=device.ip_address
                )
                
                # Duplicate Device Inputs
                for device_input in device.deviceinput_set.all():
                    DeviceInput.objects.create(
                        device=new_device,
                        input_number=device_input.input_number,
                        source=device_input.source
                    )
                
                # Duplicate Device Outputs
                for device_output in device.deviceoutput_set.all():
                    DeviceOutput.objects.create(
                        device=new_device,
                        output_number=device_output.output_number,
                        destination=device_output.destination
                    )
            
            # 4. Duplicate Amplifiers
            for amp in self.amp_set.all():
                new_location = location_map.get(amp.location_id) if amp.location_id else None
                
                new_amp = Amp.objects.create(
                    project=new_project,
                    location=new_location,
                    amp_model=amp.amp_model,
                    name=amp.name,
                    notes=amp.notes,
                    ip_address=amp.ip_address
                )
                amp_map[amp.id] = new_amp
                
                # Duplicate Amp Channels
                for channel in amp.ampchannel_set.all():
                    AmpChannel.objects.create(
                        amp=new_amp,
                        channel_number=channel.channel_number,
                        speaker_load=channel.speaker_load,
                        notes=channel.notes
                    )
                
                # Duplicate NL4 Connectors
                for nl4 in amp.nl4connector_set.all():
                    NL4Connector.objects.create(
                        amp=new_amp,
                        connector_number=nl4.connector_number,
                        ch1_plus=nl4.ch1_plus,
                        ch1_minus=nl4.ch1_minus,
                        ch2_plus=nl4.ch2_plus,
                        ch2_minus=nl4.ch2_minus
                    )
                
                # Duplicate NL8 Connectors
                for nl8 in amp.nl8connector_set.all():
                    NL8Connector.objects.create(
                        amp=new_amp,
                        connector_number=nl8.connector_number,
                        ch1_plus=nl8.ch1_plus,
                        ch1_minus=nl8.ch1_minus,
                        ch2_plus=nl8.ch2_plus,
                        ch2_minus=nl8.ch2_minus,
                        ch3_plus=nl8.ch3_plus,
                        ch3_minus=nl8.ch3_minus,
                        ch4_plus=nl8.ch4_plus,
                        ch4_minus=nl8.ch4_minus
                    )
                
                # Duplicate CaCom Outputs
                for cacom in amp.cacomoutput_set.all():
                    CacomOutput.objects.create(
                        amp=new_amp,
                        output_number=cacom.output_number,
                        ch1=cacom.ch1,
                        ch2=cacom.ch2,
                        ch3=cacom.ch3,
                        ch4=cacom.ch4,
                        ch5=cacom.ch5,
                        ch6=cacom.ch6,
                        ch7=cacom.ch7,
                        ch8=cacom.ch8,
                        ch9=cacom.ch9,
                        ch10=cacom.ch10,
                        ch11=cacom.ch11,
                        ch12=cacom.ch12,
                        ch13=cacom.ch13,
                        ch14=cacom.ch14,
                        ch15=cacom.ch15,
                        ch16=cacom.ch16
                    )
            
            # 5. Duplicate COMM System
            # Duplicate CommChannels
            for channel in self.commchannel_set.all():
                CommChannel.objects.create(
                    project=new_project,
                    channel_number=channel.channel_number,
                    name=channel.name
                )
            
            # Duplicate CommPositions
            for position in self.commposition_set.all():
                CommPosition.objects.create(
                    project=new_project,
                    position_number=position.position_number,
                    name=position.name
                )
            
            # Duplicate CommCrewNames
            for crew in self.commcrewname_set.all():
                CommCrewName.objects.create(
                    project=new_project,
                    name=crew.name,
                    position_number=crew.position_number
                )
            
            # Duplicate CommBeltPacks
            for beltpack in self.commbeltpack_set.all():
                CommBeltPack.objects.create(
                    project=new_project,
                    beltpack_number=beltpack.beltpack_number,
                    assigned_to=beltpack.assigned_to,
                    position=beltpack.position,
                    channel_assignments=beltpack.channel_assignments
                )
            
            # 6. Duplicate Mic Tracker System
            # Duplicate Presenters first (needed for sessions)
            presenter_map = {}
            for presenter in self.presenter_set.all():
                new_presenter = Presenter.objects.create(
                    project=new_project,
                    name=presenter.name,
                    title=presenter.title,
                    organization=presenter.organization
                )
                presenter_map[presenter.id] = new_presenter
            
            # Duplicate ShowDays
            showday_map = {}
            for showday in self.showday_set.all():
                new_showday = ShowDay.objects.create(
                    project=new_project,
                    day_number=showday.day_number,
                    date=showday.date,
                    name=showday.name
                )
                showday_map[showday.id] = new_showday
            
            # Duplicate MicSessions
            for session in self.micsession_set.all():
                new_showday = showday_map.get(session.show_day_id) if session.show_day_id else None
                
                new_session = MicSession.objects.create(
                    project=new_project,
                    show_day=new_showday,
                    session_number=session.session_number,
                    session_name=session.session_name,
                    start_time=session.start_time,
                    end_time=session.end_time
                )
                
                # Duplicate the many-to-many presenters relationship
                for presenter in session.presenters.all():
                    new_presenter = presenter_map.get(presenter.id)
                    if new_presenter:
                        new_session.presenters.add(new_presenter)
                
                # Duplicate MicAssignments
                for assignment in session.micassignment_set.all():
                    MicAssignment.objects.create(
                        session=new_session,
                        mic_number=assignment.mic_number,
                        mic_type=assignment.mic_type,
                        assigned_to=assignment.assigned_to,
                        notes=assignment.notes
                    )
            
            # Duplicate MicShowInformation
            for mic_info in self.micshowinformation_set.all():
                MicShowInformation.objects.create(
                    project=new_project,
                    show_name=mic_info.show_name,
                    venue=mic_info.venue,
                    dates=mic_info.dates,
                    production_company=mic_info.production_company,
                    audio_company=mic_info.audio_company
                )
            
            # 7. Duplicate Soundvision/PA System
            # Duplicate Speaker Arrays
            array_map = {}
            for array in self.speakerarray_set.all():
                new_location = location_map.get(array.location_id) if array.location_id else None
                
                new_array = SpeakerArray.objects.create(
                    project=new_project,
                    location=new_location,
                    name=array.name,
                    array_type=array.array_type,
                    notes=array.notes
                )
                array_map[array.id] = new_array
                
                # Duplicate Speaker Cabinets
                for cabinet in array.speakercabinet_set.all():
                    SpeakerCabinet.objects.create(
                        array=new_array,
                        model=cabinet.model,
                        quantity=cabinet.quantity,
                        position=cabinet.position,
                        angle=cabinet.angle
                    )
            
            # Duplicate Soundvision Predictions
            for prediction in self.soundvisionprediction_set.all():
                SoundvisionPrediction.objects.create(
                    project=new_project,
                    name=prediction.name,
                    file=prediction.file,
                    notes=prediction.notes,
                    created_at=prediction.created_at
                )
            
            # 8. Duplicate Power Distribution Plans
            for power_plan in self.powerdistributionplan_set.all():
                new_location = location_map.get(power_plan.location_id) if power_plan.location_id else None
                
                PowerDistributionPlan.objects.create(
                    project=new_project,
                    location=new_location,
                    name=power_plan.name,
                    total_amps_available=power_plan.total_amps_available,
                    voltage=power_plan.voltage,
                    notes=power_plan.notes
                )
            
            # NOTE: We intentionally do NOT duplicate:
            # - ProjectMember (team members)
            # - Invitations
            # - created_at/updated_at timestamps (automatically set to now)
            
            return new_project



class UserProfile(models.Model):
    """Extended user profile for subscription management"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    ACCOUNT_TYPES = [
        ('super_user', 'Super User'),
        ('beta', 'Beta Tester'),
        ('paid', 'Paid Subscriber'),
        ('free', 'Free Account'),
    ]
    
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='free')
    can_create_projects = models.BooleanField(default=False)
    
    # Subscription details
    lifetime_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, 
                                                     help_text="Discount % for lifetime (e.g., 50.00 for 50%)")
    subscription_start = models.DateField(blank=True, null=True)
    subscription_end = models.DateField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
    
    def __str__(self):
        return f"{self.user.username} ({self.get_account_type_display()})"


class ProjectMember(models.Model):
    """Users who have been invited to collaborate on a project"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    ROLES = [
        ('editor', 'Editor - Can view and edit'),
        ('viewer', 'Viewer - Can only view'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLES, default='editor')
    invited_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
    User,
    on_delete=models.CASCADE,
    related_name='invitations_sent'  # ← CHANGED TO UNIQUE NAME
)
    
    class Meta:
        unique_together = ['project', 'user']
        verbose_name = "Project Member"
        verbose_name_plural = "Project Members"
    
    def __str__(self):
        return f"{self.user.username} → {self.project.name} ({self.role})"

#-----Console Model----

class Console(models.Model):
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True, related_name='consoles') 
    name = models.CharField(max_length=100)
    is_template = models.BooleanField(
        default=False, 
        help_text="Mark this console as a template for creating new consoles"
    )
    
    primary_ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="Primary IP Address", help_text="Primary console IP address (optional)")
    secondary_ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="Secondary IP Address", help_text="Secondary console IP address (optional)")

    def __str__(self):
        template_prefix = "[TEMPLATE] " if self.is_template else ""
        return f"{template_prefix}{self.name}"
    
    class Meta:
        verbose_name = "Console"
        verbose_name_plural = "Consoles"
        ordering = ['-is_template', 'name']  # Templates first, then alphabetical


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
    

    def __str__(self):
        if self.dante_number:
            return f"Input {self.dante_number}"
        elif self.input_ch:
            return f"Input {self.input_ch}"
        else:
            return f"Input {self.pk or 'New'}"
        


class ConsoleAuxOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    dante_number = models.IntegerField(null=True, blank=True) 
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
    dante_number = models.IntegerField(null=True, blank=True) 
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
    
class ConsoleStereoOutput(models.Model):
    STEREO_CHOICES = [
        ('L', 'Stereo Left'),
        ('R', 'Stereo Right'),
        ('M', 'Mono'),
    ]
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    stereo_type = models.CharField(max_length=2, choices=STEREO_CHOICES, verbose_name="Buss")
    name = models.CharField(max_length=100, blank=True, null=True)
    dante_number = models.IntegerField(null=True, blank=True)
    omni_out = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.get_stereo_type_display()} - {self.name}"
    
    class Meta:
        ordering = ['stereo_type']   
   
    


    # planner/models.py

from django.db import models

class Device(models.Model):
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')
    name = models.CharField(max_length=200)
    input_count = models.PositiveIntegerField(default=0)
    output_count = models.PositiveIntegerField(default=0)
    primary_ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="Primary IP Address", help_text="Primary device IP address (optional)")
    secondary_ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="Secondary IP Address", help_text="Secondary device IP address (optional)")

    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "I/O Device"
        verbose_name_plural = "I/O Devices"
        ordering = ['name']  # or ['id']

    

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

    def save(self, *args, **kwargs):
        # Auto-populate input_number if not set
        if self.input_number is None:
            # Find the highest existing input_number for this device
            existing_inputs = DeviceInput.objects.filter(device=self.device)
            if existing_inputs.exists():
                max_number = existing_inputs.aggregate(models.Max('input_number'))['input_number__max']
                self.input_number = (max_number or 0) + 1
            else:
                self.input_number = 1
        
        super().save(*args, **kwargs)


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




    def save(self, *args, **kwargs):
        # Auto-populate output_number if not set
        if self.output_number is None:
            # Find the highest existing output_number for this device
            existing_outputs = DeviceOutput.objects.filter(device=self.device)
            if existing_outputs.exists():
                max_number = existing_outputs.aggregate(models.Max('output_number'))['output_number__max']
                self.output_number = (max_number or 0) + 1
            else:
                self.output_number = 1
        
        super().save(*args, **kwargs)




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
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, help_text="e.g., HL LA Racks, HR LA Racks, Monitor World")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Equip Location"
        verbose_name_plural = "Equip Locations"  # Child
        ordering = ['name']  # or ['id']



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
    

    nl8_connector_count = models.IntegerField(
    default=0,
    choices=[(0, 'None'), (1, '1 NL8'), (2, '2 NL8')]
    )
    
    # Cacom configuration  
    cacom_output_count = models.IntegerField(default=0)
    
    class Meta:
        verbose_name = "Amp Model Template"
        verbose_name_plural = "    └─ Amp Model Templates"  # Child - End of tree
        ordering = ['id']
    
    def __str__(self):
        return f"{self.manufacturer} {self.model_name}"


class Amp(models.Model):
    """Individual amplifier instance"""
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='amps')
    amp_model = models.ForeignKey(AmpModel, on_delete=models.PROTECT, 
        null=True,  
        blank=True )
       
    name = models.CharField(
        max_length=100, 
        help_text="Unique identifier (e.g., 'LA12X-1', 'Stage Left 1')"
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    color = models.CharField(
        max_length=7,
        blank=True,
        null=True,
        default='#FFFFFF',
        help_text="Background color for this amp in lists (hex code, e.g., #FF5733)"
    )
    
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

    # NL8 Connector A (if present)
    nl8_a_pair_1 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-A Pair 1 +/-",
        help_text="e.g., 'Ch1/Ch2'"
    )
    nl8_a_pair_2 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-A Pair 2 +/-",
        help_text="e.g., 'Ch3/Ch4'"
    )
    nl8_a_pair_3 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-A Pair 3 +/-",
        help_text="e.g., 'Ch5/Ch6'"
    )
    nl8_a_pair_4 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-A Pair 4 +/-",
        help_text="e.g., 'Ch7/Ch8'"
    )
    
    # NL8 Connector B (if present)
    nl8_b_pair_1 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-B Pair 1 +/-",
        help_text="e.g., 'Ch1/Ch2'"
    )
    nl8_b_pair_2 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-B Pair 2 +/-",
        help_text="e.g., 'Ch3/Ch4'"
    )
    nl8_b_pair_3 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-B Pair 3 +/-",
        help_text="e.g., 'Ch5/Ch6'"
    )
    nl8_b_pair_4 = models.CharField(
        max_length=50, blank=True,
        verbose_name="NL8-B Pair 4 +/-",
        help_text="e.g., 'Ch7/Ch8'"
    )
    
    # Cacom outputs (if present)
  # CaCom outputs - 4 channels per connector
    # CaCom 1 (Channels 1-4)
    cacom_1_ch1 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 1 - Ch1")
    cacom_1_ch2 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 1 - Ch2")
    cacom_1_ch3 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 1 - Ch3")
    cacom_1_ch4 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 1 - Ch4")

    # CaCom 2 (Channels 5-8)
    cacom_2_ch1 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 2 - Ch5")
    cacom_2_ch2 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 2 - Ch6")
    cacom_2_ch3 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 2 - Ch7")
    cacom_2_ch4 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 2 - Ch8")

    # CaCom 3 (Channels 9-12)
    cacom_3_ch1 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 3 - Ch9")
    cacom_3_ch2 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 3 - Ch10")
    cacom_3_ch3 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 3 - Ch11")
    cacom_3_ch4 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 3 - Ch12")

    # CaCom 4 (Channels 13-16)
    cacom_4_ch1 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 4 - Ch13")
    cacom_4_ch2 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 4 - Ch14")
    cacom_4_ch3 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 4 - Ch15")
    cacom_4_ch4 = models.CharField(max_length=100, blank=True, verbose_name="CaCom 4 - Ch16")
    
    class Meta:
        verbose_name = "Amplifier Assignment"
        verbose_name_plural = "Amplifier Assignments"  # PARENT - Standalone
        ordering = ['ip_address']

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
    AVB_CHOICES = [(f'AVB {i}', f'AVB {i}') for i in range(1, 17)]
    AVB_CHOICES.insert(0, ('', '---------'))
    
    # Input source (only show relevant options based on amp model)
    avb_stream = models.CharField(
        max_length=10,
        choices=AVB_CHOICES,
        blank=True,
        null=True,
        verbose_name="AVB Stream",
        help_text="AVB stream assignment"
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
        verbose_name = "Amp Channel"
        verbose_name_plural = "    ├─ Amp Channels"
        # UPDATE THIS: Likely fields are 'amp', 'channel_number'
        ordering = ['id']
    
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

    project = models.ForeignKey('Project', on_delete=models.CASCADE)
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
        ordering = ['name']  # or ['id']



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

    @property
    def project(self):
        """Access project through SystemProcessor"""
        return self.system_processor.project    


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

    @property
    def project(self):
        """Access project through SystemProcessor"""
        return self.system_processor.project


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
        verbose_name = "PA Zone"
        verbose_name_plural = "PA Zones"  # Child
        ordering = ['id']  # or ['id']
    
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
    
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
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
        verbose_name = "PA Cable Entry"
        verbose_name_plural = "PA Cable Entries"  # PARENT
        ordering = ['id']
    
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
                verbose_name = "PA Fan Out"
                verbose_name_plural = "    └─ PA Fan Outs"
                ordering = ['id']  # SAFE DEFAULT
                     
            
            def __str__(self):
                return f"{self.get_fan_out_type_display()} x{self.quantity}"
            


            #--------COMMS Sheet--------

            

class CommChannel(models.Model):


    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='comm_channels',
        help_text="Project this channel belongs to"
    )
    
    CHANNEL_TYPE_CHOICES = [
        ('4W', '4-Wire'),
        ('2W', '2-Wire'),
    ]
    
    input_designation = models.CharField(
        max_length=10,
        help_text="e.g., '1 4W', '2 4W', 'A 2W', 'B 2W'"
    )



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
        verbose_name = "Comm Channel"
        verbose_name_plural = "    └─ Comm Channels"  # Child
        ordering = ['id']  # or ['id']

    
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
    name = models.CharField(max_length=100)
    order = models.IntegerField(default=0)
    project = models.ForeignKey('Project', on_delete=models.CASCADE) 
    
    class Meta:
        verbose_name = "Comm Position"
        verbose_name_plural = "    ├─ Comm Positions"  # Child
        ordering = ['name']  # or ['id']
        unique_together = [['name', 'project']]
    
    def __str__(self):
        return self.name


class CommCrewName(models.Model):
    """Predefined crew names for quick selection"""
    name = models.CharField(max_length=100, unique=True)
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Comm Crew Name"
        verbose_name_plural = "    ├─ Comm Crew Names"
        # UPDATE THIS: Likely field is 'name'
        ordering = ['id'] 
    
    def __str__(self):
        return self.name



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
    

    project = models.ForeignKey('Project', on_delete=models.CASCADE)
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

    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name="IP Address",
        help_text="IP address for hardwired belt packs (optional)"
    )
    
    bp_number = models.IntegerField(verbose_name="BP #")
    updated_at = models.DateTimeField(auto_now=True)
    

    # Position and Name can be either selected from dropdown or custom text
   # Position and Name - ForeignKey to dedicated models
    position = models.ForeignKey(
        'CommPosition',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='beltpacks',
        help_text="Position assignment"
    )
    name = models.ForeignKey(
        'CommCrewName',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='beltpacks',
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


    channel_e = models.ForeignKey(
        'CommChannel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='beltpack_channel_e',
        verbose_name="CH E"
    )
    
    channel_f = models.ForeignKey(
        'CommChannel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='beltpack_channel_f',
        verbose_name="CH F"
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
    help_text="Whether this belt pack has been checked out (Wireless only)"

    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Comm Belt Pack"
        verbose_name_plural = "Comm Belt Packs"  # PARENT
        # UPDATE THIS: Likely field is 'bp_number'
        ordering = ['bp_number'] 
    
    def __str__(self):
        system_prefix = "W" if self.system_type == "WIRELESS" else "H"
        if self.name:
            return f"{system_prefix}-BP {self.bp_number}: {self.name}"
        return f"{system_prefix}-BP {self.bp_number}"
    
    def save(self, *args, **kwargs):
    # Force checked_out to False for Hardwired beltpacks
        if self.system_type == 'HARDWIRED':
            self.checked_out = False
        super().save(*args, **kwargs)

    def clean(self):
        # Add validation to prevent checked_out for Hardwired
        if self.system_type == 'HARDWIRED' and self.checked_out:
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'checked_out': 'Hardwired belt packs cannot be checked out.'
            })
        super().clean()


#-------Mics Tracker-----



from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import json

class ShowDay(models.Model):
    """Represents a day in the show schedule"""
    project = models.ForeignKey('Project', on_delete=models.CASCADE) 
    date = models.DateField(unique=True)
    name = models.CharField(max_length=100, blank=True, help_text="Optional name for the day (e.g., 'Day 1 - Setup')")
    is_collapsed = models.BooleanField(default=False, help_text="UI state: whether this day is collapsed in the view")
    order = models.IntegerField(default=0, help_text="Display order for days")
    
    class Meta:
        verbose_name = "Show Mic Tracker"
        verbose_name_plural = "Show Mic Tracker"  # PARENT
        ordering = ['date'] 

    
    def __str__(self):
        if self.name:
            return f"{self.date.strftime('%Y-%m-%d')} - {self.name}"
        return self.date.strftime('%Y-%m-%d')
    
    def get_all_mics_status(self):
        """Get a summary of all mics across all sessions for this day"""
        sessions = self.sessions.all()
        total_mics = 0
        used_mics = 0
        
        for session in sessions:
            assignments = session.mic_assignments.all()
            total_mics += assignments.count()
            used_mics += assignments.filter(is_micd=True).count()
        
        return {
            'total': total_mics,
            'used': used_mics,
            'available': total_mics - used_mics
        }
    


# ========Presenters========

class Presenter(models.Model):
    name = models.CharField(max_length=200, unique=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='presenters',
        help_text="Project this presenter belongs to"
    )
    name = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Presenter"
        verbose_name_plural = "  ├─ Presenters"  # Child of Show Mic Tracker
        ordering = ['name']
    
    def __str__(self):
        return self.name    

class MicSession(models.Model):
    """Represents a session within a show day"""
    SESSION_TYPES = [
        ('REHEARSAL', 'Rehearsal'),
        ('KEYNOTE', 'Keynote'),
        ('PANEL', 'Panel Discussion'),
        ('BREAKOUT', 'Breakout Session'),
        ('GENERAL', 'General Session'),
        ('TECH_CHECK', 'Tech Check'),
        ('OTHER', 'Other'),
    ]
    
    day = models.ForeignKey(ShowDay, on_delete=models.CASCADE, related_name='sessions')
    name = models.CharField(max_length=200)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPES, default='GENERAL')
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    
    # Configuration
    num_mics = models.IntegerField(
        default=16,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Number of mics available for this session"
    )
    
    # Display settings
    column_position = models.IntegerField(
        default=0,
        help_text="Position in the display grid (0-2 for 3-column layout)"
    )
    order = models.IntegerField(default=0, help_text="Display order within the day")
    
    class Meta:
        verbose_name = "Mic Session"
        verbose_name_plural = "    ├─ Mic Sessions"  # Child
        ordering = ['day', 'order']  # or ['id']
    
    def __str__(self):
        return f"{self.day.date.strftime('%m/%d')} - {self.name}"
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Auto-create mic assignments if this is a new session
        if is_new:
            self.create_mic_assignments()
    
    def create_mic_assignments(self):
        """Create the specified number of mic assignments for this session"""
        existing_count = self.mic_assignments.count()
        
        if existing_count < self.num_mics:
            # Add more assignments
            for i in range(existing_count + 1, self.num_mics + 1):
                MicAssignment.objects.create(
                    session=self,
                    rf_number=i
                )
        elif existing_count > self.num_mics:
            # Remove excess assignments (from the end)
            excess = self.mic_assignments.filter(rf_number__gt=self.num_mics)
            excess.delete()
    
    def get_mic_usage_stats(self):
        """Get statistics about mic usage in this session"""
        assignments = self.mic_assignments.all()
        return {
            'total': assignments.count(),
            'micd': assignments.filter(is_micd=True).count(),
            'd_mic': assignments.filter(is_d_mic=True).count(),
            'available': assignments.filter(is_micd=False).count(),
            'shared': assignments.filter(shared_presenters__isnull=False).count()
        }
    
    def duplicate_to_session(self, target_session):
        """Duplicate all mic assignments to another session"""
        for assignment in self.mic_assignments.all():
            new_assignment = MicAssignment.objects.create(
                session=target_session,
                rf_number=assignment.rf_number,
                mic_type=assignment.mic_type,
                presenter_name=assignment.presenter_name,
                is_micd=assignment.is_micd,
                is_d_mic=assignment.is_d_mic,
                notes=assignment.notes
            )
            # Copy shared presenters
            if assignment.shared_presenters:
                new_assignment.shared_presenters = assignment.shared_presenters
                new_assignment.save()

class MicAssignment(models.Model):
    """Represents a single mic assignment within a session"""
    MIC_TYPES = [
        ('', '---'),
        ('HH', 'Handheld'),
        ('LAV', 'Lavalier'),
        ('HEADSET', 'Headset'),
        ('PODIUM', 'Podium'),
        ('BOOM', 'Boom'),
        ('BOUNDARY', 'Boundary'),
        ('GOOSENECK', 'Gooseneck'),
        ('COMBO', 'Combo Pack'),
    ]
    
    session = models.ForeignKey(MicSession, on_delete=models.CASCADE, related_name='mic_assignments')
    rf_number = models.IntegerField(validators=[MinValueValidator(1)])
    
    # Mic details
    mic_type = models.CharField(max_length=20, choices=MIC_TYPES, blank=True)
    presenter = models.ForeignKey(
    Presenter,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='mic_assignments',
    help_text="Primary presenter for this mic"
)
    
    shared_presenters = models.ManyToManyField(
        Presenter,
        blank=True,
        related_name='shared_mic_assignments',
        help_text="Additional presenters sharing this mic"
)
    
    # Status checkboxes
    is_micd = models.BooleanField(default=False, verbose_name="MIC'D")
    is_d_mic = models.BooleanField(default=False, verbose_name="D-MIC")
    active_presenter_index = models.IntegerField(default=0)
    
   
    
    
    
    # Additional fields
    notes = models.TextField(blank=True)
    last_modified = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        'auth.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='mic_modifications'
    )
    
    class Meta:
        verbose_name = "Mic Assignment"
        verbose_name_plural = "    ├─ Mic Assignments"  # Child
        ordering = ['rf_number']  
    
    # Replace the methods section in MicAssignment class (lines 1407-1440+)

    def __str__(self):
        if self.presenter:
            return f"RF{self.rf_number:02d} - {self.presenter.name}"
        return f"RF{self.rf_number:02d}"
    
    def get_all_presenters(self):
        """Return list of all presenters including shared ones"""
        presenters = []
        if self.presenter:
            presenters.append(self.presenter.name)
        if self.shared_presenters.exists():
            presenters.extend([p.name for p in self.shared_presenters.all()])
        return presenters
    
    @property
    def presenter_count(self):
        """Return the total number of presenters for this mic"""
        count = 1 if self.presenter else 0
        if self.shared_presenters.exists():
            count += self.shared_presenters.count()
        return count
    
    @property
    def current_presenter(self):
        """Get the name of the currently active presenter"""
        if self.active_presenter_index == 0:
            return self.presenter.name if self.presenter else ''
        elif self.active_presenter_index <= self.shared_presenters.count():
            shared_list = list(self.shared_presenters.all())
            return shared_list[self.active_presenter_index - 1].name
        return ''
    
    @property
    def all_presenters(self):
        """Get list of all presenters (primary + shared)"""
        presenters = []
        if self.presenter:
            presenters.append({
                'name': self.presenter.name,
                'index': 0,
                'is_active': self.active_presenter_index == 0
            })
        
        for idx, presenter in enumerate(self.shared_presenters.all(), start=1):
            presenters.append({
                'name': presenter.name,
                'index': idx,
                'is_active': self.active_presenter_index == idx
            })
        
        return presenters
    
    @property
    def has_shared_presenters(self):
        """Check if this assignment has shared presenters"""
        return self.shared_presenters.exists()
    
    @property
    def shared_count(self):
        """Count of shared presenters"""
        return self.shared_presenters.count()
    
    def get_current_presenter_name(self):
        """Get the name of the currently active presenter"""
        if self.active_presenter_index == 0:
            return self.presenter.name if self.presenter else ''

    # Get shared presenters list
        shared_list = list(self.shared_presenters.all())
    
    # active_presenter_index starts at 0 for primary, 1+ for shared
        if 0 < self.active_presenter_index <= len(shared_list):
            return shared_list[self.active_presenter_index - 1].name
        
        # Fallback to primary if index is out of range
        return self.presenter.name if self.presenter else ''
    
    def rotate_to_next_presenter(self):
        """
        Move to the next presenter in the list
        Returns True if rotation successful, False if at end
        """
        total_presenters = 1 + self.shared_presenters.count()
        
        if self.active_presenter_index < total_presenters - 1:
            self.active_presenter_index += 1
            self.is_micd = False
            self.save()
            return True
        
        return False
    
    def reset_presenter_rotation(self):
        """Reset back to primary presenter"""
        self.active_presenter_index = 0
        self.is_micd = False
        self.is_d_mic = False
        self.save()
    
    @property
    def display_presenters(self):
        """Return a formatted string of all presenters"""
        presenters = []
        if self.presenter:
            presenters.append(self.presenter.name)
        if self.shared_presenters.exists():
            presenters.extend([p.name for p in self.shared_presenters.all()])
        
        if len(presenters) == 0:
            return ""
        elif len(presenters) == 1:
            return presenters[0]
        elif len(presenters) == 2:
            return f"{presenters[0]} / {presenters[1]}"
        else:
            return f"{presenters[0]} / +{len(presenters)-1} more"
    
   

class MicShowInfo(models.Model):
    """Project-specific mic show configuration"""
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='mic_show_info',
        help_text="Project this configuration belongs to"
    )
    show_name = models.CharField(max_length=200, blank=True)
    venue_name = models.CharField(max_length=200, blank=True)
    ballroom_name = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    # Default configurations
    default_mics_per_session = models.IntegerField(default=16)
    default_session_duration = models.IntegerField(default=60, help_text="Default session duration in minutes")
    
    class Meta:
        verbose_name = "Mic Show Information"
        verbose_name_plural = "    └─ Mic Show Information"
    
    def __str__(self):
        if self.show_name:
            return f"{self.show_name} - Mic Configuration"
        return f"{self.project.name} - Mic Configuration"
    
    @property
    def duration_display(self):
        if self.start_date and self.end_date:
            return f"{self.start_date.strftime('%m/%d')}-{self.end_date.strftime('%m/%d')}"
        return ""




#-------Power Esimator--------



# Add these models to your existing planner/models.py file

class AmplifierProfile(models.Model):
    """Stores amplifier specifications for power calculations""" 
    manufacturer = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    
    # Power specifications (in watts)
    idle_power_watts = models.IntegerField(
        help_text="Idle/quiescent power draw in watts"
    )
    rated_power_watts = models.IntegerField(
        help_text="1/8 power (pink noise) in watts - typical operating power"
    )
    peak_power_watts = models.IntegerField(
        help_text="1/3 power (heavy program) in watts"
    )
    max_power_watts = models.IntegerField(
        help_text="Maximum rated power in watts"
    )
    
    # Electrical specifications
    nominal_voltage = models.IntegerField(
        choices=[(120, '120V'), (208, '208V'), (240, '240V')],
        default=208
    )
    power_factor = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.95,
        help_text="Power factor (typically 0.95 for modern amps)"
    )
    efficiency = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.90,
        help_text="Amplifier efficiency (typically 0.85-0.95)"
    )
    
    # Physical specifications
    channels = models.IntegerField(default=4)
    rack_units = models.IntegerField(default=2)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Additional info
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Amplifier Profile"
        verbose_name_plural = "    └─ Amplifier Profiles"  # Child
        ordering = ['manufacturer', 'model']  # or ['i fields are 'manufacturer', 'model'
       
        
    def __str__(self):
        return f"{self.manufacturer} {self.model}"
    
    def calculate_current(self, duty_cycle='heavy_music', transient_factor=1.5):
        """Calculate current draw based on duty cycle and transient requirements"""
        duty_multipliers = {
            'speech': 0.20,
            'light_music': 0.35,
            'heavy_music': 0.50,
            'edm_concert': 0.70,
            'test_tone': 1.00
        }
        
        # Base calculation on 1/8 power (pink noise standard)
        base_draw = self.rated_power_watts
        
        # Apply duty cycle
        operational_draw = base_draw * duty_multipliers.get(duty_cycle, 0.50)
        
        # Add idle power (always present)
        total_draw = self.idle_power_watts + operational_draw
        
        # Apply transient headroom
        peak_capable_draw = total_draw * transient_factor
        
        # Convert to current (amps)
        current = peak_capable_draw / (self.nominal_voltage * float(self.power_factor))
        
        return {
            'continuous_watts': total_draw,
            'peak_watts': peak_capable_draw,
            'current_amps': round(current, 1),
            'breaker_size': math.ceil(current * 1.25 / 10) * 10  # Next standard breaker size
        }


class PowerDistributionPlan(models.Model):
    """Main power distribution planning for a show"""
    project = models.ForeignKey('Project', on_delete=models.CASCADE) 
    show_day = models.ForeignKey(ShowDay, on_delete=models.CASCADE, related_name='power_plans')
    venue_name = models.CharField(max_length=200)
    
    SERVICE_TYPES = [
        ('3phase_4wire_208', '3-Phase 4-Wire 208V'),
        ('3phase_5wire_208', '3-Phase 5-Wire 208V'),
        ('3phase_4wire_240', '3-Phase 4-Wire 240V'),
        ('single_phase_120', 'Single Phase 120V'),
        ('single_phase_240', 'Single Phase 240V'),
    ]
    service_type = models.CharField(max_length=50, choices=SERVICE_TYPES, default='3phase_4wire_208')
    
    available_amperage_per_leg = models.IntegerField(
        default=400,
        help_text="Total available amps per leg"
    )
    
    # Safety factors
    transient_headroom = models.DecimalField(
        max_digits=3, decimal_places=2, default=1.50,
        help_text="Multiplier for transient peaks (1.5 = 50% headroom)"
    )
    safety_margin = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.80,
        help_text="Derating factor (0.8 = use only 80% of available)"
    )
    
    # Additional info
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('auth.User',  # Direct string reference to User model
    on_delete=models.SET_NULL, 
    null=True, 
    blank=True,
    related_name='power_plans_created'
    )
    
    class Meta:
        verbose_name = "Power Distribution Plan"
        verbose_name_plural = "Power Distribution Plans"  # PARENT
        ordering = ['-created_at']  # or ['id']
        
    def __str__(self):
        return f"{self.show_day} - {self.venue_name} Power Plan"
    
    def get_usable_amperage(self):
        """Calculate usable amperage after applying safety margin"""
        return int(self.available_amperage_per_leg * float(self.safety_margin))
    
    def get_voltage(self):
        """Extract voltage from service type"""
        if '208' in self.service_type:
            return 208
        elif '240' in self.service_type:
            return 240
        elif '120' in self.service_type:
            return 120
        return 208  # default


class AmplifierAssignment(models.Model):
    """Assignment of amplifiers to a power distribution plan"""
    distribution_plan = models.ForeignKey(
        PowerDistributionPlan, 
        on_delete=models.CASCADE, 
        related_name='amplifier_assignments'
    )
    amplifier = models.ForeignKey(AmplifierProfile, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    
    # Zone/location tracking
    zone = models.CharField(
        max_length=100,
        help_text="Location (e.g., FOH, Delays, Fills)"
    )
    position = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Specific position within zone"
    )
    
    # Power routing
    PHASE_CHOICES = [
        ('L1', 'Phase L1/A'),
        ('L2', 'Phase L2/B'),
        ('L3', 'Phase L3/C'),
        ('AUTO', 'Auto-Balance'),
    ]
    phase_assignment = models.CharField(
        max_length=10, 
        choices=PHASE_CHOICES,
        default='AUTO'
    )
    
    # Operating mode
    DUTY_CYCLES = [
        ('speech', 'Speech/Vocal (20% duty)'),
        ('light_music', 'Light Music (35% duty)'),
        ('heavy_music', 'Heavy Music (50% duty)'),
        ('edm_concert', 'EDM/Concert (70% duty)'),
        ('test_tone', 'Test/Alignment (100% duty)'),
    ]
    duty_cycle = models.CharField(
        max_length=50, 
        choices=DUTY_CYCLES,
        default='heavy_music'
    )
    
    # Calculated values (cached for performance)
    calculated_current_per_unit = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Calculated current draw per amplifier"
    )
    calculated_total_current = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Total current draw for all units"
    )
    
    # Additional info
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Amplifiers in Power Plan"
        verbose_name_plural = "    ├─ Amplifiers in Power Plan"  # PARENT
        ordering = ['id']  # SAFE DEFAULT - replace with your fields like 'zone', 'position', etc.

        
    def __str__(self):
        return f"{self.zone} - {self.amplifier} x{self.quantity}"
    
    def save(self, *args, **kwargs):
        """Recalculate current draw on save"""
        calc = self.amplifier.calculate_current(
            duty_cycle=self.duty_cycle,
            transient_factor=float(self.distribution_plan.transient_headroom)
        )
        self.calculated_current_per_unit = calc['current_amps']
        self.calculated_total_current = calc['current_amps'] * self.quantity
        super().save(*args, **kwargs)
    
    def get_power_details(self):
        """Get detailed power calculations"""
        calc = self.amplifier.calculate_current(
            duty_cycle=self.duty_cycle,
            transient_factor=float(self.distribution_plan.transient_headroom)
        )
        return {
            'per_unit': calc,
            'total': {
                'continuous_watts': calc['continuous_watts'] * self.quantity,
                'peak_watts': calc['peak_watts'] * self.quantity,
                'current_amps': calc['current_amps'] * self.quantity,
                'breaker_size': math.ceil(calc['current_amps'] * self.quantity * 1.25 / 10) * 10
            }
        }
    


    #-------Audio Checklist----

class AudioChecklist(models.Model):
        """
        Dummy model for Audio Checklist admin interface
        This doesn't create a real table, just provides admin interface
        """
        class Meta:
            managed = False  # Don't create/delete DB table
            db_table = 'audio_checklist_dummy'  # Dummy table name
            verbose_name = 'Audio Checklist'
            verbose_name_plural = 'Audio Checklists'
            app_label = 'planner'



            #--------Prediction Module----
class SoundvisionPrediction(models.Model):
    """Main prediction file from L'Acoustics Soundvision"""
    project = models.ForeignKey('Project', on_delete=models.CASCADE) 
    show_day = models.ForeignKey('ShowDay', on_delete=models.CASCADE, related_name='predictions')
    file_name = models.CharField(max_length=255)
    version = models.CharField(max_length=50, blank=True)
    date_generated = models.DateField(null=True, blank=True)
    pdf_file = models.FileField(upload_to='predictions/', blank=True, null=True)
    raw_data = models.JSONField(default=dict, blank=True)  # Store parsed data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Soundvision Prediction"
        verbose_name_plural = "Soundvision Predictions"    
    
    def __str__(self):
        return f"{self.show_day} - {self.file_name}"
    
    @property
    def unique_array_names(self):
        """Get list of unique array base names (without symmetry suffixes)"""
        names = set()
        for array in self.speaker_arrays.all():
            # Extract base name (e.g., "KIVA II 1" from "KIVA II 1_YZ Sym")
            base_name = array.source_name.split('_')[0].strip()
            names.add(base_name)
        return sorted(list(names))

class SpeakerArray(models.Model):
    """Individual speaker array configuration"""
    CONFIGURATION_TYPES = (
        ('vertical_flown', 'Vertical, Flown Array'),
        ('vertical_ground', 'Vertical, Ground Stack'),
        ('horizontal_flown', 'Horizontal, Flown Array'),
        ('horizontal_ground', 'Horizontal, Ground Stack'),
    )
    
    BUMPER_TYPES = (
        ('KIBU-SB', 'KIBU-SB'),
        ('KIBU II', 'KIBU II'),
        ('M-BUMP', 'M-BUMP'),
        ('K1-BUMP', 'K1-BUMP'),
        ('K2-BUMP', 'K2-BUMP'),
        ('A-BUMP', 'A-BUMP'),
        ('NONE', 'No Bumper'),
    )
    
    prediction = models.ForeignKey(SoundvisionPrediction, on_delete=models.CASCADE, related_name='speaker_arrays')
    source_name = models.CharField(max_length=100)  # Full name e.g., "KIVA II 1_YZ Sym"
    array_base_name = models.CharField(max_length=100)  # Base name e.g., "KIVA II 1"
    symmetry_type = models.CharField(max_length=50, blank=True)  # e.g., "YZ Sym", "YZ Sym_YZ Sym"
    group_context = models.CharField(max_length=50, blank=True)  # Original group (MAINS, CENTER, etc) for reference
    configuration = models.CharField(max_length=50, choices=CONFIGURATION_TYPES)
    bumper_type = models.CharField(max_length=20, choices=BUMPER_TYPES)
    
    # Position data
    position_x = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    position_y = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    position_z = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    
    # Angles
    site_angle = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    azimuth = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    top_site = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    bottom_site = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    
    # Motor/Rigging data
    num_motors = models.IntegerField(default=1)
    front_pickup_position = models.CharField(max_length=100, blank=True)
    rear_pickup_position = models.CharField(max_length=100, blank=True)
    front_motor_load_lb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    rear_motor_load_lb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    
    # Weight data
    total_weight_lb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    enclosure_weight_lb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    
    # Dimensions
    bottom_elevation = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, )
    spatial_dimensions = models.CharField(max_length=100, blank=True)  # "X; Y; Z"
    
    # For KARA - MBar hole position
    mbar_hole = models.CharField(max_length=10, blank=True)  # "A" or "B"
    
    # Calculated fields
    is_single_point = models.BooleanField(default=False)
    bumper_angle = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Speaker Array"
        verbose_name_plural = "    ├─ Speaker Arrays"  # Child
        ordering = ['prediction', 'array_base_name']  #
    
    def __str__(self):
        return f"{self.source_name} ({self.prediction.show_day})"
    
    @property
    def display_name(self):
        """Display name for the array"""
        # If it has symmetry, show it
        if self.symmetry_type:
            position = "L" if self.position_x and self.position_x < 0 else "R"
            return f"{self.array_base_name} - {position}"
        return self.array_base_name
    
    @property
    def trim_height(self):
        """Bottom trim height in feet"""
        return self.bottom_elevation if self.bottom_elevation else None
    
    @property
    def trim_height_display(self):
        """Formatted trim height display"""
        if self.bottom_elevation:
            feet = int(self.bottom_elevation)
            inches = int((float(self.bottom_elevation) - feet) * 12)
            return f"{feet}' {inches}\""
        return "N/A"
    
    @property
    def total_motor_load(self):
        """Total motor load in pounds"""
        if self.front_motor_load_lb and self.rear_motor_load_lb:
            return self.front_motor_load_lb + self.rear_motor_load_lb
        elif self.total_weight_lb:
            return self.total_weight_lb
        return None
    
    @property
    def rigging_display(self):
        """Display string for rigging configuration"""
        if self.is_single_point:
            if self.front_pickup_position:
                # Extract hole number from position string
                hole = self.front_pickup_position.split(':')[0] if ':' in self.front_pickup_position else self.front_pickup_position
                return f"Hole {hole}"
            return "Single Point"
        else:
            if self.bumper_angle is not None:
                return f"Bumper {self.bumper_angle}°"
            return "Dual Point"
    
    @property
    def is_kara(self):
        """Check if this is a KARA array"""
        return 'KARA' in self.array_base_name.upper()
    
    def calculate_bumper_angle(self):
        """Calculate bumper angle for dual-point rigging"""
        if self.num_motors == 2 and self.top_site is not None:
            # For dual-point, bumper angle is typically the negative of the array site angle
            self.bumper_angle = -self.top_site
        else:
            self.bumper_angle = None
        return self.bumper_angle
    
    def parse_array_name(self):
        """Parse the source name to extract base name and symmetry"""
        parts = self.source_name.split('_')
        self.array_base_name = parts[0].strip()
        if len(parts) > 1:
            self.symmetry_type = '_'.join(parts[1:]).strip()
        else:
            self.symmetry_type = ''

class SpeakerCabinet(models.Model):
    """Individual speaker cabinet in an array"""
    SPEAKER_MODELS = (
        ('KIVA II', 'KIVA II'),
        ('KARA II', 'KARA II'),
        ('K1', 'K1'),
        ('K2', 'K2'),
        ('K3', 'K3'),
        ('A10', 'A10 (Focus/Wide)'),
        ('A15', 'A15 (Focus/Wide)'),
        ('ARCS', 'ARCS (Focus/Wide)'),
        ('SB15M', 'SB15M'),
        ('SB18', 'SB18'),
        ('SB28', 'SB28'),
        ('KS21', 'KS21'),
        ('KS28', 'KS28'),
    )
    
    PANFLEX_OPTIONS = (
        ('55/55', '55°/55°'),
        ('55/35', '55°/35°'),
        ('35/55', '35°/55°'),
        ('35/35', '35°/35°'),
        ('70/70', '70°/70°'),
        ('110/110', '110°/110°'),
        ('FOCUS', 'Focus'),
        ('WIDE', 'Wide'),
    )
    
    array = models.ForeignKey(SpeakerArray, on_delete=models.CASCADE, related_name='cabinets')
    position_number = models.IntegerField()  # Position in array (1 = top)
    speaker_model = models.CharField(max_length=20, choices=SPEAKER_MODELS)
    
    # Angles
    angle_to_next = models.DecimalField(max_digits=5, decimal_places=1, default=0)  # Angle between this and next cabinet
    site_angle = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)  # Absolute site angle
    
    # Position
    top_z = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    bottom_z = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    
    # KARA specific
    panflex_setting = models.CharField(max_length=10, choices=PANFLEX_OPTIONS, blank=True)
    
    class Meta:
        verbose_name = "Speaker Cabinet"
        verbose_name_plural = "    └─ Speaker Cabinets"  # Child
        ordering = ['id']  #
    
    def __str__(self):
        angle_str = f" ({self.angle_to_next}°)" if self.angle_to_next else ""
        panflex_str = f" [{self.panflex_setting}]" if self.panflex_setting else ""
        return f"#{self.position_number} {self.speaker_model}{angle_str}{panflex_str}"            
    


    #------Invitation Module----

    import uuid
from django.utils import timezone


class Invitation(models.Model):
    """
    Stores project invitations sent to users via email.
    Users click the unique link to accept and become ProjectMembers.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]
    
    ROLE_CHOICES = [
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    ]
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='invitations'
    )
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    invited_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='members_invite'
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-invited_at']
        unique_together = [['project', 'email', 'status']]  # Prevent duplicate pending invites
    
    def __str__(self):
        return f"{self.email} invited to {self.project.name} as {self.role}"
    
    def is_valid(self):
        """Check if invitation is still valid (pending and not expired)"""
        if self.status != 'pending':
            return False
        # Invitations expire after 7 days
        expiry_date = self.invited_at + timezone.timedelta(days=7)
        if timezone.now() > expiry_date:
            self.status = 'expired'
            self.save()
            return False
        return True
    
    def accept(self, user):
        """Accept the invitation and create ProjectMember"""
        if not self.is_valid():
            return False
        
        # Check if user's email matches invitation
        if user.email.lower() != self.email.lower():
            return False
        
        # Check if already a member
        if ProjectMember.objects.filter(project=self.project, user=user).exists():
            self.status = 'accepted'
            self.accepted_at = timezone.now()
            self.save()
            return True
        
        # Create ProjectMember
        ProjectMember.objects.create(
            project=self.project,
            user=user,
            role=self.role,
            invited_by=self.invited_by
        )
        
        # Mark invitation as accepted
        self.status = 'accepted'
        self.accepted_at = timezone.now()
        self.save()
        
        return True
    


    

