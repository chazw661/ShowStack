# Make sure these imports are at the top of your admin.py file

# At the TOP of admin.py, organize all imports together (lines 1-25):

# Django imports
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

#-----------PDF Creation Start------
#-----------End PDF Creation


# Then DELETE these duplicate imports around line 466-470:
# DELETE THESE LINES:
# from django import forms
# from django.http import HttpResponseRedirect, JsonResponse  
# from .models import P1Processor, P1Input, P1Output, DeviceOutput
# from .forms import P1InputInlineForm, P1OutputInlineForm, P1ProcessorAdminForm

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

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import Device, DeviceInput, DeviceOutput
from .forms  import DeviceInputInlineForm, DeviceOutputInlineForm
from .forms import DeviceForm, NameOnlyForm

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
    fields = ['output_number', 'signal_name', 'console_output']
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
                return format_html('<span style="color: #999;">Galaxy configuration coming soon</span>')
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
            return HttpResponseRedirect(
                reverse('admin:planner_p1processor_change', args=[p1.pk])
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


