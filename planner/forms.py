
# planner/forms.py

from django import forms
from django.forms import modelformset_factory
from .models import Device, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput



class DeviceForm(forms.ModelForm):
    """Full form used when editing an existing Device."""
    class Meta:
        model = Device
        fields = ["name", "input_count", "output_count"]
        

        def clean(self):
            print("=== DEVICEFORM CLEAN METHOD ===")
            cleaned_data = super().clean()
            print(f"Cleaned data: {cleaned_data}")
            print(f"Form errors so far: {self.errors}")
            return cleaned_data
        
        def clean_fieldname(self):
            # Individual field validation
            pass
        
        def save(self, commit=True):
            # Custom save logic
            return super().save(commit)

class NameOnlyForm(forms.ModelForm):
    """
    A stripped‐down ModelForm used only on the very first “Add”:
    only name, input_count and output_count.
    """
    class Meta:
        model = Device
        fields = ["name", "input_count", "output_count"]

# … then your ConsoleInputForm, ConsoleAuxOutputForm, etc. below …


# ─── Console Input Form ────────────────────────────────────────────────────────

class ConsoleInputForm(forms.ModelForm):
    class Meta:
        model = ConsoleInput
        fields = [
            'dante_number',
            'input_ch',
            'source',
            'group',
            'dca',
            'mute',
            'direct_out',
            'omni_in',
            'omni_out',
        ]
        

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['dante_number'].widget.attrs.update({
            'class': 'block w-6 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['input_ch'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['source'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['group'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['dca'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mute'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['direct_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_in'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

InputFormSet = modelformset_factory(
    ConsoleInput,
    form=ConsoleInputForm,
    extra=10,
    can_delete=True
)

# ─── Console Output Form ───────────────────────────────────────────────────────

class ConsoleAuxOutputForm(forms.ModelForm):
    class Meta:
        model = ConsoleAuxOutput
        fields = [
            'aux_number',
            'name',
            'mono_stereo',
            'bus_type',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['aux_number'].widget.attrs.update({
            'class': 'w-16 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mono_stereo'].widget.attrs.update({
             'class': 'mono-stereo-select'
        })
        self.fields['bus_type'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

OutputFormSet = modelformset_factory(
    ConsoleAuxOutput,
    form=ConsoleAuxOutputForm,
    extra=10,
    can_delete=True
)

# ─── Console Matrix Output Form ────────────────────────────────────────────────

class ConsoleMatrixOutputForm(forms.ModelForm):
    class Meta:
        model = ConsoleMatrixOutput
        fields = [
            'matrix_number',
            'name',
            'mono_stereo',
            'destination',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['matrix_number'].widget.attrs.update({
            'class': 'w-16 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mono_stereo'].widget.attrs.update({
            'class': 'mono-stereo-select'
        })
        self.fields['destination'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

MatrixOutputFormSet = modelformset_factory(
    ConsoleMatrixOutput,
    form=ConsoleMatrixOutputForm,
    extra=10,
    can_delete=True
)


#----------Device dropdowns--------
from django import forms
from .models import (
    DeviceInput,
    DeviceOutput,
    ConsoleInput,
    ConsoleAuxOutput,
    ConsoleMatrixOutput,
    Console,
)


# planner/forms.py

from django import forms
from django.forms import modelformset_factory
from .models import Device, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput



class DeviceForm(forms.ModelForm):
    """Full form used when editing an existing Device."""
    class Meta:
        model = Device
        fields = ["name", "input_count", "output_count"]

        def clean(self):
            # Overall form validation
            cleaned_data = super().clean()
            # Your validation logic
            return cleaned_data
        
        def clean_fieldname(self):
            # Individual field validation
            pass
        
        def save(self, commit=True):
            # Custom save logic
            return super().save(commit)

class NameOnlyForm(forms.ModelForm):
    """
    A stripped‐down ModelForm used only on the very first "Add":
    only name, input_count and output_count.
    """
    class Meta:
        model = Device
        fields = ["name", "input_count", "output_count"]

# … then your ConsoleInputForm, ConsoleAuxOutputForm, etc. below …


# ─── Console Input Form ────────────────────────────────────────────────────────

class ConsoleInputForm(forms.ModelForm):
    class Meta:
        model = ConsoleInput
        fields = [
            'dante_number',
            'input_ch',
            'source',
            'group',
            'dca',
            'mute',
            'direct_out',
            'omni_in',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['dante_number'].widget.attrs.update({
            'class': 'block w-6 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['input_ch'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['source'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['group'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['dca'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mute'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['direct_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_in'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

InputFormSet = modelformset_factory(
    ConsoleInput,
    form=ConsoleInputForm,
    extra=10,
    can_delete=True
)

# ─── Console Output Form ───────────────────────────────────────────────────────

class ConsoleAuxOutputForm(forms.ModelForm):
    class Meta:
        model = ConsoleAuxOutput
        fields = [
            'aux_number',
            'name',
            'mono_stereo',
            'bus_type',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['aux_number'].widget.attrs.update({
            'class': 'w-16 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mono_stereo'].widget.attrs.update({
             'class': 'mono-stereo-select'
        })
        self.fields['bus_type'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

OutputFormSet = modelformset_factory(
    ConsoleAuxOutput,
    form=ConsoleAuxOutputForm,
    extra=10,
    can_delete=True
)

# ─── Console Matrix Output Form ────────────────────────────────────────────────

class ConsoleMatrixOutputForm(forms.ModelForm):
    class Meta:
        model = ConsoleMatrixOutput
        fields = [
            'matrix_number',
            'name',
            'mono_stereo',
            'destination',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['matrix_number'].widget.attrs.update({
            'class': 'w-16 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mono_stereo'].widget.attrs.update({
            'class': 'mono-stereo-select'
        })
        self.fields['destination'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

MatrixOutputFormSet = modelformset_factory(
    ConsoleMatrixOutput,
    form=ConsoleMatrixOutputForm,
    extra=10,
    can_delete=True
)


#----------Device dropdowns--------
from django import forms
from .models import (
    DeviceInput,
    DeviceOutput,
    ConsoleInput,
    ConsoleAuxOutput,
    ConsoleMatrixOutput,
    Console,
)


class DeviceInputInlineForm(forms.ModelForm):
    console_input = forms.ChoiceField(
        label="Console Input",
        required=False,
        widget=forms.Select,
        choices=[],
    )

    class Meta:
        model = DeviceInput
        fields = ("input_number", "console_input")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['input_number'].required = False

        grouped = []
        # grab every Console and do Python‐side filtering
        for console in Console.objects.prefetch_related("consoleinput_set"):
            opts = [
                (ci.pk, f"{ci.input_ch}: {ci.source}")
                for ci in console.consoleinput_set.all()
                if ci.source  # only non‐empty, non‐None sources
            ]
            if opts:
                grouped.append((console.name, opts))

        # always start with the blank header
        self.fields["console_input"].choices = [("", "---------")] + grouped

        # if we're editing an existing DeviceInput, preserve its current value
        if getattr(self, "instance", None) and self.instance.pk:
            self.fields["console_input"].initial = self.instance.console_input_id

    def clean_console_input(self):
        """Convert the choice field value to the actual model instance"""
        console_input_id = self.cleaned_data.get('console_input')
        if console_input_id:
            try:
                from .models import ConsoleInput
                return ConsoleInput.objects.get(pk=console_input_id)
            except ConsoleInput.DoesNotExist:
                return None
        return None


class DeviceOutputInlineForm(forms.ModelForm):
    console_output = forms.ChoiceField(
        label="Console Output",
        required=False,
        widget=forms.Select,
        choices=[],
    )

    class Meta:
        model = DeviceOutput
        fields = ("output_number", "signal_name", "console_output")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['output_number'].required = False
        self.fields['signal_name'].required = False
        
        # Hide signal_name widget
        self.fields['signal_name'].widget = forms.HiddenInput()

        grouped = []
        for console in Console.objects.prefetch_related(
            "consoleauxoutput_set", "consolematrixoutput_set"
        ):
            opts = []
            # Aux outputs
            opts += [
                (ao.pk, f"Aux {ao.aux_number}: {ao.name}")
                for ao in console.consoleauxoutput_set.all()
                if ao.name
            ]
            # Matrix outputs  
            opts += [
                (mo.pk, f"Mat {mo.matrix_number}: {mo.name}")
                for mo in console.consolematrixoutput_set.all()
                if mo.name
            ]

            if opts:
                grouped.append((console.name, opts))

        self.fields["console_output"].choices = [("", "---------")] + grouped

        if getattr(self, "instance", None) and self.instance.pk:
            self.fields["console_output"].initial = self.instance.console_output_id

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Auto-populate signal_name from console_output
        if instance.console_output:
            if hasattr(instance.console_output, 'name'):
                instance.signal_name = instance.console_output.name
            else:
                instance.signal_name = str(instance.console_output)
        
        if commit:
            instance.save()
        return instance

    def clean_console_output(self):
        """Convert the choice field value to the actual model instance"""
        console_output_id = self.cleaned_data.get('console_output')
        if console_output_id:
            try:
                from .models import ConsoleAuxOutput
                return ConsoleAuxOutput.objects.get(pk=console_output_id)
            except ConsoleAuxOutput.DoesNotExist:
                return None
        return None
    




    #---------Amps------

   # Updated forms based on spreadsheet analysis
# Add these forms to your existing forms.py file

from django import forms
from .models import Location, Amp, AmpChannel

class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'description']  # Removed location_type
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter location name (e.g., HL LA Racks, HR LA Racks)'
            }),
            # Removed location_type widget
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of this location'
            }),
        }


class AmpForm(forms.ModelForm):
    class Meta:
        model = Amp
        fields = [
            'location', 'name', 'ip_address', 'manufacturer', 'model_number', 'channel_count',
            'avb_stream', 'analogue_input', 'aes_input',
            'cacom_output', 'preset_name', 'notes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Amp name or identifier'
            }),
            'ip_address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '192.168.1.100',
                'pattern': r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Lab.gruppen, Crown, QSC'
            }),
            'model_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Model number'
            }),
            'channel_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '16',
                'value': '4'
            }),
            'avb_stream_input': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'AVB stream source'
            }),
            'analogue_input_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '32'
            }),
            'aes_input_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '16'
            }),
            'cacom_output': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'preset_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Active preset name'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes about this amp'
            }),
        }
    
    def clean_ip_address(self):
        """Validate IP address format"""
        ip = self.cleaned_data.get('ip_address')
        if ip:
            parts = ip.split('.')
            if len(parts) != 4:
                raise forms.ValidationError("Invalid IP address format")
            try:
                for part in parts:
                    num = int(part)
                    if not 0 <= num <= 255:
                        raise forms.ValidationError("IP address octets must be between 0 and 255")
            except ValueError:
                raise forms.ValidationError("IP address must contain only numbers and dots")
        return ip
    
    def clean(self):
        """Check for duplicate IP addresses in the same location"""
        cleaned_data = super().clean()
        location = cleaned_data.get('location')
        ip_address = cleaned_data.get('ip_address')
        
        if location and ip_address:
            existing_amp = Amp.objects.filter(
                location=location, 
                ip_address=ip_address
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_amp.exists():
                raise forms.ValidationError(
                    f"An amp with IP address {ip_address} already exists in {location.name}"
                )
        
        return cleaned_data



class AmpChannelForm(forms.ModelForm):
    class Meta:
        model = AmpChannel
        fields = [
            'channel_number', 'channel_name', 'avb_stream', 
            'analogue_input', 'aes_input',
            'nl4_pair_1', 'nl4_pair_2',
            'cacom_pair',  # Single field now
            'is_active', 'notes'
        ]
        
        widgets = {
            'channel_number': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '16'
            }),
            'channel_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Left, Right, Center, Sub'
            }),
            'avb_stream': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'AVB stream assignment'
            }),
            'analogue_input': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Analogue input source'
            }),
            'aes_input': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'AES input source'
            }),
            
            
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Channel notes'
            }),
        }
    
    def clean(self):
        """Ensure channel number is unique within the amp"""
        cleaned_data = super().clean()
        amp = cleaned_data.get('amp') or (self.instance.amp if self.instance and self.instance.pk else None)
        channel_number = cleaned_data.get('channel_number')
        
        if amp and channel_number:
            existing_channel = AmpChannel.objects.filter(
                amp=amp,
                channel_number=channel_number
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_channel.exists():
                raise forms.ValidationError(
                    f"Channel {channel_number} already exists for {amp.name}"
                )
        
        return cleaned_data


# Inline form for use in admin
class AmpChannelInlineForm(AmpChannelForm):
    class Meta(AmpChannelForm.Meta):
        fields = AmpChannelForm.Meta.fields
        widgets = {
            **AmpChannelForm.Meta.widgets,
            # Make widgets more compact for inline use
            'notes': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Notes'
            }),
        }


#-------P1 Processor-----

# Add these to your forms.py

from django import forms
from .models import P1Processor, P1Input, P1Output, DeviceOutput


# Replace the P1InputInlineForm in forms.py with this version that handles 'None' strings:

class P1InputInlineForm(forms.ModelForm):
    """Form for P1 Input inline admin"""
    class Meta:
        model = P1Input
        fields = ['input_type', 'channel_number', 'label', 'origin_device_output']
        widgets = {
            'label': forms.TextInput(attrs={'class': 'vTextField'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configure the origin_device_output dropdown
        if 'origin_device_output' in self.fields:
            # Get all DeviceOutputs that have meaningful signal_name populated
            # Exclude null, empty strings, and the string 'None'
            queryset = DeviceOutput.objects.exclude(
                signal_name__isnull=True
            ).exclude(
                signal_name=''
            ).exclude(
                signal_name='None'  # Exclude the string 'None'
            ).exclude(
                signal_name='none'  # Also exclude lowercase variant
            ).select_related('device').order_by('device__name', 'output_number')
            
            # Set the queryset
            self.fields['origin_device_output'].queryset = queryset
            
            # Create a nice label for each option
            def format_label(obj):
                return f"{obj.device.name} - Out {obj.output_number}: {obj.signal_name}"
            
            self.fields['origin_device_output'].label_from_instance = format_label
            
            # Set the empty option
            self.fields['origin_device_output'].empty_label = "-- Select source --"
            
            # Make it optional
            self.fields['origin_device_output'].required = False
            
            # Add CSS class for styling
            self.fields['origin_device_output'].widget.attrs['class'] = 'vSelect'
        
        # Hide the origin_device_output field for AVB inputs (they don't use it)
        if self.instance and self.instance.pk:
            if self.instance.input_type == 'AVB':
                self.fields['origin_device_output'].widget = forms.HiddenInput()
                self.fields['origin_device_output'].required = False


class P1OutputInlineForm(forms.ModelForm):
    """Form for P1 Output inline admin"""
    class Meta:
        model = P1Output
        fields = ['output_type', 'channel_number', 'label', 'assigned_bus']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Customize the bus dropdown
        if 'assigned_bus' in self.fields:
            self.fields['assigned_bus'].empty_label = "-- Not assigned --"


class P1ImportForm(forms.Form):
    """Form for importing P1 configuration from L'Acoustics Network Manager"""
    config_file = forms.FileField(
        label="P1 Configuration File",
        help_text="Upload an exported P1 configuration file from L'Acoustics Network Manager (optional)",
        required=False,
        widget=forms.FileInput(attrs={'accept': '.xml,.json,.p1,.txt'})
    )
    
    def clean_config_file(self):
        file = self.cleaned_data.get('config_file')
        
        if file:
            # Validate file type
            if not file.name.endswith(('.xml', '.json', '.p1', '.txt')):
                raise forms.ValidationError("Invalid file format. Please upload a P1 configuration file.")
            
            # Check file size (limit to 10MB)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("File too large. Maximum size is 10MB.")
        
        return file


class P1ProcessorAdminForm(forms.ModelForm):
    """Custom form for P1 Processor admin"""
    class Meta:
        model = P1Processor
        fields = '__all__'
    
    import_config = forms.FileField(
        required=False,
        help_text="Optionally import configuration from L'Acoustics Network Manager file",
        widget=forms.FileInput(attrs={'accept': '.xml,.json,.p1,.txt'})
    )
    
    def save(self, commit=True):
        instance = super().save(commit=commit)
        
        # Handle config import if provided
        if self.cleaned_data.get('import_config'):
            # TODO: Implement import logic based on file format
            # This would parse the file and update the P1Input/P1Output records
            pass
        
        return instance