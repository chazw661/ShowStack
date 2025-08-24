# Make sure these imports are at the top of your admin.py file

# At the TOP of admin.py, organize all imports together (lines 1-25):

# Django imports
# At the TOP of admin.py, organize all imports together (lines 1-25):

# Django imports
from django.contrib.contenttypes.models import ContentType
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse, path
from django.utils import timezone
from django.utils.html import format_html
from django import forms

# Model imports
from .models import Device, DeviceInput, DeviceOutput
from .models import Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput
from .models import Location, Amp, AmpChannel
from .models import SystemProcessor, P1Processor, P1Input, P1Output

# Form imports (ALL forms in one place)
from planner.forms import ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm
from .forms import DeviceInputInlineForm, DeviceOutputInlineForm
from .forms import DeviceForm, NameOnlyForm
from .forms import P1InputInlineForm, P1OutputInlineForm, P1ProcessorAdminForm

#Galaxy Processor
from .models import GalaxyProcessor, GalaxyInput, GalaxyOutput
from .forms import GalaxyInputInlineForm, GalaxyOutputInlineForm, GalaxyProcessorAdminForm

#PA Cable
import csv

#-----------PDF Creation Start------
#-----------End PDF Creation

#-----------PDF Creation Start------

#-----------End PDF Creation


class ConsoleInputInline(admin.TabularInline):
    model = ConsoleInput
    form = ConsoleInputForm
    extra = 144
    can_delete = True
    classes = ['collapse']

    

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class PrepopulatedFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                for form in self.forms:
                    for field in form.fields.values():
                        field.required = False

                for index, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial['input_ch'] = index + 1


            def add_fields(self, form, index):
                super().add_fields(form, index)    

                if hasattr(form, 'fields') and 'DELETE' in form.fields:
                     form.fields['DELETE'].label = ""


        original_str = self.model.__str__
        self.model.__str__ = lambda self: ""
        
        return PrepopulatedFormSet       

               
       


class ConsoleAuxOutputInline(admin.TabularInline):
    model = ConsoleAuxOutput
    form = ConsoleAuxOutputForm
    extra = 72
    can_delete = True
    classes = ['collapse']

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class PrepopulatedFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                for form in self.forms:
                    for field in form.fields.values():
                        field.required = False

                for index, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial['aux_number'] = index + 1

                
        return PrepopulatedFormSet


class ConsoleMatrixOutputInline(admin.TabularInline):
    model = ConsoleMatrixOutput
    form = ConsoleMatrixOutputForm
    extra = 36
    can_delete = True
    classes = ['collapse']

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class PrepopulatedFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                for form in self.forms:
                    for field in form.fields.values():
                        field.required = False

                for index, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial['matrix_number'] = index + 1


        return PrepopulatedFormSet


@admin.register(Console)
class ConsoleAdmin(admin.ModelAdmin):
    list_display = ['name']
    inlines = [
        ConsoleInputInline,
        ConsoleAuxOutputInline,
        ConsoleMatrixOutputInline,
    ]

    class Media:
        js = ['planner/js/mono_stereo_handler.js']
        css = {
            'all': ['css/custom_admin.css']
        }


# ========== Device Admin ==========


# ———— your inlines here ——————————————————————————————————

class DeviceInputInline(admin.TabularInline):
    model = DeviceInput
    form = DeviceInputInlineForm
    extra = 0  
    template = "admin/planner/device_input_grid.html"

    def get_formset(self, request, obj=None, **kwargs):
        # Calculate how many extra forms we need
        if obj:
            existing_inputs = obj.inputs.count()
            needed = obj.input_count - existing_inputs
            kwargs['extra'] = max(0, needed)  # Only add the difference, never negative
        else:
            kwargs['extra'] = 0
            
        FormSet = super().get_formset(request, obj, **kwargs)

        class InitializingFormSet(FormSet):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                # auto-populate input_number for new rows
                for idx, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial.setdefault('input_number', idx + 1)

        return InitializingFormSet


class DeviceOutputInline(admin.TabularInline):
    model = DeviceOutput
    form = DeviceOutputInlineForm
    extra = 0
    fields = ['output_number', 'signal_name']  
    template = "admin/planner/device_output_grid.html"

    def get_formset(self, request, obj=None, **kwargs):
        # Calculate how many extra forms we need
        if obj:
            existing_outputs = obj.outputs.count()
            needed = obj.output_count - existing_outputs
            kwargs['extra'] = max(0, needed)  # Only add the difference, never negative
        else:
            kwargs['extra'] = 0
            
        FormSet = super().get_formset(request, obj, **kwargs)

        class InitializingFormSet(FormSet):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                # auto-populate output_number for new rows
                for idx, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial.setdefault('output_number', idx + 1)

        return InitializingFormSet



@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    inlines = [DeviceInputInline, DeviceOutputInline]
    list_display = ('name',)

    def get_fields(self, request, obj=None):
        """
        On the add form (obj is None) show name + counts.
        On the change form, everything is in the title/inlines,
        so show no fields above the inlines.
        """
        if obj is None:
            return ['name', 'input_count', 'output_count']
        return []

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = NameOnlyForm
        else:
            kwargs['form'] = DeviceForm
        return super().get_form(request, obj, **kwargs)

    def response_add(self, request, obj, post_url_continue=None):
        # redirect into the change page so the inlines appear.
        change_url = reverse('admin:planner_device_change', args=(obj.pk,))
        return HttpResponseRedirect(change_url)
    
    
    def save_model(self, request, obj, form, change):
        print("=== SAVE_MODEL DEBUG ===")
        print(f"Form is valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        print(f"Object data: {obj.__dict__}")
        
        if not form.is_valid():
            print("FORM VALIDATION FAILED!")
            for field, errors in form.errors.items():
                print(f"Field '{field}': {errors}")
    
        super().save_model(request, obj, form, change)
    
    def save_formset(self, request, form, formset, change):
        # If you have inline formsets
        super().save_formset(request, form, formset, change)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        print("=== CHANGEFORM_VIEW ===")
        print(f"Request method: {request.method}")
        if request.method == "POST":
            print(f"POST data: {request.POST}")
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    def save_model(self, request, obj, form, change):
        print("=== SAVE_MODEL CALLED ===")
        print(f"Form is valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        super().save_model(request, obj, form, change)    





#--------Amps---------

# Updated admin classes based on spreadsheet structure
# Add these admin classes to your existing admin.py file

from .models import Location, Amp, AmpChannel

# Update your admin.py file - replace the AmpChannelInline class with this:

class AmpChannelInline(admin.TabularInline):
    model = AmpChannel
    extra = 0
    fields = ['channel_number', 'channel_name', 'avb_stream', 'analogue_input', 'aes_input', 'nl4_pair_1', 'nl4_pair_2', 'cacom_pair', 'is_active', 'notes']
    ordering = ['channel_number']
    template = 'admin/planner/amp_channel_inline.html'  
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        
        class ChannelFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                
                # Auto-populate channel numbers based on amp's channel count
                if obj and obj.channel_count:
                    # Create the right number of forms for the amp's channels
                    for i in range(obj.channel_count):
                        if i < len(self.forms):
                            form = self.forms[i]
                            if not form.instance.pk:
                                form.initial['channel_number'] = i + 1
                                # Set default channel names based on common patterns
                                channel_names = ['Left', 'Right', 'Center', 'Sub', 'Front Fill', 'Delay', 'Foldback', 'Monitor']
                                if i < len(channel_names):
                                    form.initial['channel_name'] = channel_names[i]
        
        return ChannelFormSet
    
    def get_extra(self, request, obj=None, **kwargs):
        """Set extra forms based on amp's channel count"""
        if obj and obj.channel_count:
            existing_channels = obj.channels.count()
            return max(0, obj.channel_count - existing_channels)
        return 1




class AmpInline(admin.TabularInline):
    model = Amp
    extra = 1
    fields = ['name', 'ip_address', 'manufacturer', 'model_number', 'channel_count', 'avb_stream_input', 'preset_name']
    ordering = ['ip_address']
    
def get_queryset(self, request):
    """Custom queryset to sort amps by last octet of IP (SQLite compatible)"""
    qs = super().get_queryset(request)
    # For SQLite, we'll use Python sorting instead of SQL
    return qs.order_by('ip_address')


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'amp_count', 'total_channels', 'created_at']  # Removed location_type
    list_filter = ['created_at']  # Removed location_type
    search_fields = ['name', 'description']
    inlines = [AmpInline]
    
    fieldsets = (
        ('Location Information', {
            'fields': ('name', 'description')
        }),
    )
    
    def amp_count(self, obj):
        """Display count of amps in this location"""
        return obj.amps.count()
    amp_count.short_description = 'Amps'
    
    def total_channels(self, obj):
        """Display total number of channels across all amps in location"""
        return sum(amp.channel_count for amp in obj.amps.all())
    total_channels.short_description = 'Total Channels'




@admin.register(Amp)
class AmpAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'ip_address', 'manufacturer', 'channel_count', 'created_at']
    list_filter = ['location', 'manufacturer', 'channel_count', 'cacom_output', 'created_at']
    search_fields = ['name', 'ip_address', 'model_number', 'manufacturer', 'preset_name']
    list_select_related = ['location']
    inlines = [AmpChannelInline]

    class Media:
        css = {'all': ('planner/css/amp_channel_admin.css',)
    }
    
    # Add the PDF export action
    
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('location', 'name', 'ip_address')
        }),
        ('Hardware Configuration', {
            'fields': ('manufacturer', 'model_number', 'channel_count'),
        }),
        ('Input Configuration', {
        'fields': ('avb_stream', 'analogue_input', 'aes_input'),
        'classes': ['collapse']
        }),

        ('Output Configuration', {
             'fields': ('cacom_output',),  
             'classes': ['collapse']
        }),
        ('Settings', {
            'fields': ('preset_name', 'notes'),
            'classes': ['collapse']
        }),
    )
    
    def get_queryset(self, request):
        """Sort amps by location and IP address (SQLite compatible)"""
        qs = super().get_queryset(request)
        return qs.order_by('location', 'ip_address')
    
    def save_model(self, request, obj, form, change):
        """Auto-create channels when amp is saved"""
        super().save_model(request, obj, form, change)
        
        # Create channels if they don't exist
        existing_channels = obj.channels.count()
        if existing_channels < obj.channel_count:
            for i in range(existing_channels + 1, obj.channel_count + 1):
                from .models import AmpChannel  # Import here to avoid circular import
                AmpChannel.objects.get_or_create(
                    amp=obj,
                    channel_number=i,
                    defaults={'channel_name': f'Channel {i}'}
                )



        #------------Processor------
@admin.register(SystemProcessor)
class SystemProcessorAdmin(admin.ModelAdmin):
    list_display = ['name', 'device_type', 'location', 'ip_address', 'created_at', 'configure_button']
    list_filter = ['device_type', 'location', 'created_at']
    search_fields = ['name', 'ip_address']

    def configure_button(self, obj):
     if obj.pk:  # Only show for saved objects
        if obj.device_type == 'P1':
            # Check if P1 config exists
            try:
                p1 = obj.p1_config
                url = reverse('admin:planner_p1processor_change', args=[p1.pk])
                return format_html('<a class="button" href="{}">Configure P1</a>', url)
            except P1Processor.DoesNotExist:
                # Create P1 config URL
                url = reverse('admin:planner_p1processor_add') + f'?system_processor={obj.pk}'
                return format_html('<a class="button" href="{}">Setup P1 Configuration</a>', url)
        elif obj.device_type == 'GALAXY':
            # Check if GALAXY config exists
            try:
                galaxy = obj.galaxy_config
                url = reverse('admin:planner_galaxyprocessor_change', args=[galaxy.pk])
                return format_html('<a class="button" href="{}">Configure GALAXY</a>', url)
            except GalaxyProcessor.DoesNotExist:
                # Create GALAXY config URL
                url = reverse('admin:planner_galaxyprocessor_add') + f'?system_processor={obj.pk}'
                return format_html('<a class="button" href="{}">Setup GALAXY Configuration</a>', url)
        return '-'
    configure_button.short_description = 'Configuration'
    configure_button.allow_tags = True
    
    
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:pk>/configure/', self.configure_view, name='systemprocessor-configure'),
        ]
        return custom_urls + urls
    
    
    def configure_view(self, request, pk):
        """Redirect to appropriate configuration based on device type"""
        obj = self.get_object(request, pk)
        if obj.device_type == 'P1':
            p1, created = P1Processor.objects.get_or_create(system_processor=obj)
            # If newly created and no channels exist, create them (same as P1ProcessorAdmin._create_default_channels)
            if created and not p1.inputs.exists():
                # Standard P1 channels
                for i in range(1, 5):
                    P1Input.objects.create(p1_processor=p1, input_type='ANALOG', channel_number=i, label='')
                    P1Input.objects.create(p1_processor=p1, input_type='AES', channel_number=i, label='')
                    P1Output.objects.create(p1_processor=p1, output_type='ANALOG', channel_number=i, label='')
                    P1Output.objects.create(p1_processor=p1, output_type='AES', channel_number=i, label='')
                for i in range(1, 9):
                    P1Input.objects.create(p1_processor=p1, input_type='AVB', channel_number=i, label='')
                    P1Output.objects.create(p1_processor=p1, output_type='AVB', channel_number=i, label='')
            return HttpResponseRedirect(
                reverse('admin:planner_p1processor_change', args=[p1.pk])
            )
        elif obj.device_type == 'GALAXY':
            galaxy, created = GalaxyProcessor.objects.get_or_create(system_processor=obj)
            # If newly created and no channels exist, create them (same as GalaxyProcessorAdmin._create_default_channels)
            if created and not galaxy.inputs.exists():
                # Standard GALAXY channels
                for i in range(1, 9):
                    GalaxyInput.objects.create(galaxy_processor=galaxy, input_type='ANALOG', channel_number=i, label='')
                    GalaxyInput.objects.create(galaxy_processor=galaxy, input_type='AES', channel_number=i, label='')
                    GalaxyOutput.objects.create(galaxy_processor=galaxy, output_type='ANALOG', channel_number=i, label='', destination='')
                    GalaxyOutput.objects.create(galaxy_processor=galaxy, output_type='AES', channel_number=i, label='', destination='')
                for i in range(1, 17):
                    GalaxyInput.objects.create(galaxy_processor=galaxy, input_type='AVB', channel_number=i, label='')
                    GalaxyOutput.objects.create(galaxy_processor=galaxy, output_type='AVB', channel_number=i, label='', destination='')
            return HttpResponseRedirect(
                reverse('admin:planner_galaxyprocessor_change', args=[galaxy.pk])
            )
        messages.warning(request, f"Configuration for {obj.get_device_type_display()} not yet implemented.")
        return HttpResponseRedirect(reverse('admin:planner_systemprocessor_change', args=[pk]))
        

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj and obj.device_type in ['P1', 'GALAXY']:
            configure_url = reverse('admin:systemprocessor-configure', args=[obj.pk])
            extra_context['show_configure_button'] = True
            extra_context['configure_url'] = configure_url
        return super().change_view(request, object_id, form_url, extra_context)


#--------P1 Processor----



# ========== P1 Processor Admin ==========

class P1InputInline(admin.TabularInline):
    model = P1Input
    form = P1InputInlineForm
    extra = 0
    fields = ['input_type', 'channel_number', 'label', 'origin_device_output']
    readonly_fields = ['input_type', 'channel_number']
    can_delete = False
    template = 'admin/planner/p1_input_inline.html'  # Use custom template
     
    def has_add_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('origin_device_output__device').order_by('input_type', 'channel_number')
    
    class Media:
        js = ('admin/js/p1_input_admin.js',)


class P1OutputInline(admin.TabularInline):
    model = P1Output
    form = P1OutputInlineForm
    extra = 0
    fields = ['output_type', 'channel_number', 'label', 'assigned_bus']
    readonly_fields = ['output_type', 'channel_number']
    can_delete = False
    template = 'admin/planner/p1_output_inline.html'  # Use custom template
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by('output_type', 'channel_number')


# First, unregister if it was already registered
try:
    admin.site.unregister(P1Processor)
except admin.sites.NotRegistered:
    pass

@admin.register(P1Processor)
class P1ProcessorAdmin(admin.ModelAdmin):
    form = P1ProcessorAdminForm
    change_form_template = 'admin/planner/p1processor/change_form.html'
    list_display = ['system_processor', 'get_location', 'get_ip_address', 'input_count', 'output_count']
    list_filter = ['system_processor__location']
    search_fields = ['system_processor__name', 'system_processor__ip_address']
    actions = ['export_configurations']
    inlines = [P1InputInline, P1OutputInline]
    
    # Hide from main admin index
    def has_module_permission(self, request):
        # Hide from main admin menu but still accessible via direct URL
        return False
    
    def get_fieldsets(self, request, obj=None):
        """Different fieldsets for add vs change forms"""
        if obj is None:  # Add form
            return (
                ('Create P1 Configuration', {
                    'fields': ('system_processor', 'notes'),
                    'description': 'Select the system processor and add any initial notes. Channels will be auto-created after saving.'
                }),
            )
        else:  # Change form
            return (
                ('System Processor', {
                    'fields': ('system_processor',),
                    'classes': ('collapse',),
                    'description': 'This P1 configuration is linked to the system processor above.'
                }),
                ('P1 Configuration Notes', {
                    'fields': ('notes',),
                    'classes': ('wide',)
                }),
                ('Import Configuration', {
                    'fields': ('import_config',),
                    'classes': ('collapse',),
                    'description': 'Optionally import configuration from L\'Acoustics Network Manager'
                }),
            )
    
    def get_inline_instances(self, request, obj=None):
        """Only show inlines on change form, not add form"""
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing P1
            return ['system_processor']
        return []
    
    def response_add(self, request, obj, post_url_continue=None):
        """After adding, redirect to change form to show the inlines"""
        # The channels are created in save_model, so they'll be ready
        change_url = reverse('admin:planner_p1processor_change', args=(obj.pk,))
        messages.success(request, f'P1 Processor created with standard channel configuration (4 Analog, 4 AES, 8 AVB channels).')
        return HttpResponseRedirect(change_url)
    
    def save_model(self, request, obj, form, change):
        """Save the model and create channels if new"""
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)
        
        if is_new:
            # Auto-create standard P1 channels
            self._create_default_channels(obj)
            messages.info(request, 'Standard P1 channels have been created. You can now configure each channel.')
    
    def _create_default_channels(self, p1_processor):
        """Create default P1 channels based on standard configuration"""
        # Check if channels already exist to avoid duplicates
        if p1_processor.inputs.exists() or p1_processor.outputs.exists():
            return
        
        # Create Inputs
        # 4 Analog inputs
        for i in range(1, 5):
            P1Input.objects.create(
                p1_processor=p1_processor,
                input_type='ANALOG',
                channel_number=i,
                label=''  # Blank label
            )
        
        # 4 AES inputs
        for i in range(1, 5):
            P1Input.objects.create(
                p1_processor=p1_processor,
                input_type='AES',
                channel_number=i,
                label=''  # Blank label
            )
        
        # 8 AVB inputs
        for i in range(1, 9):
            P1Input.objects.create(
                p1_processor=p1_processor,
                input_type='AVB',
                channel_number=i,
                label=''  # Blank label
            )
        
        # Create Outputs
        # 4 Analog outputs
        for i in range(1, 5):
            P1Output.objects.create(
                p1_processor=p1_processor,
                output_type='ANALOG',
                channel_number=i,
                label=''  # Blank label
            )
        
        # 4 AES outputs
        for i in range(1, 5):
            P1Output.objects.create(
                p1_processor=p1_processor,
                output_type='AES',
                channel_number=i,
                label=''  # Blank label
            )
        
        # 8 AVB outputs
        for i in range(1, 9):
            P1Output.objects.create(
                p1_processor=p1_processor,
                output_type='AVB',
                channel_number=i,
                label=''  # Blank label
            )
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context['title'] = f'P1 Configuration for {obj.system_processor.name}'
            extra_context['subtitle'] = f'Location: {obj.system_processor.location.name} | IP: {obj.system_processor.ip_address}'
            # Add back link to system processor
            back_url = reverse('admin:planner_systemprocessor_change', args=[obj.system_processor.pk])
            extra_context['back_link'] = format_html(
                '<a href="{}">← Back to System Processor</a>',
                back_url
            )
            extra_context['show_summary_link'] = True
            extra_context['summary_url'] = f'/p1/{object_id}/summary/'
        return super().change_view(request, object_id, form_url, extra_context)
    
    def add_view(self, request, form_url='', extra_context=None):
        """Customize the add view"""
        extra_context = extra_context or {}
        extra_context['title'] = 'Create New P1 Processor Configuration'
        
        # If system_processor is in GET params, show which one
        if 'system_processor' in request.GET:
            try:
                sp_id = request.GET['system_processor']
                sp = SystemProcessor.objects.get(pk=sp_id)
                extra_context['subtitle'] = f'For System Processor: {sp.name}'
            except (SystemProcessor.DoesNotExist, ValueError):
                pass
        
        return super().add_view(request, form_url, extra_context)
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Pre-populate system_processor if passed in URL
        if 'system_processor' in request.GET and not obj:
            form.base_fields['system_processor'].initial = request.GET['system_processor']
        return form
    
    def get_location(self, obj):
        return obj.system_processor.location.name
    get_location.short_description = 'Location'
    
    def get_ip_address(self, obj):
        return obj.system_processor.ip_address
    get_ip_address.short_description = 'IP Address'
    
    def input_count(self, obj):
        return obj.inputs.count()
    input_count.short_description = 'Inputs'
    
    def output_count(self, obj):
        return obj.outputs.count()
    output_count.short_description = 'Outputs'
    
    def export_configurations(self, request, queryset):
        """Export selected P1 configurations"""
        if queryset.count() == 1:
            # Single export - redirect to export view
            return HttpResponseRedirect(f'/p1/{queryset.first().id}/export/')
        else:
            # Multiple export - create combined JSON
            all_configs = []
            for p1 in queryset:
                config = {
                    'processor': {
                        'name': p1.system_processor.name,
                        'location': p1.system_processor.location.name,
                        'ip_address': str(p1.system_processor.ip_address),
                    },
                    'inputs': list(p1.inputs.values()),
                    'outputs': list(p1.outputs.values())
                }
                all_configs.append(config)
            
            response = JsonResponse({'configurations': all_configs}, json_dumps_params={'indent': 2})
            response['Content-Disposition'] = 'attachment; filename="p1_configs.json"'
            return response
    
    class Media:
        css = {
            'all': ('admin/css/p1_processor_admin.css',)
        }
        js = ('admin/js/p1_input_admin.js',)


        # ========== GALAXY Processor Admin ==========

class GalaxyInputInline(admin.TabularInline):
    model = GalaxyInput
    form = GalaxyInputInlineForm
    extra = 0
    fields = ['input_type', 'channel_number', 'label', 'origin_device_output']
    readonly_fields = ['input_type', 'channel_number']
    can_delete = False
    template = 'admin/planner/galaxy_input_inline.html'
     
    def has_add_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('origin_device_output__device').order_by('input_type', 'channel_number')
    
    class Media:
        js = ('admin/js/galaxy_input_admin.js',)


class GalaxyOutputInline(admin.TabularInline):
    model = GalaxyOutput
    form = GalaxyOutputInlineForm
    extra = 0
    fields = ['output_type', 'channel_number', 'label', 'assigned_bus', 'destination']
    readonly_fields = ['output_type', 'channel_number']
    can_delete = False
    template = 'admin/planner/galaxy_output_inline.html'
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by('output_type', 'channel_number')


@admin.register(GalaxyProcessor)
class GalaxyProcessorAdmin(admin.ModelAdmin):
    form = GalaxyProcessorAdminForm
    change_form_template = 'admin/planner/galaxyprocessor/change_form.html'
    list_display = ['system_processor', 'get_location', 'get_ip_address', 'input_count', 'output_count']
    list_filter = ['system_processor__location']
    search_fields = ['system_processor__name', 'system_processor__ip_address']
    actions = ['export_configurations']
    inlines = [GalaxyInputInline, GalaxyOutputInline]
    
    # Hide from main admin index (like P1)
    def has_module_permission(self, request):
        return False
    
    def get_fieldsets(self, request, obj=None):
        """Different fieldsets for add vs change forms"""
        if obj is None:  # Add form
            return (
                ('Create GALAXY Configuration', {
                    'fields': ('system_processor', 'notes'),
                    'description': 'Select the system processor and add any initial notes. Channels will be auto-created after saving.'
                }),
            )
        else:  # Change form
            return (
                ('System Processor', {
                    'fields': ('system_processor',),
                    'classes': ('collapse',),
                    'description': 'This GALAXY configuration is linked to the system processor above.'
                }),
                ('GALAXY Configuration Notes', {
                    'fields': ('notes',),
                    'classes': ('wide',)
                }),
                ('Import Configuration', {
                    'fields': ('import_config',),
                    'classes': ('collapse',),
                    'description': 'Optionally import configuration from Meyer Compass software'
                }),
            )
    
    def get_inline_instances(self, request, obj=None):
        """Only show inlines on change form, not add form"""
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing GALAXY
            return ['system_processor']
        return []
    
    def response_add(self, request, obj, post_url_continue=None):
        """After adding, redirect to change form to show the inlines"""
        change_url = reverse('admin:planner_galaxyprocessor_change', args=(obj.pk,))
        messages.success(request, f'GALAXY Processor created with standard channel configuration (8 Analog, 8 AES, 16 AVB channels).')
        return HttpResponseRedirect(change_url)
    
    def save_model(self, request, obj, form, change):
        """Save the model and create channels if new"""
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)
        
        if is_new:
            # Auto-create standard GALAXY channels
            self._create_default_channels(obj)
            messages.info(request, 'Standard GALAXY channels have been created. You can now configure each channel.')
    
    def _create_default_channels(self, galaxy_processor):
        """Create default GALAXY channels based on standard configuration"""
        # Check if channels already exist to avoid duplicates
        if galaxy_processor.inputs.exists() or galaxy_processor.outputs.exists():
            return
        
        # Create Inputs - Meyer GALAXY typically has more channels
        # 8 Analog inputs
        for i in range(1, 9):
            GalaxyInput.objects.create(
                galaxy_processor=galaxy_processor,
                input_type='ANALOG',
                channel_number=i,
                label=''
            )
        
        # 8 AES inputs (4 stereo pairs)
        for i in range(1, 9):
            GalaxyInput.objects.create(
                galaxy_processor=galaxy_processor,
                input_type='AES',
                channel_number=i,
                label=''
            )
        
        # 16 AVB/Milan inputs
        for i in range(1, 17):
            GalaxyInput.objects.create(
                galaxy_processor=galaxy_processor,
                input_type='AVB',
                channel_number=i,
                label=''
            )
        
        # Create Outputs
        # 8 Analog outputs
        for i in range(1, 9):
            GalaxyOutput.objects.create(
                galaxy_processor=galaxy_processor,
                output_type='ANALOG',
                channel_number=i,
                label='',
                destination=''
            )
        
        # 8 AES outputs
        for i in range(1, 9):
            GalaxyOutput.objects.create(
                galaxy_processor=galaxy_processor,
                output_type='AES',
                channel_number=i,
                label='',
                destination=''
            )
        
        # 16 AVB/Milan outputs
        for i in range(1, 17):
            GalaxyOutput.objects.create(
                galaxy_processor=galaxy_processor,
                output_type='AVB',
                channel_number=i,
                label='',
                destination=''
            )
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context['title'] = f'GALAXY Configuration for {obj.system_processor.name}'
            extra_context['subtitle'] = f'Location: {obj.system_processor.location.name} | IP: {obj.system_processor.ip_address}'
            # Add back link to system processor
            back_url = reverse('admin:planner_systemprocessor_change', args=[obj.system_processor.pk])
            extra_context['back_link'] = format_html(
                '<a href="{}">← Back to System Processor</a>',
                back_url
            )
            extra_context['show_summary_link'] = True
            extra_context['summary_url'] = f'/galaxy/{object_id}/summary/'
        return super().change_view(request, object_id, form_url, extra_context)
    
    def add_view(self, request, form_url='', extra_context=None):
        """Customize the add view"""
        extra_context = extra_context or {}
        extra_context['title'] = 'Create New GALAXY Processor Configuration'
        
        # If system_processor is in GET params, show which one
        if 'system_processor' in request.GET:
            try:
                sp_id = request.GET['system_processor']
                sp = SystemProcessor.objects.get(pk=sp_id)
                extra_context['subtitle'] = f'For System Processor: {sp.name}'
            except (SystemProcessor.DoesNotExist, ValueError):
                pass
        
        return super().add_view(request, form_url, extra_context)
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Pre-populate system_processor if passed in URL
        if 'system_processor' in request.GET and not obj:
            form.base_fields['system_processor'].initial = request.GET['system_processor']
        return form
    
    def get_location(self, obj):
        return obj.system_processor.location.name
    get_location.short_description = 'Location'
    
    def get_ip_address(self, obj):
        return obj.system_processor.ip_address
    get_ip_address.short_description = 'IP Address'
    
    def input_count(self, obj):
        return obj.inputs.count()
    input_count.short_description = 'Inputs'
    
    def output_count(self, obj):
        return obj.outputs.count()
    output_count.short_description = 'Outputs'
    
    def export_configurations(self, request, queryset):
        """Export selected GALAXY configurations"""
        if queryset.count() == 1:
            # Single export - redirect to export view
            return HttpResponseRedirect(f'/galaxy/{queryset.first().id}/export/')
        else:
            # Multiple export - create combined JSON
            all_configs = []
            for galaxy in queryset:
                config = {
                    'processor': {
                        'name': galaxy.system_processor.name,
                        'location': galaxy.system_processor.location.name,
                        'ip_address': str(galaxy.system_processor.ip_address),
                    },
                    'inputs': list(galaxy.inputs.values()),
                    'outputs': list(galaxy.outputs.values())
                }
                all_configs.append(config)
            
            response = JsonResponse({'configurations': all_configs}, json_dumps_params={'indent': 2})
            response['Content-Disposition'] = 'attachment; filename="galaxy_configs.json"'
            return response
    
    class Media:
        css = {
            'all': ('admin/css/galaxy_processor_admin.css',)
        }
        js = ('admin/js/galaxy_input_admin.js',)




#-----------P.A, Cable------


# Add these to your admin.py file

from .models import PACableSchedule, PAZone
from .forms import PACableInlineForm, PAZoneForm

class PACableInline(admin.TabularInline):
    """Inline admin for PA cables - spreadsheet-like entry"""
    model = PACableSchedule
    form = PACableInlineForm
    extra = 5
    fields = [
        'label', 'destination', 'count', 'cable', 
        'count2', 'fan_out', 'notes', 'drawing_ref'
    ]
    
    class Media:
        css = {
            'all': ('planner/css/pa_cable_admin.css',)
        }
        js = ('planner/js/pa_cable_calculations.js',)



# First, register the PAZone admin
@admin.register(PAZone)
class PAZoneAdmin(admin.ModelAdmin):
    form = PAZoneForm
    list_display = ['name', 'description', 'zone_type', 'sort_order', 'location']
    list_filter = ['zone_type', 'location']
    search_fields = ['name', 'description']
    list_editable = ['sort_order']
    ordering = ['sort_order', 'name']
    
    actions = ['create_default_zones']
    
    def create_default_zones(self, request, queryset):
        """Create standard L'Acoustics zones"""
        PAZone.create_default_zones()
        self.message_user(request, "Default zones have been created.")
    create_default_zones.short_description = "Create default L'Acoustics zones"


# PA Cable Admin
@admin.register(PACableSchedule)
class PACableAdmin(admin.ModelAdmin):
    """Admin for PA Cable Schedule"""
    form = PACableInlineForm
    list_display = [
        'label_display', 'destination', 'count', 
        'cable_display', 'count2', 'fan_out_display', 
        'notes', 'drawing_ref'
    ]
    list_filter = ['label', 'cable', 'fan_out']
    search_fields = ['destination', 'notes', 'drawing_ref']
    list_editable = ['count', 'count2']  # Changed from 'quantity' and 'length_per_run'
    
    change_list_template = 'admin/planner/pacableschedule/change_list.html'
    
    fieldsets = (
        ('Cable Configuration', {
            'fields': ('label', 'destination', 'count', 'cable')
        }),
        ('Fan Out Configuration', {
            'fields': ('count2', 'fan_out'),
            'description': 'Additional hardware/splitters'
        }),
        ('Documentation', {
            'fields': ('notes', 'drawing_ref')
        })
    )
    
    actions = ['export_cable_schedule', 'generate_pull_sheet']
    
    def label_display(self, obj):
        return f"{obj.label.name}" if obj.label else "-"
    label_display.short_description = 'Label'
    label_display.admin_order_field = 'label'
    
    def cable_display(self, obj):
        return obj.get_cable_display()
    cable_display.short_description = 'Cable'
    cable_display.admin_order_field = 'cable'
    
    def fan_out_display(self, obj):
        return obj.get_fan_out_display() if obj.fan_out else "-"
    fan_out_display.short_description = 'Fan Out'
    fan_out_display.admin_order_field = 'fan_out'
    
    def changelist_view(self, request, extra_context=None):
        """Add cable summary to the list view"""
        response = super().changelist_view(request, extra_context=extra_context)
        
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
        
        # Calculate cable summaries including fan outs
        from django.db.models import Sum
        cable_summary = {}
        fan_out_summary = {}
        
        for cable_type in PACableSchedule.CABLE_TYPE_CHOICES:
            cables = qs.filter(cable=cable_type[0])
            if cables.exists():
                total_length = sum(c.total_cable_length for c in cables)
                if total_length > 0:
                    cable_summary[cable_type[1]] = {
                        'total_runs': cables.aggregate(Sum('count'))['count__sum'] or 0,
                        'total_length': total_length,
                        'with_20_percent': total_length * 1.2,
                        'hundreds': int(total_length * 1.2 / 100),
                        'twenty_fives': int((total_length * 1.2 % 100) / 25),
                        'remainder': (total_length * 1.2) % 25,
                        'couplers': int(total_length * 1.2 / 100) - 1 if total_length > 100 else 0,
                    }
        
        # Calculate fan out totals
        for fan_out_type in PACableSchedule.FAN_OUT_CHOICES:
            if fan_out_type[0]:  # Skip empty choice
                fan_outs = qs.filter(fan_out=fan_out_type[0])
                if fan_outs.exists():
                    total_fan_outs = fan_outs.aggregate(Sum('count2'))['count2__sum'] or 0
                    if total_fan_outs > 0:
                        fan_out_summary[fan_out_type[1]] = total_fan_outs
        
        response.context_data['cable_summary'] = cable_summary
        response.context_data['fan_out_summary'] = fan_out_summary
        response.context_data['grand_total'] = sum(s['total_length'] for s in cable_summary.values())
        response.context_data['grand_total_with_overage'] = sum(s['with_20_percent'] for s in cable_summary.values())
        
        return response
    
    def export_cable_schedule(self, request, queryset):
        """Export cable schedule to CSV with full calculations"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="pa_cable_schedule.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['L\'ACOUSTICS PA CABLE SCHEDULE'])
        writer.writerow([f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        
        writer.writerow([
            'Label', 'Destination', 'Count', 'Cable', 
            'Count2', 'Fan Out', 'Notes', 'Drawing Ref'
        ])
        
        # Group by cable type for summary
        cable_totals = {}
        fan_out_totals = {}
        
        # Write data rows
        for cable in queryset.order_by('label__sort_order', 'cable'):
            writer.writerow([
                cable.label.name if cable.label else '',
                cable.destination,
                cable.count,
                cable.get_cable_display(),
                cable.count2 if cable.count2 else '',
                cable.get_fan_out_display() if cable.fan_out else '',
                cable.notes or '',
                cable.drawing_ref or ''
            ])
            
            # Track cable totals
            cable_type_name = cable.get_cable_display()
            if cable_type_name not in cable_totals:
                cable_totals[cable_type_name] = {
                    'quantity': 0,
                    'total_length': 0
                }
            cable_totals[cable_type_name]['quantity'] += cable.count
            cable_totals[cable_type_name]['total_length'] += cable.total_cable_length
            
            # Track fan out totals
            if cable.fan_out and cable.count2:
                fan_out_name = cable.get_fan_out_display()
                if fan_out_name not in fan_out_totals:
                    fan_out_totals[fan_out_name] = 0
                fan_out_totals[fan_out_name] += cable.count2
        
        # Write cable summary
        writer.writerow([])
        writer.writerow(['CABLE SUMMARY WITH ORDERING CALCULATIONS'])
        writer.writerow([
            'Cable Type', 'Total Runs', 'Total Length (ft)', 
            '20% Overage', 'Total w/Overage',
            '100\' Lengths', '25\' Lengths', 'Remainder (ft)', 'Couplers Needed'
        ])
        
        grand_total = 0
        grand_total_with_overage = 0
        
        for cable_type, totals in cable_totals.items():
            total = totals['total_length']
            overage = total * 0.2
            total_with_overage = total * 1.2
            
            hundreds = int(total_with_overage / 100)
            twenty_fives = int((total_with_overage % 100) / 25)
            remainder = total_with_overage % 25
            couplers = hundreds - 1 if hundreds > 1 else 0
            
            writer.writerow([
                cable_type,
                totals['quantity'],
                f"{total:.1f}",
                f"{overage:.1f}",
                f"{total_with_overage:.1f}",
                hundreds,
                twenty_fives,
                f"{remainder:.1f}",
                couplers
            ])
            
            grand_total += total
            grand_total_with_overage += total_with_overage
        
        # Grand totals
        writer.writerow([])
        writer.writerow([
            'GRAND TOTAL',
            sum(t['quantity'] for t in cable_totals.values()),
            f"{grand_total:.1f}",
            f"{grand_total * 0.2:.1f}",
            f"{grand_total_with_overage:.1f}",
            '', '', '', ''
        ])
        
        # Fan Out Summary
        if fan_out_totals:
            writer.writerow([])
            writer.writerow(['FAN OUT SUMMARY'])
            writer.writerow(['Type', 'Quantity'])
            for fan_out_type, quantity in fan_out_totals.items():
                writer.writerow([fan_out_type, quantity])
        
        return response
    
    export_cable_schedule.short_description = "Export Cable Schedule to CSV"
    
    def generate_pull_sheet(self, request, queryset):
        """Generate cable pull sheet grouped by zone"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="cable_pull_sheet.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['L\'ACOUSTICS PA CABLE PULL SHEET'])
        writer.writerow([f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        
        # Group by zone
        from itertools import groupby
        
        sorted_cables = sorted(queryset, key=lambda x: (x.label.sort_order if x.label else 999, x.label.name if x.label else ''))
        
        for label, cables in groupby(sorted_cables, key=lambda x: x.label):
            if label:
                cables_list = list(cables)
                
                writer.writerow([f'ZONE: {label.name} - {label.description}'])
                writer.writerow(['Destination', 'Cable Type', 'Count', 'Fan Out', 'Count2', 'Notes'])
                
                zone_total = 0
                for cable in cables_list:
                    writer.writerow([
                        cable.destination,
                        cable.get_cable_display(),
                        cable.count,
                        cable.get_fan_out_display() if cable.fan_out else '',
                        cable.count2 if cable.count2 else '',
                        cable.notes or ''
                    ])
                    zone_total += cable.total_cable_length
                
                writer.writerow(['', '', f'Zone Total: {zone_total:.1f} ft', '', '', ''])
                writer.writerow([])
        
        return response
    
    generate_pull_sheet.short_description = "Generate Cable Pull Sheet"
    
    class Media:
        css = {
            'all': ('planner/css/pa_cable_admin.css',)
        }
        js = ('planner/js/pa_cable_calculations.js',)

