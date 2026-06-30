
# planner/forms.py

from django import forms
from django.forms import modelformset_factory
from django.contrib.contenttypes.models import ContentType
from .models import Device, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput
from .models import P1Output
from .models import  ConsoleStereoOutput
from .models import PACableSchedule, PAZone, CommPosition, CommCrewName, CommBeltPack
from .models import Console, MultitrackSession, MultitrackTemplate



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
    source_hardware = forms.ChoiceField(
        required=False,
        choices=[('', '---------')],
    )

    class Meta:
        model = ConsoleInput
        fields = [
            'dante_number',
            'input_ch',
            'source',
            'source_hardware',
            'group',
            'dca',
            'mute',
            'direct_out',
            'omni_in',
            'default_record',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Use inline styles - these WILL work
        self.fields['dante_number'].widget.attrs.update({
            'style': 'width: 40px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['input_ch'].widget.attrs.update({
            'style': 'width: 100px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['source'].widget.attrs.update({
            'style': 'width: 150px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })

        self.fields['source_hardware'].widget.attrs.update({
            'style': 'width: 120px;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['group'].widget.attrs.update({
            'style': 'width: 40px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['dca'].widget.attrs.update({
            'style': 'width: 40px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['mute'].widget.attrs.update({
            'style': 'width: 40px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['direct_out'].widget.attrs.update({
            'style': 'width: 50px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['omni_in'].widget.attrs.update({
            'style': 'width: 50px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
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
            'dante_number',
            'aux_number',
            'name',
            'mono_stereo',
            'bus_type',
            'omni_out',
            'default_record',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['dante_number'].widget.attrs.update({
            'class': 'block w-6 text-center align-middle bg-white text-black rounded-sm',
        })

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
            'dante_number',
            'matrix_number',
            'name',
            'mono_stereo',
            'omni_out',
            'default_record',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['dante_number'].widget.attrs.update({
            'class': 'block w-6 text-center align-middle bg-white text-black rounded-sm',
        })

        self.fields['matrix_number'].widget.attrs.update({
            'class': 'w-16 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mono_stereo'].widget.attrs.update({
            'class': 'mono-stereo-select'
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



# ─── Stereo/Mono Output form ────────────────────────────────────────────────

class ConsoleStereoOutputForm(forms.ModelForm):
    class Meta:
        model = ConsoleStereoOutput
        fields = ['dante_number', 'stereo_type', 'name', 'omni_out', 'default_record']
        widgets = {
            'dante_number': forms.NumberInput(attrs={
                'style': 'width: 20px !important; text-align: center;',
            }),
        }


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




#----------Device dropdowns--------
from django import forms
from django.db.models import Prefetch, IntegerField
from django.db.models.functions import Cast
from .models import (
    DeviceInput,
    DeviceOutput,
    ConsoleInput,
    ConsoleAuxOutput,
    ConsoleMatrixOutput,
    ConsoleStereoOutput,
    Console,
)


def _device_input_suggestions(project_id):
    """ConsoleInput.source values for the device-input datalist.

    Mirrors the Processor Issue #16 pattern: the inline used to render a
    Console Input dropdown FK. We replaced that with a single free-text
    signal_name combobox + datalist, scoped to the current project so
    names don't leak across shows. Existing rows keep their console_input
    FK (the device PDF's 'Console Source' column still reads it); new
    rows just store signal_name.
    """
    if not project_id:
        return []
    seen = set()
    suggestions = []
    # input_ch is a CharField, so cast to int for natural 1, 2, …, 10 order
    # (otherwise "10" sorts before "2"). Issue #28.
    qs = (ConsoleInput.objects
          .filter(console__project_id=project_id)
          .exclude(source__isnull=True)
          .exclude(source='')
          .annotate(_ch_num=Cast('input_ch', IntegerField()))
          .order_by('console__name', '_ch_num'))
    for source in qs.values_list('source', flat=True):
        name = source.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        suggestions.append(name)
    return suggestions


class DeviceInputInlineForm(forms.ModelForm):
    """Inline form for I/O Device Inputs.

    Single combobox bound to ``signal_name`` — the engineer can type freely
    or pick from a datalist sourced from project ConsoleInput.source values
    (see ``_device_input_suggestions``). The HTML datalist is rendered once
    per inline in ``device_input_grid.html``.
    """

    class Meta:
        model = DeviceInput
        fields = ("input_number", "signal_name")
        widgets = {
            'signal_name': forms.TextInput(attrs={
                'class': 'vTextField',
                'list': 'device-input-suggestions',
                'autocomplete': 'off',
            }),
        }

    def __init__(self, *args, **kwargs):
        project_id = kwargs.pop('project_id', None)
        super().__init__(*args, **kwargs)
        self.fields['input_number'].required = False
        self.fields['signal_name'].required = False
        self.input_suggestions = _device_input_suggestions(project_id)


class DeviceOutputInlineForm(forms.ModelForm):
    console_output = forms.ChoiceField(
        label="Console Output",
        required=False,
        widget=forms.Select,
        choices=[],
    )

    class Meta:
        model = DeviceOutput
        fields = ("output_number", "signal_name")  # Remove console_output from here
        
    def __init__(self, *args, **kwargs):
        # Extract project_id from kwargs
        project_id = kwargs.pop('project_id', None)
        
        super().__init__(*args, **kwargs)
        self.fields['output_number'].required = False
        self.fields['signal_name'].required = False

        # Hide signal_name widget
        self.fields['signal_name'].widget = forms.HiddenInput()

        grouped = []

        # Order outputs to match the Console admin inlines (aux_number / matrix_number
        # are CharFields, so cast to int for natural 1, 2, …, 10 order). Issue #28.
        aux_qs = ConsoleAuxOutput.objects.annotate(
            _num=Cast('aux_number', IntegerField())
        ).order_by('_num')
        matrix_qs = ConsoleMatrixOutput.objects.annotate(
            _num=Cast('matrix_number', IntegerField())
        ).order_by('_num')
        stereo_qs = ConsoleStereoOutput.objects.order_by('stereo_type')

        # Filter consoles to current project only; order matches the Consoles list.
        console_qs = Console.objects.order_by('-is_template', 'name').prefetch_related(
            Prefetch("consoleauxoutput_set", queryset=aux_qs),
            Prefetch("consolematrixoutput_set", queryset=matrix_qs),
            Prefetch("consolestereooutput_set", queryset=stereo_qs),
        )
        if project_id:
            console_qs = console_qs.filter(project_id=project_id)

        for console in console_qs:
            opts = []
            # Aux outputs
            for ao in console.consoleauxoutput_set.all():
                if ao.name:
                    opts.append((f"aux_{ao.pk}", ao.name))
            # Matrix outputs  
            for mo in console.consolematrixoutput_set.all():
                if mo.name:
                    opts.append((f"matrix_{mo.pk}", mo.name))

            for so in console.consolestereooutput_set.all():
                if so.name:
                    opts.append((f"stereo_{so.pk}", so.name))       

            if opts:
                grouped.append((console.name, opts))

        self.fields["console_output"].choices = [("", "---------")] + grouped

        # Set initial value if editing
        if self.instance and self.instance.pk and self.instance.console_output:
            if isinstance(self.instance.console_output, ConsoleAuxOutput):
                self.fields["console_output"].initial = f"aux_{self.instance.console_output.pk}"
            elif isinstance(self.instance.console_output, ConsoleMatrixOutput):
                self.fields["console_output"].initial = f"matrix_{self.instance.console_output.pk}"

    def clean_console_output(self):
        """Convert the choice field value to a dict with the object and its type"""
        console_output_value = self.cleaned_data.get('console_output')
        
        if console_output_value and console_output_value != '':
            # Parse the type and ID
            output_type, output_id = console_output_value.split('_')
            
            if output_type == 'aux':
                return {
                    'object': ConsoleAuxOutput.objects.get(pk=output_id),
                    'type': 'aux'
                }
            elif output_type == 'matrix':
                return {
                    'object': ConsoleMatrixOutput.objects.get(pk=output_id),
                    'type': 'matrix'    
                }
            



            elif output_type == 'stereo':
                return {
                    'object': ConsoleStereoOutput.objects.get(pk=output_id),
                    'type': 'stereo'
                }
        return None

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        console_output_data = self.cleaned_data.get('console_output')
        
        if console_output_data:
            console_output = console_output_data['object']
            output_type = console_output_data['type']
            
            if output_type == 'aux':
                instance.content_type = ContentType.objects.get_for_model(ConsoleAuxOutput)
            elif output_type == 'matrix':
                instance.content_type = ContentType.objects.get_for_model(ConsoleMatrixOutput)
            
            instance.object_id = console_output.pk
            instance.signal_name = console_output.name
        else:
            instance.content_type = None
            instance.object_id = None
            instance.signal_name = ""
        
        if commit:
            instance.save()
        return instance





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
        fields = ['location', 'amp_model', 'name', 'ip_address', 
          'nl4_a_pair_1', 'nl4_a_pair_2', 
          'nl4_b_pair_1', 'nl4_b_pair_2',
          'cacom_1_ch1', 'cacom_1_ch2', 'cacom_1_ch3', 'cacom_1_ch4',
          'cacom_2_ch1', 'cacom_2_ch2', 'cacom_2_ch3', 'cacom_2_ch4',
          'cacom_3_ch1', 'cacom_3_ch2', 'cacom_3_ch3', 'cacom_3_ch4',
          'cacom_4_ch1', 'cacom_4_ch2', 'cacom_4_ch3', 'cacom_4_ch4']
        
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



class AmpChannelInlineForm(forms.ModelForm):
    class Meta:
        model = AmpChannel
        fields = ['channel_number', 'channel_name', 'avb_stream', 'aes_input', 'analog_input']
        
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
class AmpChannelInlineForm(forms.ModelForm):
    class Meta:
        model = AmpChannel
        fields = ['channel_number', 'channel_name', 'avb_stream', 'aes_input', 'analog_input']
        widgets = {
            'channel_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Channel Name'
            }),
            'aes_input': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'AES Input'
            }),
            'analog_input': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Analog Input'
            }),
        }





    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'channel_number' in self.fields:
            self.fields['channel_number'].disabled = True
        
        # Remove all the AVB customization - let Django use the model's choices
        # Delete the entire "if 'avb_stream' in self.fields:" section




        # Hide input fields based on amp model capabilities (if we have an instance)
        if self.instance and self.instance.amp_id:
            try:
                amp = self.instance.amp
                if amp.amp_model:
                    # Hide fields based on what the amp model supports
                    if not amp.amp_model.has_avb_inputs:
                        if 'avb_stream' in self.fields:
                            self.fields['avb_stream'].widget = forms.HiddenInput()
                    if not amp.amp_model.has_aes_inputs:
                        if 'aes_input' in self.fields:
                            self.fields['aes_input'].widget = forms.HiddenInput()
                    if not amp.amp_model.has_analog_inputs:
                        if 'analog_input' in self.fields:
                            self.fields['analog_input'].widget = forms.HiddenInput()
            except:
                pass  # If there's any error, just show all fields


#-------P1 Processor-----

# Add these to your forms.py

from django import forms
from .models import P1Processor, P1Input, P1Output, DeviceOutput


def _processor_input_suggestions(project):
    """Device-output signal names for the processor-input datalist.

    Issue #16: the Processor input row used to have separate Name + Origin
    dropdown fields. We collapsed them into a single combobox bound to
    `label`. The user can either type freely or pick from the suggestions
    sourced here. Scoped by project to avoid leaking signal names from
    other shows.
    """
    if project is None:
        return []
    from .models import Device
    seen = set()
    suggestions = []
    qs = (Device.objects
          .filter(project=project)
          .prefetch_related('outputs')
          .order_by('name'))
    for device in qs:
        for output in device.outputs.order_by('output_number'):
            name = (output.signal_name or '').strip()
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            suggestions.append(name)
    return suggestions


class P1InputInlineForm(forms.ModelForm):
    """Form for P1 Input inline admin.

    Issue #16: single combobox for the channel name. The HTML datalist is
    rendered once per inline in the template (see p1_input_inline.html).
    """
    class Meta:
        model = P1Input
        fields = ['input_type', 'channel_number', 'label']
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'vTextField',
                'list': 'p1-input-suggestions',
                'autocomplete': 'off',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = None
        if self.instance and self.instance.pk and self.instance.p1_processor_id:
            project = self.instance.p1_processor.system_processor.project
        self.input_suggestions = _processor_input_suggestions(project)

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
    


    #--------Galaxy Processor-----

    # Add these to your forms.py file after the P1 processor forms

from .models import GalaxyProcessor, GalaxyInput, GalaxyOutput

class GalaxyInputInlineForm(forms.ModelForm):
    """Form for GALAXY Input inline admin.

    Issue #16: single combobox for the channel name. The HTML datalist is
    rendered once per inline in the template (see galaxy_input_inline.html).
    """
    class Meta:
        model = GalaxyInput
        fields = ['input_type', 'channel_number', 'label']
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'vTextField',
                'list': 'galaxy-input-suggestions',
                'autocomplete': 'off',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = None
        if self.instance and self.instance.pk and self.instance.galaxy_processor_id:
            project = self.instance.galaxy_processor.system_processor.project
        self.input_suggestions = _processor_input_suggestions(project)


class GalaxyOutputInlineForm(forms.ModelForm):
    """Form for GALAXY Output inline admin"""
    class Meta:
        model = GalaxyOutput
        fields = ['output_type', 'channel_number', 'label', 'assigned_bus', 'destination']
        widgets = {
            'label': forms.TextInput(attrs={'class': 'vTextField'}),
            'destination': forms.TextInput(attrs={'class': 'vTextField', 'placeholder': 'e.g., Amp 1 Ch 3'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Customize the bus dropdown
        if 'assigned_bus' in self.fields:
            self.fields['assigned_bus'].empty_label = "-- Not assigned --"
            self.fields['assigned_bus'].required = False
        
        # Make destination field optional
        if 'destination' in self.fields:
            self.fields['destination'].required = False


class GalaxyProcessorAdminForm(forms.ModelForm):
    """Custom form for GALAXY Processor admin"""
    class Meta:
        model = GalaxyProcessor
        fields = '__all__'
    
    import_config = forms.FileField(
        required=False,
        help_text="Optionally import configuration from Meyer Compass file",
        widget=forms.FileInput(attrs={'accept': '.xml,.json,.compass,.txt'})
    )
    
    def save(self, commit=True):
        instance = super().save(commit=commit)
        
        # Handle config import if provided
        if self.cleaned_data.get('import_config'):
            # TODO: Implement import logic based on Meyer Compass format
            pass
        
        return instance 
    


    #-----------PA Cable--------


from .models import PACableSchedule, PAZone

class PACableForm(forms.ModelForm):
    class Meta:
        model = PACableSchedule
        fields = [
            'label', 'destination', 'count', 'cable', 
            'notes', 'drawing_ref'  # Removed count2 and fan_out
        ]
        
        widgets = {
            'label': forms.Select(attrs={
                'class': 'form-control',
                'style': 'width: 100px;'
            }),
            'destination': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'width: 120px;',
                'placeholder': 'KIVA - 1'
            }),
            'count': forms.NumberInput(attrs={
                'class': 'form-control',
                'style': 'width: 60px;',
                'min': '1'
            }),
            'cable': forms.Select(attrs={
                'class': 'form-control',
                'style': 'width: 120px;'
            }),
           
            'notes': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'width: 150px;',
                'placeholder': 'Clr. 1 Top 2'
            }),
            'drawing_ref': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'width: 80px;',
                'placeholder': 'Dim ref'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field labels to match spreadsheet
        self.fields['label'].label = 'Label'
        self.fields['destination'].label = 'Destination'
        self.fields['count'].label = 'Count'
        self.fields['cable'].label = 'Cable'
        self.fields['count2'].label = 'Count'
        self.fields['fan_out'].label = 'Fan Out'
        self.fields['notes'].label = 'Notes'
        self.fields['drawing_ref'].label = 'Drawing Ref'


class PACableInlineForm(forms.ModelForm):
    """Inline form for admin interface"""
    
    class Meta:
        model = PACableSchedule
        fields = '__all__'
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color', 'value': '#FFFFFF'}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Customize field widgets for inline display
        self.fields['destination'].widget.attrs['style'] = 'width: 120px;'
        self.fields['count'].widget.attrs['style'] = 'width: 60px;'
        self.fields['notes'].widget.attrs['style'] = 'width: 150px;'
        self.fields['drawing_ref'].widget.attrs['style'] = 'width: 80px;'


# Formset for bulk entry (like spreadsheet rows)
PACableFormSet = forms.modelformset_factory(
    PACableSchedule,
    form=PACableForm,
    extra=10,  # Show 10 empty rows by default
    can_delete=True,
    can_order=False
)


# Form for managing PA Zones
class PAZoneForm(forms.ModelForm):
    class Meta:
        model = PAZone
        fields = ['name', 'zone_type', 'sort_order']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'width: 100px;',
                'placeholder': 'HL'
            }),
            'zone_type': forms.Select(attrs={
                'class': 'form-control',
                'style': 'width: 150px;'
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'style': 'width: 80px;',
                'min': '1'
            }),
        }



        #-----Comm Beltpack form
# Form for managing Comm Belt Packs with dynamic dropdowns
class CommBeltPackAdminForm(forms.ModelForm):
    """Custom form to handle dynamic field display based on system type"""
    
    position_select = forms.ModelChoiceField(
        queryset=CommPosition.objects.all(),
        required=False,
        empty_label="-- Select Position --",
        widget=forms.Select(attrs={'class': 'position-select'})
    )
    
    name_select = forms.ModelChoiceField(
        queryset=CommCrewName.objects.all(),
        required=False,
        empty_label="-- Select Name --",
        widget=forms.Select(attrs={'class': 'name-select'})
    )
    
    class Meta:
        model = CommBeltPack
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate dropdowns from saved values
        if self.instance and self.instance.position:
            try:
                pos = CommPosition.objects.get(name=self.instance.position)
                self.fields['position_select'].initial = pos
            except CommPosition.DoesNotExist:
                pass
        
        if self.instance and self.instance.name:
            try:
                crew = CommCrewName.objects.get(name=self.instance.name)
                self.fields['name_select'].initial = crew
            except CommCrewName.DoesNotExist:
                pass
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # DEBUG: Print what we're getting
        print(f"DEBUG position_select: {self.cleaned_data.get('position_select')}")
        print(f"DEBUG name_select: {self.cleaned_data.get('name_select')}")
        print(f"DEBUG instance.position before: {instance.position}")
        print(f"DEBUG instance.name before: {instance.name}")
        
        # Explicitly set position from dropdown
        if self.cleaned_data.get('position_select'):
            instance.position = self.cleaned_data['position_select'].name
        
        # Explicitly set name from dropdown
        if self.cleaned_data.get('name_select'):
            instance.name = self.cleaned_data['name_select'].name
        
        print(f"DEBUG instance.position after: {instance.position}")
        print(f"DEBUG instance.name after: {instance.name}")
        
        if commit:
            instance.save()

        return instance


# ─── Multitrack Session Form (Phase 1 v2.0) ────────────────────────────────────

class MultitrackSessionForm(forms.ModelForm):
    """ModelForm for creating / editing MultitrackSession (MTS-01, MTS-04).

    The `request` kwarg is REQUIRED — used to scope the console queryset
    to the current project. Pass via `MultitrackSessionForm(data, request=request)`.
    """

    class Meta:
        model = MultitrackSession
        fields = [
            'name',
            'console',
            'target_daw',
            'feed_source',
            'track_order_mode',
            'recorder_capacity',
            'notes',
        ]
        widgets = {
            'target_daw': forms.RadioSelect(),
            'feed_source': forms.RadioSelect(),
            'track_order_mode': forms.RadioSelect(),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    # Phase 3 — TPL-02 / D-08: owner-scoped template picker.
    # NOT in Meta.fields — MultitrackSession has no `template` FK.
    # The view (multitrack_create_view) consumes this via form.cleaned_data
    # after form.save() returns the new session, then calls
    # template.apply_to_session(session).
    template = forms.ModelChoiceField(
        queryset=MultitrackTemplate.objects.none(),   # set per-request in __init__
        required=False,
        empty_label='— None —',
        label='Start from template (optional)',
        help_text='Picking a template pre-fills the fields below.',
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

        # D-13: scope console queryset to current_project
        if request is not None and getattr(request, 'current_project', None):
            self.fields['console'].queryset = Console.objects.filter(
                project=request.current_project
            )
        else:
            self.fields['console'].queryset = Console.objects.none()

        # D-05: owner-scoped template queryset. Templates intentionally cross
        # all of this user's projects (NOT request.current_project). Setting
        # the queryset in __init__ (per-instance), NOT as a class-level attr,
        # is REQUIRED to close the IDOR vector — a class-level queryset would
        # expose every user's templates in the dropdown (RESEARCH Pitfall 6).
        if request is not None and request.user.is_authenticated:
            self.fields['template'].queryset = MultitrackTemplate.objects.filter(
                created_by=request.user
            ).order_by('name')
        else:
            self.fields['template'].queryset = MultitrackTemplate.objects.none()

        # Required-asterisk styling (UI-SPEC: required fields show *)
        for fname in ('name', 'console', 'target_daw', 'feed_source', 'track_order_mode'):
            if fname in self.fields:
                self.fields[fname].required = True

        self.fields['recorder_capacity'].required = False
        self.fields['notes'].required = False

    def clean_name(self):
        """MTS-02 unique-per-project name validation.

        UI-SPEC error string is binding — copy verbatim.
        """
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Name is required.')
        if self.request is None or not getattr(self.request, 'current_project', None):
            raise forms.ValidationError('No active project — cannot validate name.')

        existing = MultitrackSession.objects.filter(
            project=self.request.current_project,
            name=name,
        )
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                f'A session named "{name}" already exists in this project. '
                f'Pick a different name.'
            )
        return name

    def save(self, commit=True):
        """Auto-fill project from request.current_project on create."""
        instance = super().save(commit=False)
        if not instance.pk and self.request is not None:
            instance.project = self.request.current_project
        if commit:
            instance.save()
        return instance


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Console CSV Import (CSV-01..CSV-05)
# ─────────────────────────────────────────────────────────────────────────────

class ConsoleCsvUploadForm(forms.Form):
    """Upload form for Yamaha Editor channel-label CSVs.

    Creates a NEW Console in the current project from the uploaded CSV — the
    engineer names the console on this form. Accepts a single section CSV or a
    `.zip` of multiple section files.
    """
    console_name = forms.CharField(
        label='New console name',
        required=True,
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Show A FOH (QL5)',
            'autocomplete': 'off',
        }),
        help_text='A new console with this name will be created in the current project.',
    )
    csv_file = forms.FileField(
        label='CSV or zip',
        required=True,
        widget=forms.FileInput(attrs={'accept': '.csv,.zip'}),
        help_text=(
            'Yamaha CL/QL Editor or Rivage PM Editor export. '
            'Single section CSV, or a .zip of multiple section files.'
        ),
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def clean_console_name(self):
        name = (self.cleaned_data.get('console_name') or '').strip()
        if not name:
            raise forms.ValidationError('Console name is required.')
        if self.request is not None and getattr(self.request, 'current_project', None):
            if Console.objects.filter(
                project=self.request.current_project, name__iexact=name
            ).exists():
                raise forms.ValidationError(
                    f'A console named "{name}" already exists in this project. '
                    'Pick a different name.'
                )
        return name

    def clean_csv_file(self):
        f = self.cleaned_data.get('csv_file')
        if f:
            name_lower = (f.name or '').lower()
            if not (name_lower.endswith('.csv') or name_lower.endswith('.zip')):
                raise forms.ValidationError('Upload must be a .csv or .zip file.')
            # 5 MB cap — zip-bomb mitigation. Legitimate Yamaha exports are < 300 KB.
            if f.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File too large. Maximum size is 5 MB.')
        return f
