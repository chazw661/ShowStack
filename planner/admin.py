

# At the TOP of admin.py, organize all imports together (lines 1-25):

# Django imports
from django.contrib.contenttypes.models import ContentType
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse, path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe  
from django.shortcuts import render, redirect  
from django.contrib.admin.views.decorators import staff_member_required  
from django.views.decorators.http import require_POST  
from django import forms
from django.db.models import Count, Q, Max
from .models import AmplifierProfile, PowerDistributionPlan, AmplifierAssignment
from django.db.models import Sum 
from .models import SoundvisionPrediction, SpeakerArray, SpeakerCabinet
from django.contrib.admin import AdminSite
from django.contrib import messages 
from . import admin_ordering
from .models import ConsoleStereoOutput

# Python standard library imports
import csv
import math
import json  
from datetime import datetime, timedelta  

# Model imports (add the mic tracking models to your existing model imports)
from .models import Device, DeviceInput, DeviceOutput
from .models import Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput
from .models import Location, Amp, AmpChannel
from .models import SystemProcessor, P1Processor, P1Input, P1Output
from .models import GalaxyProcessor, GalaxyInput, GalaxyOutput
from .models import ShowDay, MicSession, MicAssignment, MicShowInfo 

# Form imports
from planner.forms import ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm
from .forms import DeviceInputInlineForm, DeviceOutputInlineForm
from .forms import DeviceForm, NameOnlyForm
from .forms import P1InputInlineForm, P1OutputInlineForm, P1ProcessorAdminForm
from .forms import GalaxyInputInlineForm, GalaxyOutputInlineForm, GalaxyProcessorAdminForm
from .models import AudioChecklist
from .forms import ConsoleStereoOutputForm




#-----Console Page----


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

        original_str = self.model.__str__
        self.model.__str__ = lambda self: ""            

                
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

        original_str = self.model.__str__
        self.model.__str__ = lambda self: "" 
                    


        return PrepopulatedFormSet
    
class ConsoleStereoOutputInline(admin.TabularInline):
    model = ConsoleStereoOutput
    form = ConsoleStereoOutputForm
    extra = 3  # Changed from 4 to 3
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

                # Pre-populate stereo types if new
                stereo_types = ['L', 'R', 'M']  # Changed from AL, AR, BL, BR
                for index, form in enumerate(self.forms):
                    if not form.instance.pk and index < len(stereo_types):
                        form.initial['stereo_type'] = stereo_types[index]

        original_str = self.model.__str__
        self.model.__str__ = lambda self: ""
        
        return PrepopulatedFormSet   




@admin.register(Console)
class ConsoleAdmin(admin.ModelAdmin):
    list_display = ['name_with_template_badge', 'is_template', 'export_yamaha_button']
    list_filter = ['is_template']
    
    fieldsets = (
        ('Console Information', {
            'fields': ('name', 'is_template')
        }),
    )
    
    inlines = [
        ConsoleInputInline,
        ConsoleAuxOutputInline,
        ConsoleMatrixOutputInline,
        ConsoleStereoOutputInline,
    ]
    
    actions = ['export_yamaha_rivage_csvs', 'duplicate_console']
    
    def name_with_template_badge(self, obj):
        if obj.is_template:
            return format_html('<strong>📋 {}</strong>', obj.name)
        return obj.name
    name_with_template_badge.short_description = 'Name'
    name_with_template_badge.admin_order_field = 'name'
    
    @admin.action(description='Duplicate selected console (with all inputs/outputs)')
    def duplicate_console(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one console to duplicate.", level='ERROR')
            return
        
        original = queryset.first()
        
        # Create new console
        new_console = Console.objects.create(
            name=f"{original.name} (Copy)",
            is_template=False
        )
        
        # Duplicate all related inputs
        for input_obj in original.consoleinput_set.all():
            ConsoleInput.objects.create(
                console=new_console,
                dante_number=input_obj.dante_number,
                input_ch=input_obj.input_ch,
                source=input_obj.source,
                group=input_obj.group,
                dca=input_obj.dca,
                mute=input_obj.mute,
                direct_out=input_obj.direct_out,
                omni_in=input_obj.omni_in,
                omni_out=input_obj.omni_out
            )
        
        # Duplicate aux outputs
        for aux in original.consoleauxoutput_set.all():
            ConsoleAuxOutput.objects.create(
                console=new_console,
                dante_number=aux.dante_number,
                aux_number=aux.aux_number,
                name=aux.name,
                mono_stereo=aux.mono_stereo,
                bus_type=aux.bus_type,
                omni_out=aux.omni_out
            )
        
        # Duplicate matrix outputs
        for matrix in original.consolematrixoutput_set.all():
            ConsoleMatrixOutput.objects.create(
                console=new_console,
                dante_number=matrix.dante_number,
                matrix_number=matrix.matrix_number,
                name=matrix.name,
                mono_stereo=matrix.mono_stereo,
                destination=matrix.destination,
                omni_out=matrix.omni_out
            )
        
        # Duplicate stereo outputs
        for stereo in original.consolestereooutput_set.all():
            ConsoleStereoOutput.objects.create(
                console=new_console,
                stereo_type=stereo.stereo_type,
                name=stereo.name,
                dante_number=stereo.dante_number,
                omni_out=stereo.omni_out
            )
        
        self.message_user(request, f"Successfully duplicated '{original.name}' as '{new_console.name}'")
        return redirect(f'/admin/planner/console/{new_console.id}/change/')
    
    def export_yamaha_button(self, obj):
        """Add export button in list view"""
        if obj.pk:
            url = f'/admin/planner/console/{obj.pk}/export-yamaha/'
            return format_html(
                '<a class="button" href="{}" style="padding: 5px 10px; background: #417690; color: white; border-radius: 4px; text-decoration: none;">Export</a>',
                url
            )
        return '-'
    export_yamaha_button.short_description = 'Export'
    export_yamaha_button.allow_tags = True
    
    def export_yamaha_rivage_csvs(self, request, queryset):
        """Admin action to export Yamaha CSVs for selected consoles"""
        if queryset.count() != 1:
            from .utils.yamaha_export import export_yamaha_csvs
            console = queryset.first()
            return export_yamaha_csvs(console)
        else:
            self.message_user(request, "Please select exactly one console to export.", level='warning')
    export_yamaha_rivage_csvs.short_description = "Export Yamaha Rivage CSVs"
    
    def get_urls(self):
        """Add custom URL for export"""
        urls = super().get_urls()
        from django.urls import path
        custom_urls = [
            path('<int:pk>/export-yamaha/',
                 self.admin_site.admin_view(self.export_yamaha_view),
                 name='console-export-yamaha'),
        ]
        return custom_urls + urls
    
    def export_yamaha_view(self, request, pk):
        """View to handle Yamaha CSV export"""
        from .utils.yamaha_export import export_yamaha_csvs
        console = Console.objects.get(pk=pk)
        return export_yamaha_csvs(console)
    
    class Media:
        js = ['planner/js/mono_stereo_handler.js',
              'planner/js/global_nav.js',]
        css = {
            'all': ['css/custom_admin.css', 'planner/css/console_admin.css']
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

from .models import AmpModel, Amp, AmpChannel

@admin.register(AmpModel)
class AmpModelAdmin(admin.ModelAdmin):
    list_display = ('manufacturer', 'model_name', 'channel_count', 
                   'nl4_connector_count', 'cacom_output_count')
    list_filter = ('manufacturer', 'channel_count', 'nl4_connector_count')
    search_fields = ('manufacturer', 'model_name')
    
    fieldsets = (
        ('Model Information', {
            'fields': ('manufacturer', 'model_name', 'channel_count')
        }),
        ('Input Configuration', {
            'fields': ('has_analog_inputs', 'has_aes_inputs', 'has_avb_inputs'),
            'classes': ('collapse',)
        }),
        ('Output Configuration', {
            'fields': ('nl4_connector_count', 'cacom_output_count'),
            'classes': ('collapse',)
        }),
    )


class AmpChannelInlineForm(forms.ModelForm):
    class Meta:
        model = AmpChannel
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.amp_id:
            amp = self.instance.amp
            # Show/hide input fields based on amp model capabilities
            if not amp.amp_model.has_avb_inputs:
                self.fields['avb_stream'].widget = forms.HiddenInput()
            if not amp.amp_model.has_aes_inputs:
                self.fields['aes_input'].widget = forms.HiddenInput()
            if not amp.amp_model.has_analog_inputs:
                self.fields['analog_input'].widget = forms.HiddenInput()


class AmpChannelInline(admin.TabularInline):
    model = AmpChannel
    form = AmpChannelInlineForm
    extra = 0
    fields = ['channel_number', 'channel_name', 'avb_stream', 'aes_input', 'analog_input']
    readonly_fields = ['channel_number']
    
    def has_add_permission(self, request, obj=None):
        return False  # Channels are auto-created
    
    def has_delete_permission(self, request, obj=None):
        return False  # Prevent accidental deletion


class AmpAdminForm(forms.ModelForm):
    class Meta:
        model = Amp
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'amp_model' in self.data:
            try:
                amp_model_id = int(self.data.get('amp_model'))
                amp_model = AmpModel.objects.get(id=amp_model_id)
                
                # Hide NL4 fields if amp doesn't have NL4 connectors
                if amp_model.nl4_connector_count == 0:
                    for field in ['nl4_a_pair_1', 'nl4_a_pair_2', 'nl4_b_pair_1', 'nl4_b_pair_2']:
                        self.fields[field].widget = forms.HiddenInput()
                elif amp_model.nl4_connector_count == 1:
                    for field in ['nl4_b_pair_1', 'nl4_b_pair_2']:
                        self.fields[field].widget = forms.HiddenInput()
                
                # Hide Cacom fields if amp doesn't have Cacom outputs
                if amp_model.cacom_output_count == 0:
                    for field in ['cacom_1_assignment', 'cacom_2_assignment', 
                                 'cacom_3_assignment', 'cacom_4_assignment']:
                        self.fields[field].widget = forms.HiddenInput()
                elif amp_model.cacom_output_count < 4:
                    for i in range(amp_model.cacom_output_count + 1, 5):
                        self.fields[f'cacom_{i}_assignment'].widget = forms.HiddenInput()
                        
            except (ValueError, AmpModel.DoesNotExist):
                pass


@admin.register(Amp)
class AmpAdmin(admin.ModelAdmin):
    form = AmpAdminForm
    list_display = ('name', 'location', 'amp_model', 'ip_address')
    list_filter = ('location', 'amp_model__manufacturer', 'amp_model__model_name')
    search_fields = ('name', 'ip_address')
    ordering = ['location', 'name']
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            ('Basic Information', {
                'fields': ('location', 'amp_model', 'name', 'ip_address')
            }),
        ]
        
        if obj and obj.amp_model.nl4_connector_count > 0:
            nl4_fields = []
            if obj.amp_model.nl4_connector_count >= 1:
                nl4_fields.append(('nl4_a_pair_1', 'nl4_a_pair_2'))
            if obj.amp_model.nl4_connector_count >= 2:
                nl4_fields.append(('nl4_b_pair_1', 'nl4_b_pair_2'))
            
            fieldsets.append(('NL4 Connectors', {
                'fields': nl4_fields,
                'classes': ('collapse',)
            }))
        
        if obj and obj.amp_model.cacom_output_count > 0:
            cacom_fields = []
            for i in range(1, min(obj.amp_model.cacom_output_count + 1, 5)):
                cacom_fields.append(f'cacom_{i}_assignment')
            
            fieldsets.append(('Cacom Outputs', {
                'fields': cacom_fields,
                'classes': ('collapse',)
            }))
        
        return fieldsets
    
    inlines = [AmpChannelInline]

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'amp_count', 'processor_count']
    search_fields = ['name', 'description']
    ordering = ['name']
    
    fieldsets = (
        ('Location Information', {
            'fields': ('name', 'description')
        }),
    )
    
    def amp_count(self, obj):
        """Show how many amps are in this location"""
        return obj.amps.count()
    amp_count.short_description = 'Amps'
    
    def processor_count(self, obj):
        """Show how many processors are in this location"""
        return obj.system_processors.count()
    processor_count.short_description = 'Processors'
                



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

from .models import PACableSchedule, PAZone, PAFanOut
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

class PAFanOutInline(admin.TabularInline):
        """Inline for managing multiple fan outs per cable run"""
        model = PAFanOut
        extra = 1
        fields = ['fan_out_type', 'quantity']
        
        def get_formset(self, request, obj=None, **kwargs):
            formset = super().get_formset(request, obj, **kwargs)
            formset.form.base_fields['fan_out_type'].widget.attrs.update({
                'style': 'width: 150px;'
            })
            formset.form.base_fields['quantity'].widget.attrs.update({
                'style': 'width: 80px;',
                'class': 'fan-out-quantity'
            })
            return formset




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

    # Hide from sidebar but still accessible via direct URL
    def has_module_permission(self, request):
        return False
    
    def create_default_zones(self, request, queryset):
        """Create standard L'Acoustics zones"""
        PAZone.create_default_zones()
        self.message_user(request, "Default zones have been created.")
    create_default_zones.short_description = "Create default L'Acoustics zones"


# PA Cable Admin

class PAFanOutInline(admin.TabularInline):
    """Inline for managing multiple fan outs per cable run"""
    model = PAFanOut
    extra = 1
    fields = ['fan_out_type', 'quantity']
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields['fan_out_type'].widget.attrs.update({
            'style': 'width: 150px;'
        })
        formset.form.base_fields['quantity'].widget.attrs.update({
            'style': 'width: 80px;',
            'class': 'fan-out-quantity'
        })
        return formset

@admin.register(PACableSchedule)
class PACableAdmin(admin.ModelAdmin):
    """Admin for PA Cable Schedule"""
    form = PACableInlineForm
    inlines = [PAFanOutInline]  # Add this line
    list_display = [
    'label_display', 'destination', 'count', 'length',
    'cable_display', 'fan_out_summary_display',  # Changed from 'fan_out'
    'notes', 'drawing_ref'
]
    list_filter = ['label', 'cable']
    search_fields = ['destination', 'notes', 'drawing_ref']
    list_editable = ['count' ,'length']  
    
    change_list_template = 'admin/planner/pacableschedule/change_list.html'
    
    fieldsets = (
        ('Cable Configuration', {
            'fields': ('label', 'destination', 'count', 'length' , 'cable')
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
    
    def fan_out_summary_display(self, obj):
        """Display summary of all fan outs"""
        return obj.fan_out_summary or "-"
        fan_out_summary_display.short_description = 'Fan Outs'
    
    def changelist_view(self, request, extra_context=None):
        """Add cable and fan out summary to the list view"""
        response = super().changelist_view(request, extra_context=extra_context)
        
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
        
        # Calculate cable summaries
        from django.db.models import Sum
        cable_summary = {}
        
        for cable_type in PACableSchedule.CABLE_TYPE_CHOICES:
            cables = qs.filter(cable=cable_type[0])
            if cables.exists():
                total_length = sum(c.total_cable_length for c in cables)
                if total_length > 0:
                    # Calculate standard cable quantities needed
                    hundreds = int(total_length / 100)
                    remaining = total_length % 100
                    
                    # Round up remaining to next standard length
                    fifties = 0
                    twenty_fives = 0
                    tens = 0
                    fives = 0
                    
                    if remaining > 0:
                        if remaining > 50:
                            # Need 1×100' for anything over 50'
                            hundreds += 1
                        elif remaining > 25:
                            # Need 1×50' for 26-50'
                            fifties = 1
                        elif remaining > 10:
                            # Need 1×25' for 11-25'
                            twenty_fives = 1
                        elif remaining > 5:
                            # Need 1×10' for 6-10'
                            tens = 1
                        elif remaining > 0:
                            # Need 1×5' for 1-5'
                            fives = 1
                    
                    cable_summary[cable_type[1]] = {
                        'total_runs': cables.aggregate(Sum('count'))['count__sum'] or 0,
                        'total_length': total_length,
                        'hundreds': hundreds,
                        'fifties': fifties,
                        'twenty_fives': twenty_fives,
                        'tens': tens,
                        'fives': fives,
                        'couplers': hundreds - 1 if hundreds > 1 else 0,
                    }
        
        # Calculate fan out totals with 20% overage
        fan_out_summary = {}
        for cable in qs.prefetch_related('fan_outs'):
            for fan_out in cable.fan_outs.all():
                if fan_out.fan_out_type:
                    fan_out_name = fan_out.get_fan_out_type_display()
                    if fan_out_name not in fan_out_summary:
                        fan_out_summary[fan_out_name] = {
                            'total_quantity': 0,
                            'with_overage': 0
                        }
                    fan_out_summary[fan_out_name]['total_quantity'] += fan_out.quantity
        
        # Calculate 20% overage for each fan out type
        for fan_out_type in fan_out_summary:
            total = fan_out_summary[fan_out_type]['total_quantity']
            fan_out_summary[fan_out_type]['with_overage'] = math.ceil(total * 1.2)
        
        # Add to context
        response.context_data['cable_summary'] = cable_summary
        response.context_data['fan_out_summary'] = fan_out_summary
        response.context_data['grand_total'] = sum(s['total_length'] for s in cable_summary.values())
        
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
        for cable in queryset.prefetch_related('fan_outs').order_by('label__sort_order', 'cable'):
            # Build fan out summary string for this cable
            fan_out_display = ''
            if cable.fan_outs.exists():
                fan_out_items = []
                for fan_out in cable.fan_outs.all():
                    if fan_out.fan_out_type:
                        fan_out_items.append(f'{fan_out.get_fan_out_type_display()} x{fan_out.quantity}')
                fan_out_display = ', '.join(fan_out_items)
            
            writer.writerow([
                cable.label.name if cable.label else '',
                cable.destination,
                cable.count,
                cable.get_cable_display(),
                fan_out_display,  # Changed: now shows all fan outs
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
            
            # Track fan out totals (lines 1279-1284 should be replaced with:)
        for fan_out in cable.fan_outs.all():
            if fan_out.fan_out_type:
                fan_out_name = fan_out.get_fan_out_type_display()
                if fan_out_name not in fan_out_totals:
                    fan_out_totals[fan_out_name] = 0
                fan_out_totals[fan_out_name] += fan_out.quantity
            
        
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
        
       
        # Fan Out Summary with 20% Overage
        if fan_out_totals:
            writer.writerow([])
            writer.writerow(['FAN OUT SUMMARY'])
            writer.writerow(['Type', 'Total Quantity', '20% Overage', 'Total w/Overage'])
            for fan_out_type, quantity in fan_out_totals.items():
                with_overage = math.ceil(quantity * 1.2)
                writer.writerow([
                    fan_out_type, 
                    quantity,
                    f"{quantity} × 20%",
                    with_overage
                ])
        
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




                #--------COMM Page-------

# Add these to your planner/admin.py file


from django import forms
from django.db.models import Count, Q, Max
from .models import CommChannel, CommPosition, CommCrewName, CommBeltPack
from django.http import HttpResponseRedirect

# Comm Channel Admin
@admin.register(CommChannel)
class CommChannelAdmin(admin.ModelAdmin):
    list_display = ['channel_number', 'input_designation', 'name', 'abbreviation', 'channel_type', 'order']
    list_editable = ['order']
    ordering = ['order', 'channel_number']
    search_fields = ['name', 'abbreviation', 'channel_number']
    
    def get_model_perms(self, request):
        """Show in COMM section of admin"""
        return super().get_model_perms(request)


# Comm Position Admin

# Add this BEFORE the CommPositionAdmin class
@admin.action(description='Populate common positions')
def populate_common_positions(modeladmin, request, queryset):
    """Create common position options"""
    positions = [
        ('FOH Lights', 1),
        ('FOH Audio', 2),
        ('FOH Stage Manager', 3),
        ('FOH Producer', 4),
        ('Video Playback', 5),
        ('Video Director', 6),
        ('Video Switch', 7),
        ('Video Shading', 8),
        ('Video Record', 9),
        ('A2', 10),
        ('Graphics', 11),
        ('BSM', 12),
        ('LED', 13),
        ('Dimmer Beach', 14),
        ('TD', 15),
    ]
    
    for name, order in positions:
        CommPosition.objects.get_or_create(
            name=name,
            defaults={'order': order}
        )
    
    modeladmin.message_user(request, "Common positions populated successfully.")


@admin.register(CommPosition)
class CommPositionAdmin(admin.ModelAdmin):
    list_display = ['name', 'order']
    list_editable = ['order']
    ordering = ['order', 'name']
    search_fields = ['name']
    actions = [populate_common_positions]  # Make sure this is defined
    
    def changelist_view(self, request, extra_context=None):
        # Force show actions even when queryset is empty
        if 'action' in request.POST:
            # Process the action even if no items selected
            action = self.get_actions(request)[request.POST['action']][0]
            action(self, request, self.get_queryset(request).none())
            return HttpResponseRedirect(request.get_full_path())
        
        # Always show the action form
        extra_context = extra_context or {}
        extra_context['has_filters'] = True  # Forces action dropdown to show
        
        return super().changelist_view(request, extra_context)
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        # Ensure our populate action is always available
        if 'populate_common_positions' not in actions:
            actions['populate_common_positions'] = (
                populate_common_positions,
                'populate_common_positions',
                'Populate common positions'
            )
        return actions


# Comm Crew Name Admin
@admin.register(CommCrewName)
class CommCrewNameAdmin(admin.ModelAdmin):
    list_display = ['name']
    ordering = ['name']
    search_fields = ['name']
    
    def get_model_perms(self, request):
        """Show in COMM section of admin"""
        return super().get_model_perms(request)


# Custom form for CommBeltPack with dynamic dropdowns

class CommBeltPackForm(forms.ModelForm):
    # Custom widgets for position and name that combine dropdown + text input
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
        widgets = {
            'position': forms.TextInput(attrs={'class': 'position-input'}),
            'name': forms.TextInput(attrs={'class': 'name-input'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'cols': 40}),
            'unit_location': forms.TextInput(attrs={'class': 'unit-location', 'placeholder': 'e.g., Unit #1 - FOH Rack'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial values for select fields if instance exists
        if self.instance and self.instance.pk:
            # Try to match position with existing CommPosition
            try:
                pos = CommPosition.objects.get(name=self.instance.position)
                self.fields['position_select'].initial = pos
            except CommPosition.DoesNotExist:
                pass
            
            # Try to match name with existing CommCrewName
            try:
                crew = CommCrewName.objects.get(name=self.instance.name)
                self.fields['name_select'].initial = crew
            except CommCrewName.DoesNotExist:
                pass



class CreateBeltPacksForm(forms.Form):
    """Form to ask how many belt packs to create"""
    count = forms.IntegerField(
        min_value=1, 
        max_value=100,
        initial=20,
        label="Number of belt packs to create"
    )
    starting_number = forms.IntegerField(
        min_value=1,
        initial=1,
        label="Starting BP number"
    )
    unit_location = forms.CharField(
        max_length=100,
        required=False,
        initial="Unit #1",
        label="Unit Location (for wireless only)",
        widget=forms.TextInput(attrs={'placeholder': 'e.g., Unit #1 - FOH Rack'})
    )

# Simpler action functions with different quantities
def create_5_wireless_beltpacks(modeladmin, request, queryset):
    """Create 5 wireless belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='WIRELESS').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 6):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            unit_location='Unit #1'
        )
    
    modeladmin.message_user(request, f"Created 5 wireless belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_5_wireless_beltpacks.short_description = 'Create 5 Wireless belt packs'

def create_10_wireless_beltpacks(modeladmin, request, queryset):
    """Create 10 wireless belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='WIRELESS').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 11):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            unit_location='Unit #1'
        )
    
    modeladmin.message_user(request, f"Created 10 wireless belt packs (BP #{max_bp+1} to #{max_bp+10})")
create_10_wireless_beltpacks.short_description = 'Create 10 Wireless belt packs'

def create_20_wireless_beltpacks(modeladmin, request, queryset):
    """Create 20 wireless belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='WIRELESS').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 21):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            unit_location='Unit #1'
        )
    
    modeladmin.message_user(request, f"Created 20 wireless belt packs (BP #{max_bp+1} to #{max_bp+20})")
create_20_wireless_beltpacks.short_description = 'Create 20 Wireless belt packs'

def create_50_wireless_beltpacks(modeladmin, request, queryset):
    """Create 50 wireless belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='WIRELESS').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 51):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            unit_location='Unit #1'
        )
    
    modeladmin.message_user(request, f"Created 50 wireless belt packs (BP #{max_bp+1} to #{max_bp+50})")
create_50_wireless_beltpacks.short_description = 'Create 50 Wireless belt packs'

# Hardwired versions
def create_5_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 5 hardwired belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='HARDWIRED').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 6):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i
        )
    
    modeladmin.message_user(request, f"Created 5 hardwired belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_5_hardwired_beltpacks.short_description = 'Create 5 Hardwired belt packs'

def create_10_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 10 hardwired belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='HARDWIRED').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 11):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i
        )
    
    modeladmin.message_user(request, f"Created 10 hardwired belt packs (BP #{max_bp+1} to #{max_bp+10})")
create_10_hardwired_beltpacks.short_description = 'Create 10 Hardwired belt packs'

def create_20_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 20 hardwired belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='HARDWIRED').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 21):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i
        )
    
    modeladmin.message_user(request, f"Created 20 hardwired belt packs (BP #{max_bp+1} to #{max_bp+20})")
create_20_hardwired_beltpacks.short_description = 'Create 20 Hardwired belt packs'

def create_50_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 50 hardwired belt packs"""
    max_bp = CommBeltPack.objects.filter(system_type='HARDWIRED').aggregate(
        Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 51):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i
        )
    
    modeladmin.message_user(request, f"Created 50 hardwired belt packs (BP #{max_bp+1} to #{max_bp+50})")
create_50_hardwired_beltpacks.short_description = 'Create 50 Hardwired belt packs'

def clear_all_beltpacks(modeladmin, request, queryset):
    """Delete ALL belt packs - use with caution"""
    count = CommBeltPack.objects.all().count()
    if count > 0:
        CommBeltPack.objects.all().delete()
        modeladmin.message_user(request, f"Deleted {count} belt packs", level=messages.WARNING)
    else:
        modeladmin.message_user(request, "No belt packs to delete")
clear_all_beltpacks.short_description = '⚠️ DELETE all belt packs'





from .models import CommBeltPack

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

        if self.instance and self.instance.pk:
            if self.instance.position:
                try:
                    pos = CommPosition.objects.get(name=self.instance.position)
                    self.fields['position_select'].initial = pos
                except CommPosition.DoesNotExist:
                    pass
            
            if self.instance.name:
                try:
                    crew = CommCrewName.objects.get(name=self.instance.name)
                    self.fields['name_select'].initial = crew
                except CommCrewName.DoesNotExist:
                    pass
        
        # Hide checked_out field for Hardwired beltpacks
        if self.instance and self.instance.system_type == 'HARDWIRED':
            if 'checked_out' in self.fields:
                self.fields['checked_out'].widget = forms.HiddenInput()
                self.fields['checked_out'].required = False
        
        # For new objects, add JavaScript to handle dynamic hiding
        if not self.instance.pk:
            if 'checked_out' in self.fields:
                self.fields['checked_out'].help_text = "Whether this belt pack has been checked out (Wireless only)"

    class Media:
        js = ('admin/js/comm_beltpack_admin.js',)
        css = {
            'all': ('admin/css/comm_admin.css',)
        }
        


@admin.register(CommBeltPack)
class CommBeltPackAdmin(admin.ModelAdmin):
    form = CommBeltPackAdminForm
    
    list_filter = ['system_type', 'checked_out', 'group', 'headset', 'audio_pgm']
    search_fields = ['bp_number', 'name', 'position', 'notes', 'unit_location']
    ordering = ['system_type', 'bp_number']
    
    # Actions for checking in/out and bulk creation
    actions = [
        'check_out_beltpacks',
        'check_in_beltpacks',
        create_5_wireless_beltpacks,
        create_10_wireless_beltpacks,
        create_20_wireless_beltpacks,
        create_50_wireless_beltpacks,
        create_5_hardwired_beltpacks,
        create_10_hardwired_beltpacks,
        create_20_hardwired_beltpacks,
        create_50_hardwired_beltpacks,
        clear_all_beltpacks
    ]
    
    def get_list_display(self, request):
        """Dynamically adjust list display based on filters"""
        base_display = ['display_bp_number', 'position', 'name', 'display_channels',
                       'headset', 'audio_pgm', 'group']
        
        # Check if we're filtering by system type
        system_type = request.GET.get('system_type__exact')
        
        # Only show checked_out column for wireless or when not filtering
        if system_type != 'HARDWIRED':
            base_display.append('display_checked_out')
        
        base_display.extend(['notes', 'updated_at'])
        return base_display
    
    def display_bp_number(self, obj):
        """Display BP number with system type prefix and icon"""
        if obj.system_type == "WIRELESS":
            icon = "📡"  # Antenna emoji
            prefix = "W"
        else:
            icon = "🔌"  # Plug emoji
            prefix = "H"
        return format_html("{} {}-{}", icon, prefix, obj.bp_number)
    display_bp_number.short_description = "BP #"
    display_bp_number.admin_order_field = 'bp_number'
    
    def display_checked_out(self, obj):
        """Display checked out status - only meaningful for wireless"""
        if obj.system_type == 'HARDWIRED':
            return format_html('<span style="color: #666;">—</span>')
        elif obj.checked_out:
            # When checked out = True, show green dot (it IS checked out to someone)
            return format_html('<span style="color: green; font-size: 1.2em;">●</span>')
        else:
            # When checked out = False, show red dot (it's available/not checked out)
            return format_html('<span style="color: red; font-size: 1.2em;">●</span>')
    display_checked_out.short_description = "Checked Out"
    display_checked_out.admin_order_field = 'checked_out'
    
    def display_channels(self, obj):
        """Display assigned channels compactly"""
        channels = []
        if obj.channel_a:
            channels.append(f"A:{obj.channel_a.abbreviation}")
        if obj.channel_b:
            channels.append(f"B:{obj.channel_b.abbreviation}")
        if obj.channel_c:
            channels.append(f"C:{obj.channel_c.abbreviation}")
        if obj.channel_d:
            channels.append(f"D:{obj.channel_d.abbreviation}")
        return " | ".join(channels) if channels else "-"
    display_channels.short_description = "Channels"
    
    def get_fieldsets(self, request, obj=None):
        """Dynamic fieldsets based on system type"""
        # Base fieldsets without checked_out
        base_fieldsets = [
            ('System Configuration', {
                'fields': ('system_type', 'bp_number')
            }),
            ('Assignment', {
                'fields': (('position_select', 'position'), ('name_select', 'name'), 'headset'),
            }),
            ('Channel Assignments', {
                'fields': (
                    ('channel_a', 'channel_b'),
                    ('channel_c', 'channel_d'),
                ),
            }),
        ]
        
        # Add Settings section with or without checked_out
        if obj and obj.system_type == 'HARDWIRED':
            # Hardwired: no checked_out field
            base_fieldsets.append(
                ('Settings', {
                    'fields': ('audio_pgm', 'group'),
                })
            )
        else:
            # Wireless or new objects: include checked_out
            base_fieldsets.append(
                ('Settings', {
                    'fields': ('audio_pgm', 'group', 'checked_out'),
                })
            )
        
        # Add Notes section
        base_fieldsets.append(
            ('Notes', {
                'fields': ('notes',),
                'classes': ('collapse',)
            })
        )
        
        return base_fieldsets
    
    @admin.action(description='Check out selected belt packs (Wireless only)')
    def check_out_beltpacks(self, request, queryset):
        """Mark selected belt packs as checked out (wireless only)"""
        wireless_packs = queryset.filter(system_type='WIRELESS')
        updated = wireless_packs.update(checked_out=True)
        
        hardwired_count = queryset.filter(system_type='HARDWIRED').count()
        
        if updated:
            self.message_user(
                request,
                f'{updated} wireless belt pack(s) checked out.',
                messages.SUCCESS
            )
        if hardwired_count > 0:
            self.message_user(
                request,
                f'{hardwired_count} hardwired belt pack(s) skipped (cannot be checked out).',
                messages.WARNING
            )
    
    @admin.action(description='Check in selected belt packs')
    def check_in_beltpacks(self, request, queryset):
        """Mark selected belt packs as checked in (wireless only)"""
        wireless_packs = queryset.filter(system_type='WIRELESS')
        updated = wireless_packs.update(checked_out=False)
        
        if updated:
            self.message_user(
                request,
                f'{updated} wireless belt pack(s) checked in.',
                messages.SUCCESS
            )
    
    def changelist_view(self, request, extra_context=None):
        """Add summary information grouped by system type"""
        extra_context = extra_context or {}
        
        # Get counts by system type
        wireless_total = CommBeltPack.objects.filter(system_type='WIRELESS').count()
        wireless_checked = CommBeltPack.objects.filter(system_type='WIRELESS', checked_out=True).count()
        hardwired_total = CommBeltPack.objects.filter(system_type='HARDWIRED').count()
        
        # Group counts by system
        wireless_groups = {}
        hardwired_groups = {}
        
        for choice_key, choice_name in CommBeltPack.GROUP_CHOICES:
            if choice_key:
                w_count = CommBeltPack.objects.filter(system_type='WIRELESS', group=choice_key).count()
                h_count = CommBeltPack.objects.filter(system_type='HARDWIRED', group=choice_key).count()
                
                if w_count > 0:
                    wireless_groups[choice_name] = w_count
                if h_count > 0:
                    hardwired_groups[choice_name] = h_count
        
        extra_context.update({
            'wireless_total': wireless_total,
            'wireless_checked': wireless_checked,
            'wireless_available': wireless_total - wireless_checked,
            'hardwired_total': hardwired_total,
            'hardwired_available': hardwired_total,  # Hardwired are always available
            'wireless_groups': wireless_groups,
            'hardwired_groups': hardwired_groups,
        })
        
        return super().changelist_view(request, extra_context)
    
    class Media:
        css = {
            'all': ('admin/css/comm_admin.css',)
        }
        js = ('admin/js/comm_beltpack_admin.js',)
    
    def changelist_view(self, request, extra_context=None):
        """Add summary information grouped by system type"""
        extra_context = extra_context or {}
        
        # Get counts by system type
        wireless_total = CommBeltPack.objects.filter(system_type='WIRELESS').count()
        wireless_checked = CommBeltPack.objects.filter(system_type='WIRELESS', checked_out=True).count()
        hardwired_total = CommBeltPack.objects.filter(system_type='HARDWIRED').count()
        hardwired_checked = CommBeltPack.objects.filter(system_type='HARDWIRED', checked_out=True).count()
        
        # Group counts by system
        wireless_groups = {}
        hardwired_groups = {}
        
        for choice_key, choice_name in CommBeltPack.GROUP_CHOICES:
            if choice_key:
                w_count = CommBeltPack.objects.filter(system_type='WIRELESS', group=choice_key).count()
                h_count = CommBeltPack.objects.filter(system_type='HARDWIRED', group=choice_key).count()
                
                if w_count > 0:
                    wireless_groups[choice_name] = w_count
                if h_count > 0:
                    hardwired_groups[choice_name] = h_count
        
        extra_context.update({
            'wireless_total': wireless_total,
            'wireless_checked': wireless_checked,
            'wireless_available': wireless_total - wireless_checked,
            'hardwired_total': hardwired_total,
            'hardwired_checked': hardwired_checked,
            'hardwired_available': hardwired_total - hardwired_checked,
            'wireless_groups': wireless_groups,
            'hardwired_groups': hardwired_groups,
        })
        
        return super().changelist_view(request, extra_context)
    


# Add a custom admin action to populate default channels
@admin.action(description='Populate default FS II channels')
def populate_default_channels(modeladmin, request, queryset):
    """Create the default 10 FS II channels"""
    default_channels = [
        ('1 4W', 'FS II - 1', 'Production', 'PROD', 1),
        ('2 4W', 'FS II - 2', 'Audio', 'AUDIO', 2),
        ('3 4W', 'FS II - 3', 'Video', 'VIDEO', 3),
        ('4 4W', 'FS II - 4', 'Lights', 'LIGHTS', 4),
        ('A 2W', 'FS II - 5', 'Camera', 'CAMS', 5),
        ('B 2W', 'FS II - 6', 'Graphics', 'GFX', 6),
        ('C 2W', 'FS II - 7', 'Stage Mgr', 'SM', 7),
        ('D 2W', 'FS II - 8', 'Carps', 'CARP', 8),
        ('', 'FS II - 9', 'ALL', 'ALL', 9),
        ('', 'FS II - 10', 'Program', 'PGM', 10),
    ]
    
    for input_des, channel_num, name, abbr, order in default_channels:
        CommChannel.objects.get_or_create(
            channel_number=channel_num,
            defaults={
                'input_designation': input_des,
                'name': name,
                'abbreviation': abbr,
                'order': order
            }
        )
    
    modeladmin.message_user(request, "Default FS II channels populated successfully.")


# Add action to the CommChannel admin
CommChannelAdmin.actions = [populate_default_channels]



#--------Mic Tracking Sheet-----



# Around line 2233 in admin.py - REPLACE ENTIRE MicAssignmentForm:

# REPLACE the entire MicAssignmentForm with this cleaner version:

class MicAssignmentForm(forms.ModelForm):
    """Form that accepts plain text for shared presenters"""
    
    class Meta:
        model = MicAssignment
        fields = '__all__'
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        }
    
    def __init__(self, *args, **kwargs):
        # Extract the instance BEFORE calling super
        instance = kwargs.get('instance')
        
        # If editing existing record with shared_presenters, convert to text
        if instance and instance.pk and instance.shared_presenters:
            if isinstance(instance.shared_presenters, list):
                # Check for clean data only
                if all(isinstance(x, str) and not x.startswith('[') for x in instance.shared_presenters):
                    # Temporarily replace the list with text for display
                    instance._original_shared = instance.shared_presenters
                    instance.shared_presenters = '\n'.join(instance.shared_presenters)
        
        super().__init__(*args, **kwargs)
        
        # Now customize the field
        self.fields['shared_presenters'] = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={
                'rows': 3,
                'cols': 40,
                'placeholder': 'Enter names separated by commas or new lines\nExample: Sue, Tom, Ben'
            }),
            help_text='Enter additional presenter names separated by commas or new lines',
            label='Shared presenters'
        )
        
        # Restore original if we modified it
        if instance and hasattr(instance, '_original_shared'):
            instance.shared_presenters = instance._original_shared
    
    def clean_shared_presenters(self):
        """Convert text input to list"""
        value = self.cleaned_data.get('shared_presenters', '').strip()
        
        if not value:
            return []
        
        # Simple split
        if '\n' in value:
            return [n.strip() for n in value.split('\n') if n.strip()]
        else:
            return [n.strip() for n in value.split(',') if n.strip()]
    
class MicAssignmentInline(admin.TabularInline):
    model = MicAssignment
    form = MicAssignmentForm
    extra = 0
    fields = ['rf_number', 'mic_type', 'presenter_name', 'is_micd', 'is_d_mic', 'shared_presenters', 'notes']
    ordering = ['rf_number']
    readonly_fields = ['rf_number']

@admin.register(ShowDay)
class ShowDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'name', 'session_count', 'total_mics', 'mics_used', 'view_day_link')
    list_filter = ('date',)
    search_fields = ('name',)
    ordering = ['date']
    
    def session_count(self, obj):
        return obj.sessions.count()
    session_count.short_description = "Sessions"
    
    def total_mics(self, obj):
        stats = obj.get_all_mics_status()
        return stats['total']
    total_mics.short_description = "Total Mics"
    
    def mics_used(self, obj):
        stats = obj.get_all_mics_status()
        return f"{stats['used']}/{stats['total']}"
    mics_used.short_description = "Mics Used"
    
    def view_day_link(self, obj):
        url = f'/mic-tracker/?day={obj.id}'
        return format_html('<a href="{}" class="button">View Day</a>', url)
    view_day_link.short_description = "View"

@admin.register(MicSession)
class MicSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'day', 'session_type', 'start_time', 'location', 'mic_usage', 'edit_mics_link')
    list_filter = ('day', 'session_type')
    search_fields = ('name', 'location')
    ordering = ['day__date', 'order', 'start_time']
    inlines = [MicAssignmentInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('day', 'name', 'session_type', 'location')
        }),
        ('Schedule', {
            'fields': ('start_time', 'end_time')
        }),
        ('Configuration', {
            'fields': ('num_mics', 'column_position', 'order')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    
    def mic_usage(self, obj):
        stats = obj.get_mic_usage_stats()
        return f"{stats['micd']}/{stats['total']}"
    mic_usage.short_description = "Mics Used"
    
    def edit_mics_link(self, obj):
        url = f'/mic-tracker/?session={obj.id}'
        return format_html('<a href="{}" class="button">Quick Edit</a>', url)
        edit_mics_link.short_description = "Quick Edit"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Update mic assignments if num_mics changed
        if 'num_mics' in form.changed_data:
            obj.create_mic_assignments()

@admin.register(MicAssignment)
class MicAssignmentAdmin(admin.ModelAdmin):
    form = MicAssignmentForm
    list_display = ('rf_display', 'session', 'mic_type', 'presenter_display', 'is_micd', 'is_d_mic', 'last_modified')
    list_filter = ('session__day', 'session', 'mic_type', 'is_micd', 'is_d_mic')
    search_fields = ('presenter_name', 'session__name', 'notes')
    list_editable = ('is_micd', 'is_d_mic')
    ordering = ['session__day__date', 'session__order', 'rf_number']
    
    fieldsets = (
        ('Assignment Details', {
            'fields': ('session', 'rf_number', 'mic_type')
        }),
        ('Presenter Information', {
            'fields': ('presenter_name', 'shared_presenters')
        }),
        ('Status', {
            'fields': ('is_micd', 'is_d_mic')
        }),
        ('Additional Info', {
            'fields': ('notes', 'modified_by'),
            'classes': ('collapse',)
        }),
    )
    
    def rf_display(self, obj):
        return f"RF{obj.rf_number:02d}"
    rf_display.short_description = "RF#"
    rf_display.admin_order_field = 'rf_number'
    
    def presenter_display(self, obj):
        return obj.display_presenters
    presenter_display.short_description = "Presenter(s)"
    
    def save_model(self, request, obj, form, change):
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(MicShowInfo)
class MicShowInfoAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Show Information', {
            'fields': ('show_name', 'venue_name', 'ballroom_name')
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date')
        }),
        ('Defaults', {
            'fields': ('default_mics_per_session', 'default_session_duration')
        }),
    )
    
    def has_add_permission(self, request):
        # Only allow one instance
        return not MicShowInfo.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False


# ===== ADD TO planner/urls.py (or create if doesn't exist) =====

from django.urls import path
from . import views

app_name = 'planner'

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('mic-tracker/', views.mic_tracker_view, name='mic_tracker'),
    path('api/mic/update/', views.update_mic_assignment, name='update_mic_assignment'),
    path('api/mic/bulk-update/', views.bulk_update_mics, name='bulk_update_mics'),
    path('api/session/duplicate/', views.duplicate_session, name='duplicate_session'),
    path('api/day/toggle/', views.toggle_day_collapse, name='toggle_day_collapse'),
    path('mic-tracker/export/', views.export_mic_tracker, name='export_mic_tracker'),
]


#--------Power Estimator---------

@admin.register(AmplifierProfile)
class AmplifierProfileAdmin(admin.ModelAdmin):
    list_display = [
        'manufacturer', 'model', 'channels', 'rated_power_watts', 
        'nominal_voltage', 'rack_units'
    ]
    list_filter = ['manufacturer', 'nominal_voltage', 'channels']
    search_fields = ['manufacturer', 'model', 'notes']
    ordering = ['manufacturer', 'model']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('manufacturer', 'model', 'channels', 'rack_units', 'weight_kg')
        }),
        ('Power Specifications', {
            'fields': (
                'idle_power_watts', 'rated_power_watts', 
                'peak_power_watts', 'max_power_watts'
            ),
            'description': 'Power values in watts. Rated power is 1/8 power (pink noise), typical for calculations.'
        }),
        ('Electrical Specifications', {
            'fields': ('nominal_voltage', 'power_factor', 'efficiency')
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


class AmplifierAssignmentInline(admin.TabularInline):
    model = AmplifierAssignment
    extra = 1
    fields = [
        'amplifier', 'quantity', 'zone', 'position', 
        'duty_cycle', 'phase_assignment', 
        'calculated_current_per_unit', 'calculated_total_current'
    ]
    readonly_fields = ['calculated_current_per_unit', 'calculated_total_current']
    autocomplete_fields = ['amplifier']


# Update your PowerDistributionPlanAdmin class in planner/admin.py

@admin.register(PowerDistributionPlan)
class PowerDistributionPlanAdmin(admin.ModelAdmin):
    list_display = [
        'show_day', 'venue_name', 'service_type', 
        'available_amperage_per_leg', 'get_total_current', 'created_at', 'view_calculator_button',
    ]
    list_filter = ['service_type', 'created_at']
    search_fields = ['venue_name', 'show_day__name', 'notes']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Show Information', {
            'fields': ('show_day', 'venue_name')
        }),
        ('Electrical Service', {
            'fields': ('service_type', 'available_amperage_per_leg')
        }),
        ('Safety Settings', {
            'fields': ('transient_headroom', 'safety_margin'),
            'description': 'Transient headroom accounts for audio peaks. Safety margin is the derating factor.'
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    # Remove get_summary_html from readonly_fields since it's not a real field
    readonly_fields = ['created_by', 'created_at', 'updated_at', 'get_total_current']
    
    inlines = [AmplifierAssignmentInline]
    

    
    def get_total_current(self, obj):
        """Calculate total current for list display"""
        if not obj.pk:
            return '-'
        total = obj.amplifier_assignments.aggregate(
            total=Sum('calculated_total_current')
        )['total'] or 0
        return f"{total:.1f}A"
    get_total_current.short_description = 'Total Current'
    
    def view_calculator_button(self, obj):
        """Add button to view calculator in list display"""
        if obj.pk:
            url = f"/audiopatch/power-distribution/{obj.pk}/"
            return format_html(
                '<a class="button" href="{}" style="background:#4a9eff; color:white; padding:5px 10px; text-decoration:none; border-radius:4px;">View Calculator</a>',
                url
            )
        return '-'
    view_calculator_button.short_description = 'Power Calculator'
    
    def get_calculator_link(self, obj):
        """Add large button to view calculator in change form"""
        if obj.pk:
            url = f"/audiopatch/power-distribution/{obj.pk}/"
            return format_html(
                '''
                <div style="padding: 20px; background: #2a2a2a; border-radius: 8px; text-align: center;">
                    <p style="color: #e0e0e0; margin-bottom: 15px;">
                        View phase distribution, load balancing, and detailed power analysis
                    </p>
                    <a href="{}" class="button" style="
                        display: inline-block;
                        background: #4a9eff;
                        color: white;
                        padding: 12px 30px;
                        text-decoration: none;
                        border-radius: 4px;
                        font-size: 16px;
                        font-weight: bold;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
                    " target="_blank">
                        📊 Open Power Distribution Calculator
                    </a>
                    <p style="color: #888; margin-top: 15px; font-size: 12px;">
                        Opens in new tab with visual phase bars and imbalance monitoring
                    </p>
                </div>
                ''',
                url
            )
        return 'Save the plan first to access the calculator'
    get_calculator_link.short_description = 'Visual Power Distribution Calculator'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        
    def get_total_current(self, obj):
        """Calculate total current for list display"""
        if not obj.pk:
            return '-'
        total = obj.amplifier_assignments.aggregate(
            total=Sum('calculated_total_current')
        )['total'] or 0
        return f"{total:.1f}A"
    get_total_current.short_description = 'Total Current'
    
    def view_calculator_button(self, obj):
        """Add button to view calculator in list display"""
        if obj.pk:
            url = f"/audiopatch/power-distribution/{obj.pk}/"
            return format_html(
                '<a class="button" href="{}" style="background:#4a9eff; color:white; padding:5px 10px; text-decoration:none; border-radius:4px;">View Calculator</a>',
                url
            )
        return '-'
    view_calculator_button.short_description = 'Power Calculator'
    
    def get_calculator_link(self, obj):
        """Add large button to view calculator in change form"""
        if obj.pk:
            url = f"/audiopatch/power-distribution/{obj.pk}/"
            return format_html(
                '''
                <div style="padding: 20px; background: #2a2a2a; border-radius: 8px; text-align: center;">
                    <p style="color: #e0e0e0; margin-bottom: 15px;">
                        View phase distribution, load balancing, and detailed power analysis
                    </p>
                    <a href="{}" class="button" style="
                        display: inline-block;
                        background: #4a9eff;
                        color: white;
                        padding: 12px 30px;
                        text-decoration: none;
                        border-radius: 4px;
                        font-size: 16px;
                        font-weight: bold;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
                    " target="_blank">
                        📊 Open Power Distribution Calculator
                    </a>
                    <p style="color: #888; margin-top: 15px; font-size: 12px;">
                        Opens in new tab with visual phase bars and imbalance monitoring
                    </p>
                </div>
                ''',
                url
            )
        return 'Save the plan first to access the calculator'
    get_calculator_link.short_description = 'Visual Power Distribution Calculator'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    
    
    def get_summary_html(self, obj):
        """Generate HTML summary of power distribution"""
        if not obj.pk:
            return "Save the plan first to see summary"
        
        # [Keep all the existing get_summary_html code here - the same as before]
        # Get all assignments
        assignments = obj.amplifier_assignments.all()
        
        # Calculate totals by phase
        phase_totals = {
            'L1': 0,
            'L2': 0,
            'L3': 0,
            'AUTO': 0
        }
        
        total_amps = 0
        total_current = 0
        total_power = 0
        
        for assignment in assignments:
            phase = assignment.phase_assignment
            current = float(assignment.calculated_total_current or 0)
            phase_totals[phase] += current
            total_amps += assignment.quantity
            total_current += current
            
            # Calculate power
            power_details = assignment.get_power_details()
            total_power += power_details['total']['peak_watts']
        
        # Auto-balance AUTO assignments
        auto_current = phase_totals['AUTO']
        if auto_current > 0:
            # Distribute AUTO current evenly
            per_phase = auto_current / 3
            phase_totals['L1'] += per_phase
            phase_totals['L2'] += per_phase
            phase_totals['L3'] += per_phase
        
        # Calculate imbalance
        max_phase = max(phase_totals['L1'], phase_totals['L2'], phase_totals['L3'])
        min_phase = min(phase_totals['L1'], phase_totals['L2'], phase_totals['L3'])
        if max_phase > 0:
            imbalance = ((max_phase - min_phase) / max_phase) * 100
        else:
            imbalance = 0
        
        # Calculate percentages
        usable = obj.get_usable_amperage()
        
        # Calculate total of all phases
        phase_total_sum = phase_totals['L1'] + phase_totals['L2'] + phase_totals['L3']
        
        # Return the HTML
        return f"""
        <div style="background: #2a2a2a; padding: 15px; border-radius: 8px; color: #e0e0e0;">
            <h3 style="margin-top: 0; color: #4a9eff;">System Totals</h3>
            
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px;">
                <div style="background: #1a1a1a; padding: 10px; border-radius: 4px;">
                    <strong>Total Amplifiers:</strong><br>
                    <span style="font-size: 24px; color: #4a9eff;">{total_amps}</span>
                </div>
                <div style="background: #1a1a1a; padding: 10px; border-radius: 4px;">
                    <strong>Total Current:</strong><br>
                    <span style="font-size: 24px; color: #4a9eff;">{total_current:.1f}A</span>
                </div>
                <div style="background: #1a1a1a; padding: 10px; border-radius: 4px;">
                    <strong>Peak Power:</strong><br>
                    <span style="font-size: 24px; color: #4a9eff;">{total_power/1000:.1f}kW</span>
                </div>
            </div>
            
            <h4 style="color: #4a9eff;">Phase Distribution</h4>
            <table style="width: 100%; color: #e0e0e0; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid #444;">
                    <th style="text-align: left; padding: 8px;">Phase</th>
                    <th style="text-align: left; padding: 8px;">Current</th>
                    <th style="text-align: left; padding: 8px;">% of {usable}A</th>
                    <th style="text-align: left; padding: 8px;">Status</th>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>L1</strong></td>
                    <td style="padding: 8px;">{phase_totals['L1']:.1f}A</td>
                    <td style="padding: 8px;">{(phase_totals['L1']/usable*100):.1f}%</td>
                    <td style="padding: 8px;">{'✓ Good' if phase_totals['L1']/usable*100 < 50 else '⚠️ Moderate' if phase_totals['L1']/usable*100 < 80 else '❌ High'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>L2</strong></td>
                    <td style="padding: 8px;">{phase_totals['L2']:.1f}A</td>
                    <td style="padding: 8px;">{(phase_totals['L2']/usable*100):.1f}%</td>
                    <td style="padding: 8px;">{'✓ Good' if phase_totals['L2']/usable*100 < 50 else '⚠️ Moderate' if phase_totals['L2']/usable*100 < 80 else '❌ High'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>L3</strong></td>
                    <td style="padding: 8px;">{phase_totals['L3']:.1f}A</td>
                    <td style="padding: 8px;">{(phase_totals['L3']/usable*100):.1f}%</td>
                    <td style="padding: 8px;">{'✓ Good' if phase_totals['L3']/usable*100 < 50 else '⚠️ Moderate' if phase_totals['L3']/usable*100 < 80 else '❌ High'}</td>
                </tr>
                <tr style="border-top: 2px solid #4a9eff; font-weight: bold; background: #1a1a1a;">
                    <td style="padding: 8px;"><strong>TOTAL</strong></td>
                    <td style="padding: 8px; color: #4a9eff;"><strong>{phase_total_sum:.1f}A</strong></td>
                    <td style="padding: 8px;">-</td>
                    <td style="padding: 8px;">3-Phase Total</td>
                </tr>
            </table>
            
            <div style="margin-top: 15px; padding: 10px; background: #1a1a1a; border-radius: 4px;">
                <strong>Phase Imbalance:</strong> 
                <span style="color: {'#28a745' if imbalance < 10 else '#ffc107' if imbalance < 15 else '#dc3545'};">
                    {imbalance:.1f}%
                </span>
                {' ✓' if imbalance < 10 else ' ⚠️ Target <10%'}
            </div>
            
            <div style="margin-top: 15px; padding: 10px; background: #1a1a1a; border-radius: 4px;">
                <strong>Average Load per Phase:</strong> {(phase_total_sum/3):.1f}A
                <span style="color: #888; margin-left: 10px;">
                    ({(phase_total_sum/3/usable*100):.1f}% of usable)
                </span>
            </div>
            
            <div style="margin-top: 10px; font-size: 12px; color: #888;">
                Available: {obj.available_amperage_per_leg}A per leg<br>
                Usable (with {int(obj.safety_margin*100)}% margin): {usable}A per leg<br>
                Transient Headroom: {int((obj.transient_headroom-1)*100)}%
            </div>
        </div>
        """
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AmplifierAssignment)
class AmplifierAssignmentAdmin(admin.ModelAdmin):
    list_display = [
        'distribution_plan', 'zone', 'amplifier', 'quantity', 
        'duty_cycle', 'phase_assignment', 'calculated_total_current'
    ]


@admin.register(AudioChecklist)
class AudioChecklistAdmin(admin.ModelAdmin):
    """Admin interface for Audio Checklist"""
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def changelist_view(self, request, extra_context=None):
        """Show our custom checklist instead of model list"""
        context = {
            'title': 'Audio Production Checklist',
            'cl': self,
            'opts': self.model._meta,
            'has_filters': False,
            'has_add_permission': False,
        }
        return render(request, 'admin/planner/audio_checklist.html', context)
    



    #--------Prediction Module-----


class SpeakerCabinetInline(admin.TabularInline):
    model = SpeakerCabinet
    extra = 0
    fields = ['position_number', 'speaker_model', 'angle_to_next', 'site_angle', 
              'panflex_setting', 'top_z', 'bottom_z']
    ordering = ['position_number']

class SpeakerArrayInline(admin.StackedInline):
    model = SpeakerArray
    extra = 0
    fields = (
        ('source_name', 'configuration', 'bumper_type'),
        ('position_x', 'position_y', 'position_z'),
        ('site_angle', 'azimuth'),
        ('num_motors', 'is_single_point', 'bumper_angle'),
        ('front_motor_load_lb', 'rear_motor_load_lb', 'total_weight_lb'),
        ('bottom_elevation', 'mbar_hole'),
    )
    readonly_fields = ['bumper_angle']

@admin.register(SoundvisionPrediction)
class SoundvisionPredictionAdmin(admin.ModelAdmin):
    list_display = ['show_day', 'file_name', 'version', 'date_generated', 'created_at', 'array_summary', 'view_detail_link']
    list_filter = ['show_day', 'created_at', 'date_generated']
    search_fields = ['file_name', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'parsed_data_display']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('show_day', 'file_name', 'version', 'date_generated')
        }),
        ('File Upload', {
            'fields': ('pdf_file',),
            'description': 'Upload L\'Acoustics Soundvision PDF report'
        }),
        ('Parsed Data', {
            'fields': ('parsed_data_display',),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    inlines = [SpeakerArrayInline]
    
    def array_summary(self, obj):
        return f"{obj.speaker_arrays.count()} arrays"
    array_summary.short_description = "Arrays"

    def view_detail_link(self, obj):
        url = reverse('planner:prediction_detail', kwargs={'pk': obj.pk})
        return format_html('<a class="button" style="padding: 3px 10px; background: #417690; color: white; border-radius: 4px; text-decoration: none;" href="{}">View Details</a>', url)
    view_detail_link.short_description = 'Actions'
    
    def parsed_data_display(self, obj):
        if obj.raw_data:
            return format_html('<pre style="background: #2a2a2a; padding: 10px; border-radius: 5px; color: #e0e0e0;">{}</pre>', 
                             json.dumps(obj.raw_data, indent=2))
        return "No data parsed yet"
    parsed_data_display.short_description = "Raw Parsed Data"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # If a PDF file was uploaded, parse it
        if obj.pdf_file and ('pdf_file' in form.changed_data or not change):
            try:
                from .soundvision_parser import import_soundvision_prediction
                import_soundvision_prediction(obj, obj.pdf_file)
                messages.success(request, f'Successfully parsed {obj.file_name}')
            except Exception as e:
                messages.error(request, f'Error parsing PDF: {str(e)}')




@admin.register(SpeakerArray)
class SpeakerArrayAdmin(admin.ModelAdmin):
    list_display = ['source_name', 'prediction', 'configuration', 'display_weight', 
                   'display_trim', 'display_rigging', 'cabinet_count']
    list_filter = ['configuration', 'bumper_type', 'num_motors']
    search_fields = ['source_name', 'array_base_name']
    readonly_fields = ['bumper_angle', 'total_motor_load', 'trim_height', 'cabinet_summary']
    
    inlines = [SpeakerCabinetInline]
    
    def display_weight(self, obj):
        if obj.total_weight_lb:
            return format_html('<strong>{:.0f} lb</strong>', obj.total_weight_lb)
        return "-"
    display_weight.short_description = "Weight"
    
    def display_trim(self, obj):
        return obj.trim_height_display
    display_trim.short_description = "Bottom Trim"
    
    def display_rigging(self, obj):
        return obj.rigging_display
    display_rigging.short_description = "Rigging"
    
    def cabinet_count(self, obj):
        return obj.cabinets.count()
    cabinet_count.short_description = "Cabinets"
    
    def cabinet_summary(self, obj):
        cabinets = obj.cabinets.all().order_by('position_number')
        if not cabinets:
            return "No cabinets configured"
        
        summary_lines = []
        for cab in cabinets:
            angle_str = f"→ {cab.angle_to_next}°" if cab.angle_to_next else ""
            panflex_str = f" [{cab.panflex_setting}]" if cab.panflex_setting else ""
            line = f"#{cab.position_number}: {cab.speaker_model}{angle_str}{panflex_str}"
            summary_lines.append(line)
        
        return format_html('<div style="font-family: monospace; white-space: pre-line; background: #2a2a2a; padding: 10px; border-radius: 5px;">{}</div>', 
                          '\n'.join(summary_lines))
    cabinet_summary.short_description = "Cabinet Configuration"

@admin.register(SpeakerCabinet)
class SpeakerCabinetAdmin(admin.ModelAdmin):
    list_display = ['position_number', 'speaker_model', 'array', 'angle_to_next', 
                   'site_angle', 'panflex_setting']
    list_filter = ['speaker_model', 'panflex_setting']
    search_fields = ['array__source_name', 'speaker_model']
    ordering = ['array', 'position_number']    




#-----Dark Theme-----

class DarkThemeAdminMixin:
    class Media:
        css = {
            'all': (
                'admin/css/custom.css',  # Your existing custom CSS
                'audiopatch/css/dark_theme.css',  # The new dark theme
            )
        }
        js = (
            'audiopatch/js/dark_theme.js',
        )




