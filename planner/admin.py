# Make sure these imports are at the top of your admin.py file

from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone


# Your existing model imports
from .models import Device, DeviceInput, DeviceOutput
from .models import Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput
from .models import Location, Amp, AmpChannel

# Your existing form imports
from planner.forms import ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm
from .forms import DeviceInputInlineForm, DeviceOutputInlineForm
from .forms import DeviceForm, NameOnlyForm

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
    form     = DeviceInputInlineForm
    extra = 0  
    template = "admin/planner/device_input_grid.html"


    def get_formset(self, request, obj=None, **kwargs):
        print("👉 DeviceInputInline.get_formset() called with obj=", obj) 
        # show exactly obj.input_count extra blank rows
        kwargs['extra'] = obj.input_count if obj else 0
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
    form     = DeviceOutputInlineForm
    extra = 0
    template = "admin/planner/device_output_grid.html"


    def get_formset(self, request, obj=None, **kwargs):
        kwargs['extra'] = obj.output_count if obj else 0
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

class AmpChannelInline(admin.TabularInline):
    model = AmpChannel
    extra = 0
    fields = ['channel_number', 'channel_name', 'avb_stream', 'analogue_input', 'aes_input', 'nl4_output', 'cacom_output', 'is_active', 'notes']
    ordering = ['channel_number']
    
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


# Replace your existing AmpAdmin class with this updated version

@admin.register(Amp)
class AmpAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'ip_address', 'manufacturer', 'model_number', 'channel_count', 'preset_name']
    list_filter = ['location', 'manufacturer', 'channel_count', 'cacom_output', 'created_at']
    search_fields = ['name', 'ip_address', 'model_number', 'manufacturer', 'preset_name']
    list_select_related = ['location']
    inlines = [AmpChannelInline]
    
    # Add the PDF export action
    
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('location', 'name', 'ip_address')
        }),
        ('Hardware Configuration', {
            'fields': ('manufacturer', 'model_number', 'channel_count'),
        }),
        ('Input Configuration', {
            'fields': ('avb_stream_input', 'analogue_input_count', 'aes_input_count'),
            'classes': ['collapse']
        }),
        ('Output Configuration', {
            'fields': ('nl4_outputs', 'cacom_output'),
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


@admin.register(AmpChannel)
class AmpChannelAdmin(admin.ModelAdmin):
    list_display = ['amp', 'channel_number', 'channel_name', 'avb_stream', 'analogue_input', 'is_active']
    list_filter = ['amp__location', 'amp', 'is_active', 'channel_name']
    search_fields = ['amp__name', 'channel_name', 'avb_stream', 'analogue_input']
    list_select_related = ['amp', 'amp__location']
    
    fieldsets = (
        ('Channel Information', {
            'fields': ('amp', 'channel_number', 'channel_name', 'is_active')
        }),
        ('Input Routing', {
            'fields': ('avb_stream', 'analogue_input', 'aes_input'),
        }),
        ('Output Routing', {
            'fields': ('nl4_output', 'cacom_output'),
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ['collapse']
        }),
    )
    
    def get_queryset(self, request):
        """Sort channels by amp and channel number"""
        qs = super().get_queryset(request)
        return qs.order_by('amp__location', 'amp__name', 'channel_number')