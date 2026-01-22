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
from . import admin_ordering
from .models import ConsoleStereoOutput
from django.urls import path

# Python standard library imports
import csv
import math
import json  
from datetime import datetime, timedelta  

from planner.models import Project, ProjectMember
from django.db import models

# Model imports (add the mic tracking models to your existing model imports)
from .models import Device, DeviceInput, DeviceOutput
from .models import Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput
from .models import Location, Amp, AmpChannel
from .models import SystemProcessor, P1Processor, P1Input, P1Output
from .models import GalaxyProcessor, GalaxyInput, GalaxyOutput
from .models import ShowDay, MicSession, MicAssignment, MicShowInfo 
from .models import Presenter

# Form imports
from planner.forms import ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm
from .forms import DeviceInputInlineForm, DeviceOutputInlineForm
from .forms import DeviceForm, NameOnlyForm
from .forms import P1InputInlineForm, P1OutputInlineForm, P1ProcessorAdminForm
from .forms import GalaxyInputInlineForm, GalaxyOutputInlineForm, GalaxyProcessorAdminForm
from .models import AudioChecklist
from .forms import ConsoleStereoOutputForm
from .admin_site import showstack_admin_site

from django.contrib import admin, messages


from .models import CommBeltPack, CommBeltPackChannel






class BaseAdmin(admin.ModelAdmin):
    """Base admin class that provides dark theme CSS"""
    
    class Media:
        css = {
            'all': ('css/dark-admin.css',)
        }


class BaseEquipmentAdmin(BaseAdmin):
    """Base admin for equipment models with project filtering and role-based permissions"""


    def _get_user_role_for_project(self, request, project):
        """Get user's role for a specific project (returns 'owner', 'editor', 'viewer', or None)"""
        if project is None:
            return None
        if project.owner == request.user:
            
            try:
                from planner.models import ProjectMember
                member = ProjectMember.objects.get(user=request.user, project=project)
                return member.role  # 'editor' or 'viewer'
            except ProjectMember.DoesNotExist:
                
                return None
        



    def save_model(self, request, obj, form, change):
        """Auto-assign current project to new equipment"""
        if not change:  # Only for new objects
            if hasattr(request, 'current_project') and request.current_project:
                from planner.models import Project
                try:
                    # Handle both Project objects and IDs
                    if isinstance(request.current_project, Project):
                        obj.project = request.current_project
                    else:
                        obj.project = Project.objects.get(id=request.current_project)
                except Project.DoesNotExist:
                    pass
        super().save_model(request, obj, form, change)    
    
    def _is_premium_owner(self, request):
        """Check if user is paid/beta (premium accounts)"""
        if not hasattr(request.user, 'userprofile'):
            return False
        
        profile = request.user.userprofile
        # Paid and beta accounts are considered premium
        return profile.account_type in ['paid', 'beta', 'premium']
    
    def _user_has_editor_access(self, request):
        """Check if user has editor access to ANY project"""
        return ProjectMember.objects.filter(
            user=request.user,
            role='editor'
        ).exists()
    
    def get_exclude(self, request, obj=None):
        """Hide project field on add/edit forms - auto-assigned from current_project"""
        exclude = list(super().get_exclude(request, obj) or [])
        if hasattr(self.model, 'project'):
            exclude.append('project')
        return exclude
    
    def get_queryset(self, request):
        """Filter equipment to user's accessible projects"""
        qs = super().get_queryset(request)
        
        # DEBUG - remove after fixing
        if self.model.__name__ == 'CommChannel':
            print(f"DEBUG CommChannel get_queryset:")
            print(f"  has current_project: {hasattr(request, 'current_project')}")
            print(f"  current_project: {getattr(request, 'current_project', None)}")
            print(f"  qs count before filter: {qs.count()}")
        
        # Filter by CURRENTLY SELECTED project, not all accessible projects
        if not hasattr(request, 'current_project') or not request.current_project:
            return qs.none()  # No project selected = show nothing
        
        current_project_id = request.current_project.id
        
        # Map child models to their parent field path
        # Map child models to their parent field path
        child_model_paths = {
            'PAFanOut': 'cable_schedule__project_id',
            'MicSession': 'day__project_id',
            'MicAssignment': 'session__day__project_id',
            # 'Presenter': REMOVED - now has direct project FK ✓
            # 'MicShowInfo': REMOVED - now has direct project OneToOneField ✓
            'SpeakerArray': 'prediction__project_id',
            'SpeakerCabinet': 'array__prediction__project_id',
            'AmplifierAssignment': 'distribution_plan__project_id',
            'P1Processor': 'system_processor__project_id',
            'GalaxyProcessor': 'system_processor__project_id',
            'P1Input': 'p1_processor__system_processor__project_id',
            'P1Output': 'p1_processor__system_processor__project_id',
            'GalaxyInput': 'galaxy_processor__system_processor__project_id',
            'GalaxyOutput': 'galaxy_processor__system_processor__project_id',
        }
        
        # Get the model name
        model_name = self.model.__name__
        
        # If this is a child model, filter through parent
        if model_name in child_model_paths:
            filter_path = child_model_paths[model_name]
            filter_kwargs = {filter_path: current_project_id}
            return qs.filter(**filter_kwargs)
        
        # Otherwise, filter directly by project_id
        return qs.filter(project_id=current_project_id)
            
        
    def has_module_permission(self, request):
        """Show module if user has any accessible projects"""
        if not request.user.is_authenticated:
            return super().has_module_permission(request)
        
        if request.user.is_superuser:
            return True
        
        # Check if user has any accessible projects
        has_projects = Project.objects.filter(
            models.Q(owner=request.user) |
            models.Q(projectmember__user=request.user)
        ).exists()
        
        return has_projects
    
    def has_view_permission(self, request, obj=None):
        """Allow view if user has access to the project"""
        if request.user.is_superuser:
            return True
        
        if obj is None:
            return self.has_module_permission(request)
        
        # Check if user owns or is member of this project
        return (obj.project.owner == request.user or 
                ProjectMember.objects.filter(
                    user=request.user, 
                    project=obj.project
                ).exists())
    
    def has_add_permission(self, request):
        """Allow add if user is owner or editor (NOT viewer)"""
        if request.user.is_superuser:
            return True
        
        # Premium owners can add
        if self._is_premium_owner(request):
            return True
        
        # Editors can add (but NOT viewers)
        return self._user_has_editor_access(request)
    
    def has_change_permission(self, request, obj=None):
        """Allow change if user is owner or editor (NOT viewer)"""
        if request.user.is_superuser:
            return True
        
        if obj is None:
            # For changelist view - show if has any editor access
            return self._is_premium_owner(request) or self._user_has_editor_access(request)
        
        # Check specific object permission
       # Handle both Project and Equipment objects
        project = obj if obj.__class__.__name__ == 'Project' else obj.project
        role = self._get_user_role_for_project(request, project)
        return role in ['owner', 'editor']  # Viewers can't edit
    
    def has_delete_permission(self, request, obj=None):
        """Allow delete if user is owner or editor (NOT viewer)"""
        if request.user.is_superuser:
            return True
        
        if obj is None:
            return self._is_premium_owner(request) or self._user_has_editor_access(request)
        
        # Check specific object permission
        # Handle both Project and Equipment objects, including nested children
        if obj.__class__.__name__ == 'Project':
            project = obj
        elif hasattr(obj, 'project'):
            project = obj.project
        elif hasattr(obj, 'array'):  # SpeakerCabinet
            project = obj.array.prediction.project
        elif hasattr(obj, 'prediction'):  # SpeakerArray
            project = obj.prediction.project
        else:
            project = None
        role = self._get_user_role_for_project(request, project)
        return role in ['owner', 'editor']  # Viewers can't delete
    


#------Duplicate Project Admin

# Add this to your planner/admin.py file

class DuplicateProjectForm(forms.Form):
    """Form for renaming a project during duplication"""
    new_name = forms.CharField(
        max_length=200,
        label="New Project Name",
        widget=forms.TextInput(attrs={
            'class': 'vTextField',
            'style': 'width: 100%;',
            'autofocus': True
        })
    )
    
    def __init__(self, *args, original_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        if original_name:
            self.fields['new_name'].initial = f"Copy of {original_name}"


@admin.action(description="Duplicate selected project")
def duplicate_project_action(modeladmin, request, queryset):
    """
    Admin action to duplicate a project with all related data.
    Shows an intermediate page to rename the project.
    """
    
    # Only allow duplicating one project at a time
    if queryset.count() != 1:
        
        modeladmin.message_user(
            request,
            "Please select exactly one project to duplicate.",
            level=messages.ERROR
        )
        return
    
    project = queryset.first()
   
    
    # If this is a POST request, we're coming back from the form
    if request.POST.get('confirm_duplicate'):
       
        form = DuplicateProjectForm(request.POST, original_name=project.name)
        
        if form.is_valid():
           
            new_name = form.cleaned_data['new_name']
           
            try:
                user = request.user
                if not user.is_authenticated:
                    print("❌ User not authenticated")
                    modeladmin.message_user(
                        request,
                        'You must be logged in to duplicate projects.',
                        level=messages.ERROR
                    )
                    return
                
               
                
                # Duplicate the project
                new_project = project.duplicate(
                    new_name=new_name,
                    duplicate_for_user=user
                )
                
                print(f"✅ SUCCESS! New project created: {new_project.name}")
                
                # ... rest of success handling
                
                modeladmin.message_user(
                    request,
                    f'Successfully created "{new_project.name}" as a copy of "{project.name}".',
                    level=messages.SUCCESS
                )
                
                # Redirect to the new project's change page
                from django.urls import reverse
                url = reverse('admin:planner_project_change', args=[new_project.id])
                return redirect(url)
                
            except Exception as e:
                modeladmin.message_user(
                    request,
                    f'Error duplicating project: {str(e)}',
                    level=messages.ERROR
                )
                return
    else:
        form = DuplicateProjectForm(original_name=project.name)
    
   # Show the intermediate page
    context = {
        'form': form,
        'project': project,
        'projects': [project],  # Add this
        'queryset': queryset,    # Add this
        'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,  # Add this
        'opts': modeladmin.model._meta,
        'title': f'Duplicate Project: {project.name}',
        'site_title': modeladmin.admin_site.site_title,
        'site_header': modeladmin.admin_site.site_header,
    }
    
    return render(request, 'admin/planner/duplicate_project.html', context)
    
    return render(request, 'admin/planner/duplicate_project.html', context)

@admin.action(description="TEST - Just a test action")
def test_action(modeladmin, request, queryset):
    modeladmin.message_user(request, "Test action works!", level=messages.SUCCESS)



@admin.register(Project, site=showstack_admin_site)
class ProjectAdmin(admin.ModelAdmin):
    """Admin for Project model - doesn't use BaseEquipmentAdmin filtering"""
    list_display = ['name', 'owner', 'start_date', 'end_date', 'venue', 'is_archived']
    list_filter = ['is_archived', 'start_date', 'end_date']
    search_fields = ['name', 'venue', 'client']
    actions = [duplicate_project_action]
    readonly_fields = ['owner', 'created_at', 'updated_at']  # <-- owner is readonly
    exclude = []  # We'll set this dynamically
    
    def get_exclude(self, request, obj=None):
        """Hide owner field on add form"""
        if obj is None:  # Adding new project
            return ['owner']  # Hide owner field
        return []  # Show owner (readonly) on edit form
    
    fieldsets = (
        ('Project Details', {
            'fields': ('name', 'owner', 'start_date', 'end_date', 'venue', 'client')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_archived',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    class Media:
        css = {
            'all': ('admin/css/project_list_buttons.css',)
        }
    
    def get_queryset(self, request):
        """Show user's own projects and projects they're members of"""
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs
        
        # Show projects user owns or is a member of
        from planner.models import ProjectMember
        member_project_ids = ProjectMember.objects.filter(
            user=request.user
        ).values_list('project_id', flat=True)
        
        return qs.filter(
            Q(owner=request.user) | Q(id__in=member_project_ids)
        )
    
    def has_add_permission(self, request):
        """Paid/beta users can add projects"""
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'userprofile'):
            return request.user.userprofile.account_type in ['paid', 'beta', 'premium']
        return False
    
    def save_model(self, request, obj, form, change):
        """Set owner to current user if creating"""
        if not change:  # New project
            obj.owner = request.user
        super().save_model(request, obj, form, change)



class BaseEquipmentInline(admin.TabularInline):
    """Base inline class with viewer restrictions for equipment inlines"""
    
    def _user_is_viewer(self, request, obj):
        """Check if user is a viewer for this object's project"""
        if request.user.is_superuser:
            return False
        
        if obj is None:
            return False
        
        # Check if owner
        try:
            if obj.project.owner == request.user:
                return False
        except:
            return False
        
        # Check if viewer
        try:
            member = ProjectMember.objects.get(user=request.user, project=obj.project)
            return member.role == 'viewer'
        except ProjectMember.DoesNotExist:
            return True
    
    def has_add_permission(self, request, obj=None):
        """Viewers cannot add"""
        if request.user.is_superuser:
            return True
        
        if self._user_is_viewer(request, obj):
            return False
        
        return True
    
    def has_change_permission(self, request, obj=None):
        """Viewers cannot change"""
        if request.user.is_superuser:
            return True
            
        if self._user_is_viewer(request, obj):
            return False
        
        return True
    
    def has_delete_permission(self, request, obj=None):
        """Viewers cannot delete"""
        if request.user.is_superuser:
            return True
            
        if self._user_is_viewer(request, obj):
            return False
        
        return True
    
    def get_max_num(self, request, obj=None, **kwargs):
        """Prevent adding new rows for viewers"""
        if self._user_is_viewer(request, obj):
            return 0
        return super().get_max_num(request, obj, **kwargs)
    
    def get_formset(self, request, obj=None, **kwargs):
        """Make form fields disabled for viewers"""
        formset = super().get_formset(request, obj, **kwargs)
        
        if self._user_is_viewer(request, obj):
            # Make all fields disabled
            for field_name, field in formset.form.base_fields.items():
                field.disabled = True
        
        return formset

# ==================== SHOWSTACK BRANDING ====================
admin.site.site_header = "ShowStack Audio Administration"
admin.site.site_title = "ShowStack Audio"
admin.site.index_title = "ShowStack Audio Management"


#




#-----Console Page----


class ConsoleInputInline(admin.TabularInline):
    model = ConsoleInput
    form = ConsoleInputForm
    extra = 0
    can_delete = True
    classes = ['collapse']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        from django.db.models.functions import Cast
        from django.db.models import IntegerField
        return qs.annotate(
            input_ch_int=Cast('input_ch', IntegerField())
        ).order_by('input_ch_int')

    def get_extra(self, request, obj=None, **kwargs):
        """Return 144 for new consoles, 0 for existing"""
        if obj is None:  # Creating new console
            return 144
        return 0  # Editing existing console

    

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
    extra = 0
    can_delete = True
    classes = ['collapse']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        from django.db.models.functions import Cast
        from django.db.models import IntegerField
        return qs.annotate(
            aux_num_int=Cast('aux_number', IntegerField())
        ).order_by('aux_num_int')
    


    def get_extra(self, request, obj=None, **kwargs):
        """Return 48 for new consoles, 0 for existing"""
        if obj is None:  # Creating new console
            return 48
        return 0  # Editing existing console

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
    extra = 0
    can_delete = True
    classes = ['collapse']


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        from django.db.models.functions import Cast
        from django.db.models import IntegerField
        return qs.annotate(
            matrix_num_int=Cast('matrix_number', IntegerField())
        ).order_by('matrix_num_int')
    

    def get_extra(self, request, obj=None, **kwargs):
        """Return 24 for new consoles, 0 for existing"""
        if obj is None:  # Creating new console
            return 24
        return 0  # Editing existing console

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





class ConsoleAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'location','primary_ip_address', 'secondary_ip_address', 'is_template']
    list_filter = ['is_template', 'location']
    
    fieldsets = (
        ('Console Information', {
            'fields': ('name', 'location', 'primary_ip_address', 'secondary_ip_address', 'is_template')
        }),
    )
    
    inlines = [
        ConsoleInputInline,
        ConsoleAuxOutputInline,
        ConsoleMatrixOutputInline,
        ConsoleStereoOutputInline,
    ]
    
    actions = ['export_yamaha_rivage_csvs',]

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    def name_with_template_badge(self, obj):
        if obj.is_template:
            return format_html('<strong>📋 {}</strong>', obj.name)
        return obj.name
    name_with_template_badge.short_description = 'Name'
    name_with_template_badge.admin_order_field = 'name'


    def export_buttons(self, obj):
        """Add PDF and Yamaha CSV export buttons"""
       
        
        
        # PDF export using the new URL pattern
        pdf_url = reverse('planner:console_pdf_export', args=[obj.id])
        
        # Yamaha CSV export using the existing URL pattern
        yamaha_url = f'/admin/planner/console/{obj.pk}/export-yamaha/'
        
        return format_html(
            '<a class="button" href="{}" target="_blank" '
            'style="padding: 6px 12px; background: #4a9eff; color: white; '
            'text-decoration: none; border-radius: 4px; margin-right: 5px; '
            'font-weight: 500;">📄 PDF</a>'
            '<a class="button" href="{}" target="_blank" '
            'style="padding: 6px 12px; background: #2a9d8f; color: white; '
            'text-decoration: none; border-radius: 4px; font-weight: 500;">📊 Yamaha CSV</a>',
            pdf_url,
            yamaha_url
    )

    export_buttons.short_description = 'Exports'
    
    # @admin.action(description='Duplicate selected console (with all inputs/outputs)')
    # def duplicate_console(self, request, queryset):
    #     if queryset.count() != 1:
    #         self.message_user(request, "Please select exactly one console to duplicate.", level='ERROR')
    #         return
        
    #     original = queryset.first()

        
    #     # Create new console
    #     new_console = Console.objects.create(
    #         name=f"{original.name} (Copy)",
    #         is_template=False
    #     )
        
    #     # Duplicate all related inputs
    #     for input_obj in original.consoleinput_set.all():
    #         ConsoleInput.objects.create(
    #             console=new_console,
    #             dante_number=input_obj.dante_number,
    #             input_ch=input_obj.input_ch,
    #             source=input_obj.source,
    #             group=input_obj.group,
    #             dca=input_obj.dca,
    #             mute=input_obj.mute,
    #             direct_out=input_obj.direct_out,
    #             omni_in=input_obj.omni_in,
                
    #         )
        
    #     # Duplicate aux outputs
    #     for aux in original.consoleauxoutput_set.all():
    #         ConsoleAuxOutput.objects.create(
    #             console=new_console,
    #             dante_number=aux.dante_number,
    #             aux_number=aux.aux_number,
    #             name=aux.name,
    #             mono_stereo=aux.mono_stereo,
    #             bus_type=aux.bus_type,
    #             omni_out=aux.omni_out
    #         )
        
    #     # Duplicate matrix outputs
    #     for matrix in original.consolematrixoutput_set.all():
    #         ConsoleMatrixOutput.objects.create(
    #             console=new_console,
    #             dante_number=matrix.dante_number,
    #             matrix_number=matrix.matrix_number,
    #             name=matrix.name,
    #             mono_stereo=matrix.mono_stereo,
    #             omni_out=matrix.omni_out
    #         )
        
    #     # Duplicate stereo outputs
    #     for stereo in original.consolestereooutput_set.all():
    #         ConsoleStereoOutput.objects.create(
    #             console=new_console,
    #             stereo_type=stereo.stereo_type,
    #             name=stereo.name,
    #             dante_number=stereo.dante_number,
    #             omni_out=stereo.omni_out
    #         )
        
    #     self.message_user(request, f"Successfully duplicated '{original.name}' as '{new_console.name}'")
    #     return redirect(f'/admin/planner/console/{new_console.id}/change/')
    

    

    def console_template_library_view(self, request):
        """
        Display all console templates from all projects.
        Allow user to import template to current project.
        """
        # Get current project
        current_project = getattr(request, 'current_project', None)
        
        if not current_project:
            messages.error(request, "No project selected. Please select a project first.")
            return redirect('admin:planner_console_changelist')
        
        # Handle template import POST request
        if request.method == 'POST':
            template_id = request.POST.get('template_id')
            if template_id:
                try:
                    original = Console.objects.get(id=template_id, is_template=True)
                    
                    # Don't import if already in current project
                    if original.project.id == current_project.id:
                        messages.warning(request, f"Template '{original.name}' is already in this project.")
                        return redirect('admin:console_template_library')
                    
                    # Create new console in current project
                    new_console = Console.objects.create(
                        project=current_project,
                        name=f"{original.name} (from {original.project.name})",
                        is_template=False,
                        primary_ip_address=original.primary_ip_address,
                        secondary_ip_address=original.secondary_ip_address,
                    )
                    
                    # Duplicate all related inputs
                    for input_obj in original.consoleinput_set.all().order_by('input_ch'):
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
                        )
                    
                    # Duplicate aux outputs
                    for aux in original.consoleauxoutput_set.all().order_by('aux_number'):
                        ConsoleAuxOutput.objects.create(
                            console=new_console,
                            dante_number=aux.dante_number,
                            aux_number=aux.aux_number,
                            name=aux.name,
                            mono_stereo=aux.mono_stereo,
                            bus_type=aux.bus_type,
                            omni_in=aux.omni_in,
                            omni_out=aux.omni_out,
                        )
                    
                    # Duplicate matrix outputs
                    for matrix in original.consolematrixoutput_set.all().order_by('matrix_number'):
                        ConsoleMatrixOutput.objects.create(
                            console=new_console,
                            dante_number=matrix.dante_number,
                            matrix_number=matrix.matrix_number,
                            name=matrix.name,
                            mono_stereo=matrix.mono_stereo,
                            destination=matrix.destination,
                            omni_out=matrix.omni_out,
                        )
                    
                    messages.success(
                        request, 
                        f"Successfully imported template '{original.name}' as '{new_console.name}'"
                    )
                    return redirect(f'/admin/planner/console/{new_console.id}/change/')
                    
                except Console.DoesNotExist:
                    messages.error(request, "Template not found.")
                    return redirect('admin:console_template_library')
                except Exception as e:
                    messages.error(request, f"Error importing template: {str(e)}")
                    return redirect('admin:console_template_library')
        
        # GET request - show template library
        all_templates = Console.objects.filter(is_template=True).select_related('project').annotate(
            inputs_count=Count('consoleinput', distinct=True),
            aux_count=Count('consoleauxoutput', distinct=True),
            matrix_count=Count('consolematrixoutput', distinct=True),
        ).order_by('project__name', 'name')
        
        # Group templates by project
        templates_by_project = {}
        for template in all_templates:
            if template.project not in templates_by_project:
                templates_by_project[template.project] = []
            templates_by_project[template.project].append(template)
        
        context = {
            'templates_by_project': templates_by_project,
            'current_project': current_project,
            'title': 'Console Template Library',
        }
        
        return render(request, 'admin/planner/console_template_library.html', context)

    

    def changelist_view(self, request, extra_context=None):
        """Add Template Library button to the console list page"""
        extra_context = extra_context or {}
        extra_context['template_library_url'] = '/console-template-library/'
        return super().changelist_view(request, extra_context=extra_context)
    
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
        if queryset.count() == 1:
            from .utils.yamaha_export import export_yamaha_csvs
            console = queryset.first()
            return export_yamaha_csvs(console)
        else:
            self.message_user(request, "Please select exactly one console to export.", level='warning')
    export_yamaha_rivage_csvs.short_description = "Export Yamaha Rivage CSVs"
    
    def get_urls(self):
        """Add custom URL for export"""
        urls = super().get_urls()
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
            'all': ['admin/css/dark_mode.css',
                    'planner/css/custom_admin.css',
                    'planner/css/console_admin.css',
                    'admin/css/console_list_buttons.css']  # ADD THIS LINE
        }



    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter dropdown options based on current project"""
        if db_field.name == "location":
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = Location.objects.filter(project=request.current_project)
            else:
                kwargs["queryset"] = Location.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def get_queryset(self, request):
        """Filter consoles by current project"""
         
        
    def get_queryset(self, request):
        """Filter consoles by current project"""
        qs = super().get_queryset(request)
        
        # DEBUG - print what we see
        print(f"🔍 DEBUG: hasattr current_project: {hasattr(request, 'current_project')}")
        if hasattr(request, 'current_project'):
            print(f"🔍 DEBUG: Current project: {request.current_project}")
            print(f"🔍 DEBUG: Current project ID: {request.current_project.id if request.current_project else 'None'}")
        
        if hasattr(request, 'current_project') and request.current_project:
            filtered_qs = qs.filter(project=request.current_project)
            print(f"🔍 DEBUG: Total consoles: {qs.count()}, Filtered consoles: {filtered_qs.count()}")
            return filtered_qs
        
        print(f"🔍 DEBUG: No project - returning empty queryset")
        return qs.none()
    

    def save_model(self, request, obj, form, change):
        """Auto-assign current project to new consoles"""
        if not change:  # Only for new objects
            if hasattr(request, 'current_project') and request.current_project:
                obj.project = request.current_project
            else:
                # Fallback: get project from session
                project_id = request.session.get('current_project_id')
                if project_id:
                    from .models import Project
                    obj.project = Project.objects.get(id=project_id)
        super().save_model(request, obj, form, change)

# ========== Device Admin ==========


# ———— your inlines here ——————————————————————————————————

class DeviceInputInline(BaseEquipmentInline):
    model = DeviceInput
    form = DeviceInputInlineForm
    extra = 0
    ordering = ['input_number']
    template = "admin/planner/device_input_grid.html"

    def get_queryset(self, request):
        """Order by input_number to ensure grid positions match"""
        qs = super().get_queryset(request)
        return qs.order_by('input_number')
    
    def get_formset(self, request, obj=None, **kwargs):
        # Calculate how many extra forms we need
        if obj:
            existing_inputs = obj.inputs.count()
            needed = obj.input_count - existing_inputs
            kwargs['extra'] = max(0, needed)
        else:
            kwargs['extra'] = 0

        FormSet = super().get_formset(request, obj, **kwargs)
        FormSet.request = request  # Store request on formset
        
        class InitializingFormSet(FormSet):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                for idx, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial.setdefault('input_number', idx + 1)
            
            def get_form_kwargs(self, index):
                """Pass project_id to each form"""
                kwargs = super().get_form_kwargs(index)
                if hasattr(self, 'request'):
                    kwargs['project_id'] = self.request.session.get('current_project_id')
                return kwargs

        return InitializingFormSet


class DeviceOutputInline(BaseEquipmentInline):
    model = DeviceOutput
    form = DeviceOutputInlineForm
    extra = 0
    ordering = ['output_number']
    fields = ['output_number', 'signal_name']
    template = "admin/planner/device_output_grid.html"


    def get_queryset(self, request):
        """Order by output_number to ensure grid positions match"""
        qs = super().get_queryset(request)
        return qs.order_by('output_number')
    
    def get_formset(self, request, obj=None, **kwargs):
        # Calculate how many extra forms we need
        if obj:
            existing_outputs = obj.outputs.count()
            needed = obj.output_count - existing_outputs
            kwargs['extra'] = max(0, needed)
        else:
            kwargs['extra'] = 0

        FormSet = super().get_formset(request, obj, **kwargs)
        FormSet.request = request  # Store request on formset
        
        class InitializingFormSet(FormSet):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                for idx, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial.setdefault('output_number', idx + 1)
            
            def get_form_kwargs(self, index):
                """Pass project_id to each form"""
                kwargs = super().get_form_kwargs(index)
                if hasattr(self, 'request'):
                    kwargs['project_id'] = self.request.session.get('current_project_id')
                return kwargs

        return InitializingFormSet




class DeviceAdmin(BaseEquipmentAdmin):
    inlines = [DeviceInputInline, DeviceOutputInline]
    list_display = ['name','primary_ip_address', 'secondary_ip_address', 'device_actions',]
    #list_filter = ['location',]  
    search_fields = ['name'] 


    class Media:
        css = {
            'all': ('admin/css/device_list_buttons.css',)
        }


    def get_fields(self, request, obj=None):
        """
        On the add form (obj is None) show name + counts.
        On the change form, everything is in the title/inlines,
        so show no fields above the inlines.
        """
        if obj is None:
            return ['name', 'location', 'primary_ip_address', 'secondary_ip_address', 'input_count', 'output_count']
        return ['name', 'location','primary_ip_address', 'secondary_ip_address']
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
    
    
    
    

    
    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        
        # After saving, ensure all input/output slots exist
        device = form.instance
        if device.pk:
            # Fill in missing DeviceInput records
            existing_input_numbers = set(
                device.inputs.values_list('input_number', flat=True)
            )
            for num in range(1, device.input_count + 1):
                if num not in existing_input_numbers:
                    DeviceInput.objects.create(
                        device=device,
                        input_number=num,
                        signal_name=''
                    )
            
            # Fill in missing DeviceOutput records
            existing_output_numbers = set(
                device.outputs.values_list('output_number', flat=True)
            )
            for num in range(1, device.output_count + 1):
                if num not in existing_output_numbers:
                    DeviceOutput.objects.create(
                        device=device,
                        output_number=num,
                        signal_name=''
                    )

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        print("=== CHANGEFORM_VIEW ===")
        print(f"Request method: {request.method}")
        if request.method == "POST":
            print(f"POST data: {request.POST}")
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    




    def changelist_view(self, request, extra_context=None):
        """Add custom buttons to Device list view"""
        extra_context = extra_context or {}
        extra_context['export_all_devices_pdf_url'] = reverse('planner:all_devices_pdf_export')
        return super().changelist_view(request, extra_context=extra_context)
    
    def device_actions(self, obj):
        """Custom column with PDF export button"""
        
       
        
        pdf_url = reverse('planner:device_pdf_export', args=[obj.id])
        
        return format_html(
            '<a class="button" href="{}" target="_blank" '
            'style="background-color: #4a9eff; color: white; padding: 5px 10px; '
            'text-decoration: none; border-radius: 3px; font-size: 12px;">Export PDF</a>',
            pdf_url
        )
    
    device_actions.short_description = 'Actions'


    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter dropdown options based on current project"""
        if db_field.name == "location":
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = Location.objects.filter(project=request.current_project)
            else:
                kwargs["queryset"] = Location.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    


    def get_queryset(self, request):
        """Filter consoles by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()  # No project selected = show nothing
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project to new devices"""
        # Debug info (from your original)
        print("=== SAVE_MODEL CALLED ===")
        print(f"Form is valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        
        if not form.is_valid():
            print("FORM VALIDATION FAILED!")
            for field, errors in form.errors.items():
                print(f"Field '{field}': {errors}")
        
        # Project assignment
        if not change and hasattr(request, 'current_project'):
            obj.project = request.current_project
        
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    



#--------Amps---------

from .models import AmpModel, Amp, AmpChannel


class AmpModelAdmin(admin.ModelAdmin):
    list_display = ('manufacturer', 'model_name', 'channel_count', 
                   'nl4_connector_count', 'cacom_output_count')
    list_filter = ('manufacturer', 'channel_count', 'nl4_connector_count', 'nl8_connector_count')
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
            'fields': ('nl4_connector_count', 'nl8_connector_count', 'cacom_output_count'),
            'classes': ('collapse',)
        }),
    )



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)


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

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'channel_name':
            kwargs['widget'] = forms.TextInput(attrs={
                'placeholder': "e.g., 'PA', 'LF', 'HF', 'SUB'",
                'style': 'font-size: 0.85em;'  # Makes it smaller
            })
        return super().formfield_for_dbfield(db_field, request, **kwargs)


    


    
    
    def has_add_permission(self, request, obj=None):
        return False  # Channels are auto-created
    
    def has_delete_permission(self, request, obj=None):
        return False  # Prevent accidental deletion
    

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        
        # Pass the amp (parent) to each form for project context
        class FormSetWithParent(formset):
            def _construct_form(self, i, **kwargs):
                form = super()._construct_form(i, **kwargs)
                if obj:  # obj is the Amp instance
                    form.parent_instance = obj
                return form
        
        return FormSetWithParent


class AmpAdminForm(forms.ModelForm):
    class Meta:
        model = Amp
        fields = '__all__'
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color', 'value': '#FFFFFF'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'amp_model' in self.data:
            try:
                amp_model_id = int(self.data.get('amp_model'))
                amp_model = AmpModel.objects.get(id=amp_model_id)
                
               # Hide NL4 fields if amp doesn't have NL4 connectors
                if amp_model.nl4_connector_count == 0:
                    for field in ['nl4_a_pair_1', 'nl4_a_pair_2', 'nl4_b_pair_1', 'nl4_b_pair_2']:
                        if field in self.fields:  # ← Add this check
                            self.fields[field].widget = forms.HiddenInput()
                elif amp_model.nl4_connector_count == 1:
                    for field in ['nl4_b_pair_1', 'nl4_b_pair_2']:
                        if field in self.fields:  # ← Add this check
                            self.fields[field].widget = forms.HiddenInput()
                
               # Hide CaCom fields based on cacom_output_count
                cacom_fields = {
                    1: ['cacom_1_ch1', 'cacom_1_ch2', 'cacom_1_ch3', 'cacom_1_ch4'],
                    2: ['cacom_2_ch1', 'cacom_2_ch2', 'cacom_2_ch3', 'cacom_2_ch4'],
                    3: ['cacom_3_ch1', 'cacom_3_ch2', 'cacom_3_ch3', 'cacom_3_ch4'],
                    4: ['cacom_4_ch1', 'cacom_4_ch2', 'cacom_4_ch3', 'cacom_4_ch4'],
                }

                # Hide CaCom connectors not available
                for connector_num, fields in cacom_fields.items():
                    if connector_num > amp_model.cacom_output_count:
                        for field in fields:
                            if field in self.fields:
                                self.fields[field].widget = forms.HiddenInput()

                # Hide NL8 fields if amp doesn't have NL8 connectors
                if amp_model.nl8_connector_count == 0:
                    for field in ['nl8_a_pair_1', 'nl8_a_pair_2', 'nl8_a_pair_3', 'nl8_a_pair_4',
                                'nl8_b_pair_1', 'nl8_b_pair_2', 'nl8_b_pair_3', 'nl8_b_pair_4']:
                        if field in self.fields:
                            self.fields[field].widget = forms.HiddenInput()
                elif amp_model.nl8_connector_count == 1:
                    for field in ['nl8_b_pair_1', 'nl8_b_pair_2', 'nl8_b_pair_3', 'nl8_b_pair_4']:
                        if field in self.fields:
                            self.fields[field].widget = forms.HiddenInput()
                    
            except (ValueError, AmpModel.DoesNotExist):
                pass



class AmpAdmin(BaseEquipmentAdmin):
    form = AmpAdminForm
    list_display = ('name', 'location', 'amp_model', 'ip_address', 'color_preview')
    list_filter = ('location', 'amp_model__manufacturer', 'amp_model__model_name')
    search_fields = ('name', 'ip_address')
    ordering = ['location', 'name']
    actions = ['assign_color_to_amps']

    class Media:
        css = {
            'all': ('admin/css/amp_list_buttons.css',)
        }
        js = ('admin/js/amp_row_colors.js',)  # Keep this one for row coloring
            
    def color_preview(self, obj):
        """Show a small color preview in the list"""
        if obj.color:
            return format_html(
                '<div style="width: 30px; height: 20px; background-color: {}; border: 1px solid #000;"></div>',
                obj.color
            )
        return '-'
    color_preview.short_description = 'Color'



    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Override to handle global vs project-specific ForeignKeys"""
        if db_field.name == "amp_model":
            # AmpModel is global - don't filter by project
            kwargs["queryset"] = AmpModel.objects.all()
        elif db_field.name == "location":
            # Location is project-specific - filter by current project
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = Location.objects.filter(project=request.current_project)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    

    
    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            ('Basic Information', {
                'fields': ('location', 'amp_model', 'name', 'ip_address', 'color')
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
                
            }))
        
        if obj and obj.amp_model.cacom_output_count > 0:
            cacom_fields = []
            for i in range(1, min(obj.amp_model.cacom_output_count + 1, 5)):
                # Each CaCom has 4 channels
                cacom_fields.extend([
                    f'cacom_{i}_ch1',
                    f'cacom_{i}_ch2',
                    f'cacom_{i}_ch3',
                    f'cacom_{i}_ch4'
                ])
            
            fieldsets.append(('CaCom Outputs', {
                'fields': cacom_fields,
                
            }))


        if obj and obj.amp_model.nl8_connector_count > 0:
            nl8_fields = []
            if obj.amp_model.nl8_connector_count >= 1:
                nl8_fields.extend(['nl8_a_pair_1', 'nl8_a_pair_2', 'nl8_a_pair_3', 'nl8_a_pair_4'])
            if obj.amp_model.nl8_connector_count >= 2:
                nl8_fields.extend(['nl8_b_pair_1', 'nl8_b_pair_2', 'nl8_b_pair_3', 'nl8_b_pair_4'])
            
            fieldsets.append(('NL8 Connectors', {
                'fields': nl8_fields,
                'classes': ('collapse',)
            }))    

        return fieldsets
    
    inlines = [AmpChannelInline]

    #----Only show locations in this project--

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter dropdown options based on current project"""
        if db_field.name == "location":
            # Only show locations from the current project
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = Location.objects.filter(project=request.current_project)
            else:
                kwargs["queryset"] = Location.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    #----Only show Amps in this project


    def get_queryset(self, request):
            """Filter consoles by current project"""
            qs = super().get_queryset(request)
            if hasattr(request, 'current_project') and request.current_project:
                return qs.filter(project=request.current_project)
            return qs.none()  # No project selected = show nothing
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project to new consoles"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)    

    @admin.action(description='Assign color to selected amps')
    def assign_color_to_amps(self, request, queryset):
        """Bulk assign color to selected amps"""
        if 'apply' in request.POST:
            # Get the color from the form
            color = request.POST.get('color')
            # Get the amp IDs from hidden fields
            amp_ids = request.POST.getlist('_selected_action')
            
            if color and amp_ids:
                # Reconstruct the queryset from the IDs
                amps = Amp.objects.filter(id__in=amp_ids)
                count = amps.update(color=color)
                self.message_user(request, f'Color {color} assigned to {count} amp(s).', messages.SUCCESS)
                return HttpResponseRedirect(request.get_full_path())
        
        # Show intermediate page with color picker
        return render(request, 'admin/assign_amp_color.html', {
            'amps': queryset,
            'action': 'assign_color_to_amps',
            'queryset': queryset
        })
    
    def render_change_form(self, request, context, *args, **kwargs):
        """Override to reorder inline formsets"""
        # Call parent to get the context
        context = super().render_change_form(request, context, *args, **kwargs)
        
        # Check if we have inline_admin_formsets in context
        if 'inline_admin_formsets' in context and context['inline_admin_formsets']:
            # Store the inline formsets
            inlines = context['inline_admin_formsets']
            
            # We'll inject custom ordering flag
            context['show_inputs_first'] = True
            context['amp_channel_inline'] = inlines
        
        return context



class LocationAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'description', 'amp_count', 'processor_count', 'export_pdf_button']
    search_fields = ['name', 'description']
    ordering = ['name']
    
    fieldsets = (
        ('Location Information', {
            'fields': ('name', 'description')
        }),
    )


    class Media:
        css = {
            'all': ('admin/css/location_admin.css',)
        }
    
    

    def export_pdf_button(self, obj):
        """PDF export button for each location"""
        url = reverse('planner:location_pdf_export', args=[obj.id])
        return format_html(
            '<a class="button" href="{}" target="_blank">📄 Export PDF</a>',
            url
        )
    export_pdf_button.short_description = 'Export'
    export_pdf_button.allow_tags = True
    
    def amp_count(self, obj):
        """Show how many amps are in this location"""
        return obj.amps.count()
    amp_count.short_description = 'Amps'
    
    def processor_count(self, obj):
        """Show how many processors are in this location"""
        return obj.system_processors.count()
    processor_count.short_description = 'Processors'
                
    def get_queryset(self, request):
        """Filter consoles by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()  # No project selected = show nothing
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project to new consoles"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)    


        #------------Processor------

class SystemProcessorAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'device_type', 'location', 'ip_address', 'created_at', 'configure_button']
    list_filter = ['device_type', 'location', 'created_at']
    search_fields = ['name', 'ip_address']
    exclude = ['project']

    def configure_button(self, obj):
        if obj.pk:  # Only show for saved objects
            # ✅ ALWAYS use configure_view - it handles everything
            url = reverse('admin:systemprocessor-configure', args=[obj.pk])
            
            if obj.device_type == 'P1':
                try:
                    obj.p1_config  # Check if exists
                    button_text = 'Configure P1'
                except P1Processor.DoesNotExist:
                    button_text = 'Setup P1 Configuration'
                return format_html('<a class="button" href="{}">{}</a>', url, button_text)
            
            elif obj.device_type == 'GALAXY':
                try:
                    obj.galaxy_config
                    button_text = 'Configure GALAXY'
                except GalaxyProcessor.DoesNotExist:
                    button_text = 'Setup GALAXY Configuration'
                return format_html('<a class="button" href="{}">{}</a>', url, button_text)
        
        return '-'

    configure_button.short_description = 'Configuration'
    configure_button.allow_tags = True
    
    
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:pk>/configure/', 
                self.admin_site.admin_view(self.configure_view),  # ✅ Wrap with admin_view
                name='systemprocessor-configure'),
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
    

    #----Only show Equip Locaions for this project---

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter dropdown options based on current project"""
        if db_field.name == "location":
            # Only show locations from the current project
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = Location.objects.filter(project=request.current_project)
            else:
                kwargs["queryset"] = Location.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    #-----Only show Processors for this project----
    def get_queryset(self, request):
        """Filter consoles by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()  # No project selected = show nothing
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project to new consoles"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)    




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


class P1ProcessorAdmin(BaseEquipmentAdmin):
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
    

    def get_queryset(self, request):
        """Filter P1 processors by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(system_processor__project=request.current_project)
        return qs.none()

    def response_change(self, request, obj):
        """After saving, redirect back to System Processors list"""
        if "_continue" not in request.POST and "_addanother" not in request.POST and "_save" in request.POST:
            messages.success(request, f'P1 Configuration for "{obj.system_processor.name}" was changed successfully.')
            return HttpResponseRedirect(reverse('admin:planner_systemprocessor_changelist'))
        return super().response_change(request, obj)
    
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
        
    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)    
    
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



class GalaxyProcessorAdmin(BaseEquipmentAdmin):
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
    
    def get_queryset(self, request):
        """Filter Galaxy processors by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(system_processor__project=request.current_project)
        return qs.none()

    def response_change(self, request, obj):
        """After saving, redirect back to System Processors list"""
        if "_continue" not in request.POST and "_addanother" not in request.POST and "_save" in request.POST:
            messages.success(request, f'GALAXY Configuration for "{obj.system_processor.name}" was changed successfully.')
            return HttpResponseRedirect(reverse('admin:planner_systemprocessor_changelist'))
        return super().response_change(request, obj)
    
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
        

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)    
    
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

class PAZoneAdmin(BaseEquipmentAdmin):
    form = PAZoneForm
    list_display = ['name', 'description', 'zone_type', 'sort_order', 'location']
    list_filter = ['zone_type', 'location']
    search_fields = ['name', 'description']
    list_editable = ['sort_order']
    ordering = ['sort_order', 'name']
    
    actions = ['create_default_zones']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter location dropdown by current project"""
        if db_field.name == 'location':
            if hasattr(request, 'current_project') and request.current_project:
                kwargs['queryset'] = Location.objects.filter(
                    project=request.current_project
                ).order_by('name')
            else:
                kwargs['queryset'] = Location.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        """Filter zones by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            from django.db.models import Q
            return qs.filter(project=request.current_project)
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)
    
    # ... rest of existing code ...

    # Hide from sidebar but still accessible via direct URL
    def has_module_permission(self, request):
        return False
    
    def create_default_zones(self, request, queryset):
        """Create standard L'Acoustics zones"""
        PAZone.create_default_zones()
        self.message_user(request, "Default zones have been created.")
    create_default_zones.short_description = "Create default L'Acoustics zones"


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)


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


class PACableAdmin(BaseEquipmentAdmin):
    """Admin for PA Cable Schedule"""
    form = PACableInlineForm
    inlines = [PAFanOutInline]  # Add this line
    list_display = [
    'label','destination', 'count', 'length',
    'cable_display', 'fan_out_summary_display',  # Changed from 'fan_out'
    'notes', 'drawing_ref'
]
    list_filter = ['cable']
    search_fields = ['destination', 'notes', 'drawing_ref']
    list_editable = ['count' ,'length']  
    
    change_list_template = 'admin/planner/pacableschedule/change_list.html'
    
    fieldsets = (
        ('Cable Configuration', {
            'fields': ('label','destination', 'count', 'length' , 'cable')
        }),
      
        
        ('Documentation', {
            'fields': ('notes', 'drawing_ref')
        })
    )
    
    actions = ['export_cable_schedule']


   
    
    
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
                # Initialize counters FIRST - at this indentation level
                hundreds = 0
                fifties = 0
                twenty_fives = 0
                tens = 0
                fives = 0
                total_length = 0  # ← Must be here, BEFORE the loop
                
                # Process each cable individually
                for cable in cables:
                    cable_length = cable.total_cable_length
                    total_length += cable_length
                    
                    # Round THIS cable to standard lengths
                    remaining = cable_length
                    
                    # Count 100' cables for this run
                    while remaining > 50:
                        hundreds += 1
                        remaining -= 100
                    
                    # Count remaining
                    if remaining > 25:
                        fifties += 1
                    elif remaining > 10:
                        twenty_fives += 1
                    elif remaining > 5:
                        tens += 1
                    elif remaining > 0:
                        fives += 1
                
                # AFTER the loop, check and add to summary
                if total_length > 0:
                    cable_summary[cable_type[1]] = {
                        'total_runs': cables.aggregate(Sum('count'))['count__sum'] or 0,
                        'total_length': total_length,
                        'hundreds': hundreds,
                        'hundreds_with_safety': math.ceil(hundreds * 1.2),
                        'fifties': fifties,
                        'fifties_with_safety': math.ceil(fifties * 1.2),
                        'twenty_fives': twenty_fives,
                        'twenty_fives_with_safety': math.ceil(twenty_fives * 1.2),
                        'tens': tens,
                        'tens_with_safety': math.ceil(tens * 1.2),
                        'fives': fives,
                        'fives_with_safety': math.ceil(fives * 1.2),
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


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('planner/css/pa_cable_admin.css',)
        }
        js = ('planner/js/pa_cable_calculations.js',)


    def get_queryset(self, request):
        """Filter by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)

                #--------COMM Page-------

# Add these to your planner/admin.py file



from .models import CommChannel, CommPosition, CommCrewName, CommBeltPack
from django.http import HttpResponseRedirect

# Comm Channel Admin

class CommChannelAdmin(BaseEquipmentAdmin):
    list_display = ['channel_number', 'name', 'abbreviation', 'channel_type', 'order']
    list_editable = ['order']
    ordering = ['order', 'channel_number']
    search_fields = ['name', 'abbreviation', 'channel_number']
    
    def get_model_perms(self, request):
        """Show in COMM section of admin"""
        return super().get_model_perms(request)
    


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/comm_channel_buttons.css',)
        }
        


def _get_current_project(modeladmin, request):
    """Helper to get current project for admin actions"""
    if not hasattr(request, 'current_project') or not request.current_project:
        modeladmin.message_user(request, "No project selected", level=messages.ERROR)
        return None
    
    from planner.models import Project
    if isinstance(request.current_project, Project):
        return request.current_project
    else:
        try:
            return Project.objects.get(id=request.current_project)
        except Project.DoesNotExist:
            modeladmin.message_user(request, "Invalid project", level=messages.ERROR)
            return None
        




# Comm Position Admin

@admin.action(description='Populate common positions')
def populate_common_positions(modeladmin, request, queryset):
    """Create common position options"""
    # Get current project
    if not hasattr(request, 'current_project') or not request.current_project:
        modeladmin.message_user(request, "No project selected", level=messages.ERROR)
        return
    
    from planner.models import Project
    if isinstance(request.current_project, Project):
        project = request.current_project
    else:
        try:
            project = Project.objects.get(id=request.current_project)
        except Project.DoesNotExist:
            modeladmin.message_user(request, "Invalid project", level=messages.ERROR)
            return
    
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
        ('Cam 1',16),
        ('Cam 2',17),
        ('Cam 3',18),

    ]
    
    for name, order in positions:
        CommPosition.objects.get_or_create(
            name=name,
            project=project,
            defaults={'order': order}
        )
    
    modeladmin.message_user(request, "Common positions populated successfully.")



class CommPositionAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'order']
    list_editable = ['order']
    ordering = ['order', 'name']
    search_fields = ['name']

    def get_queryset(self, request):
        """Filter positions by current project"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            if hasattr(request, 'current_project') and request.current_project:
                return qs.filter(project=request.current_project)
            return qs
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()
    
    
    actions = [populate_common_positions]  # Make sure this is defined
    
    def changelist_view(self, request, extra_context=None):
        """Allow populate action to work on empty list"""
        
        # Special handling ONLY for populate action
        if 'action' in request.POST and request.POST['action'] == 'populate_common_positions':
            action = self.get_actions(request)['populate_common_positions'][0]
            action(self, request, self.get_queryset(request))  # Use actual queryset
            return HttpResponseRedirect(request.get_full_path())
        
        # For all other actions (including delete), use normal behavior
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
    

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/comm_position_buttons.css',)
        }
    
    


# Comm Crew Name Admin

class CommCrewNameAdmin(BaseEquipmentAdmin):
    list_display = ['name']
    ordering = ['name']
    search_fields = ['name']
    exclude = ['project']
    
    def get_urls(self):
        """Add custom URL for CSV import."""
       
        urls = super().get_urls()
        custom_urls = [
            path('import-csv/', self.admin_site.admin_view(self.import_csv_view), name='planner_commcrewname_import_csv'),
        ]
        return custom_urls + urls
    
    def import_csv_view(self, request):
        """Redirect to the import view."""
        from django.shortcuts import redirect
    
        return redirect('planner:import_comm_crew_names_csv')
    
    def changelist_view(self, request, extra_context=None):
        """Add import button to changelist."""
        extra_context = extra_context or {}
        extra_context['show_import_csv'] = True
        return super().changelist_view(request, extra_context)
    

    def get_queryset(self, request):
        """Filter crew names by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()
    
    def get_model_perms(self, request):
        """Show in COMM section of admin"""
        return super().get_model_perms(request)
    


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)

        
    class Media:
        css = {
            'all': ('admin/css/comm_crew_name_buttons.css',)
        }

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

# Simpler action functions with different quantities
def create_5_wireless_beltpacks(modeladmin, request, queryset):
    """Create 5 wireless belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='WIRELESS',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 6):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            project=project
        )
    
    modeladmin.message_user(request, f"Created 5 wireless belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_5_wireless_beltpacks.short_description = 'Create 5 Wireless belt packs'


def create_10_wireless_beltpacks(modeladmin, request, queryset):
    """Create 10 wireless belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='WIRELESS',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 11):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            project=project
        )
    
    modeladmin.message_user(request, f"Created 10 wireless belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_10_wireless_beltpacks.short_description = 'Create 10 Wireless belt packs'

def create_20_wireless_beltpacks(modeladmin, request, queryset):
    """Create 20 wireless belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='WIRELESS',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 21):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            project=project
        )
    
    modeladmin.message_user(request, f"Created 20 wireless belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_20_wireless_beltpacks.short_description = 'Create 20 Wireless belt packs'
    
    

def create_50_wireless_beltpacks(modeladmin, request, queryset):
    """Create 50 wireless belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='WIRELESS',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 51):
        CommBeltPack.objects.create(
            system_type='WIRELESS',
            bp_number=max_bp + i,
            project=project
        )
    
    modeladmin.message_user(request, f"Created 50 wireless belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_50_wireless_beltpacks.short_description = 'Create 50 Wireless belt packs'

# Hardwired versions
def create_5_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 5 hardwired belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='HARDWIRED',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 6):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i,
            project=project
            # Note: NO unit_location for hardwired
        )
    
    modeladmin.message_user(request, f"Created 5 hardwired belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_5_hardwired_beltpacks.short_description = 'Create 5 Hardwired belt packs'

def create_10_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 10 hardwired belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='HARDWIRED',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 11):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i,
            project=project
            # Note: NO unit_location for hardwired
        )
    
    modeladmin.message_user(request, f"Created 10 hardwired belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_10_hardwired_beltpacks.short_description = 'Create 10 Hardwired belt packs'

def create_20_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 20 hardwired belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='HARDWIRED',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 21):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i,
            project=project
            # Note: NO unit_location for hardwired
        )
    
    modeladmin.message_user(request, f"Created 20 hardwired belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_20_hardwired_beltpacks.short_description = 'Create 20 Hardwired belt packs'

def create_50_hardwired_beltpacks(modeladmin, request, queryset):
    """Create 50 hardwired belt packs"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    max_bp = CommBeltPack.objects.filter(
        system_type='HARDWIRED',
        project=project
    ).aggregate(Max('bp_number'))['bp_number__max'] or 0
    
    for i in range(1, 51):
        CommBeltPack.objects.create(
            system_type='HARDWIRED',
            bp_number=max_bp + i,
            project=project
            # Note: NO unit_location for hardwired
        )
    
    modeladmin.message_user(request, f"Created 50 hardwired belt packs (BP #{max_bp+1} to #{max_bp+5})")
create_50_hardwired_beltpacks.short_description = 'Create 50 Hardwired belt packs'

def clear_all_beltpacks(modeladmin, request, queryset):
    """Delete ALL belt packs in current project - use with caution"""
    project = _get_current_project(modeladmin, request)
    if not project:
        return
    
    count = CommBeltPack.objects.filter(project=project).count()
    if count > 0:
        CommBeltPack.objects.filter(project=project).delete()
        modeladmin.message_user(request, f"Deleted {count} belt packs", level=messages.WARNING)
    else:
        modeladmin.message_user(request, "No belt packs to delete")
clear_all_beltpacks.short_description = '⚠️ DELETE all belt packs'









class CommBeltPackChannelInline(admin.TabularInline):
    """Inline for managing belt pack channels"""
    model = CommBeltPackChannel
    extra = 0  # Don't show empty forms by default
    fields = ['channel_number', 'channel']
    ordering = ['channel_number']
    
    def has_add_permission(self, request, obj=None):
        """Allow users with change permission on parent to add channels"""
        if request.user.is_superuser:
            return True
        # Check if user has permission to edit the parent belt pack
        return request.user.has_perm('planner.change_commbeltpack')
    
    def has_change_permission(self, request, obj=None):
        """Allow users with change permission on parent to edit channels"""
        if request.user.is_superuser:
            return True
        return request.user.has_perm('planner.change_commbeltpack')
    
    def has_delete_permission(self, request, obj=None):
        """Allow users with change permission on parent to delete channels"""
        if request.user.is_superuser:
            return True
        return request.user.has_perm('planner.change_commbeltpack')
    

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter channel dropdown by current project"""
        if db_field.name == "channel":
            current_project = getattr(request, "current_project", None)
            if current_project:
                kwargs["queryset"] = CommChannel.objects.filter(project=current_project)
            else:
                kwargs["queryset"] = CommChannel.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    

    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        return formset
    


class CommBeltPackAdminForm(forms.ModelForm):
    """Custom form to handle dynamic field display based on system type"""
    
    class Meta:
        model = CommBeltPack
        fields = '__all__'
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hide checked_out field for Hardwired beltpacks
        if self.instance and self.instance.system_type == 'HARDWIRED':
            if 'checked_out' in self.fields:
                self.fields['checked_out'].widget = forms.HiddenInput()
                self.fields['checked_out'].required = False
        
        # For new objects, add help text
        if not self.instance.pk:
            if 'checked_out' in self.fields:
                self.fields['checked_out'].help_text = "Whether this belt pack has been checked out (Wireless only)"
        
        # ========================================
        # FIX MULTI-TENANCY: Filter querysets by project
        # ========================================
        if self.instance and self.instance.project_id:
            project = self.instance.project
            
            # Filter position dropdown to current project only
            if 'position' in self.fields:
                self.fields['position'].queryset = CommPosition.objects.filter(project=project).order_by('name')
            
            # Filter name dropdown to current project only
            if 'name' in self.fields:
                self.fields['name'].queryset = CommCrewName.objects.filter(project=project).order_by('name')
            
            # Filter all 6 channel dropdowns to current project only
            for channel_field in ['channel_a', 'channel_b', 'channel_c', 'channel_d', 'channel_e', 'channel_f']:
                if channel_field in self.fields:
                    self.fields[channel_field].queryset = CommChannel.objects.filter(project=project).order_by('input_designation')

    class Media:
        css = {
           'all': ('admin/css/comm_admin_v2.css',)
        }
        js = ('admin/js/comm_beltpack_admin.js',) 
        

# Custom filters that respect current project for CommBeltPack
class ProjectFilteredPositionFilter(admin.SimpleListFilter):
    title = 'position'
    parameter_name = 'position'
    
    def lookups(self, request, model_admin):
        current_project = getattr(request, 'current_project', None)
        if current_project:
            # Get distinct positions used in this project's beltpacks
            positions = CommPosition.objects.filter(
                beltpacks__project=current_project
            ).distinct().order_by('name')
            return [(p.id, p.name) for p in positions]
        return []
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(position_id=self.value())
        return queryset


class ProjectFilteredLocationFilter(admin.SimpleListFilter):
    title = 'Location'
    parameter_name = 'unit_location'
    
    def lookups(self, request, model_admin):
        current_project = getattr(request, 'current_project', None)
        if current_project:
            locations = Location.objects.filter(project=current_project).order_by('name')
            return [(loc.id, loc.name) for loc in locations]
        return []
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(unit_location_id=self.value())
        return queryset


class CommBeltPackAdmin(BaseEquipmentAdmin):
    form = CommBeltPackAdminForm
    
    # Add autocomplete for better UX (optional but recommended)
    #autocomplete_fields = ['position', 'name', 'channel_a', 'channel_b', 'channel_c', 'channel_d', 'channel_e', 'channel_f']
    
    # Right after autocomplete_fields, add:
    list_display = [
        'bp_number',
        'system_type_icon',  # Custom method
        'manufacturer_display',  # Custom method  
        'position',  # Keep as field for inline editing
        'name',
        'unit_location',  # Location column
        'channel_summary',
        'headset',
        'ip_address',
        'checked_out'
    ]




      # ← Line 3324 - end of list_display
    
    # ADD THIS RIGHT HERE:
    list_editable = [
        'position',
        'name',
        'unit_location',
        'headset',
        'ip_address',
        'checked_out'
    ]
    
        
    
    list_filter = [
        'system_type', 
        'manufacturer', 
        ProjectFilteredLocationFilter,
        ProjectFilteredPositionFilter,
        'headset',
        'checked_out',
    ]
    inlines = [CommBeltPackChannelInline]
    search_fields = ['bp_number', 'name__name', 'position__name', 'notes', 'unit_location__name', 'ip_address']
    ordering = ['system_type', 'bp_number']
    
    def get_changelist_formset(self, request, **kwargs):
        """Override to filter unit_location dropdown by current project in list view"""
        formset = super().get_changelist_formset(request, **kwargs)
        
        # Get current project
        current_project = getattr(request, 'current_project', None)
        
        if current_project:
            # Get the form class and override the queryset for unit_location
            form = formset.form
            if 'unit_location' in form.base_fields:
                # Create a copy of the field to avoid modifying the original
                import copy
                form.base_fields['unit_location'] = copy.deepcopy(form.base_fields['unit_location'])
                form.base_fields['unit_location'].queryset = Location.objects.filter(project=current_project)
        
        return formset
    
    # Actions for checking in/out and bulk creation
    actions = [
        'duplicate_beltpacks',
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
    
    def system_type_icon(self, obj):
        """Display icon for system type"""
        if obj.system_type == 'WIRELESS':
            return '📡'
        return '🔌'
    system_type_icon.short_description = 'Type'

    def manufacturer_display(self, obj):
        """Display manufacturer name"""
        return obj.get_manufacturer_display()
    manufacturer_display.short_description = 'System'
    manufacturer_display.admin_order_field = 'manufacturer'

    def channel_summary(self, obj):
        """Display summary of assigned channels with visual badges (3 per row)"""
        from django.utils.safestring import mark_safe
        
        channels = obj.channels.all()
        if not channels:
            return mark_safe('<span style="color: #666;">No channels</span>')
        
        # Initialize badges list
        badges = []
        
        # Create visual badges for each channel
        for ch in channels[:12]:  # Show first 12
            if ch.channel:
                # Get channel info
                ch_num = ch.channel_number
                ch_abbrev = ch.channel.abbreviation if hasattr(ch.channel, 'abbreviation') and ch.channel.abbreviation else ch.channel.name[:4]
                
                # Create a colored badge
                badge = f'''<span style="display: inline-block; background: #14b8a6; color: #000; padding: 2px 8px; margin: 2px; border-radius: 3px; font-size: 11px; font-weight: 500; white-space: nowrap; min-width: 75px; text-align: center;">{ch_num}: {ch_abbrev}</span>'''
                badges.append(badge)
            else:
                # Empty channel badge
                badge = f'''<span style="display: inline-block; background: #333; color: #666; padding: 2px 8px; margin: 2px; border-radius: 3px; font-size: 11px; white-space: nowrap; min-width: 75px; text-align: center;">{ch.channel_number}: —</span>'''
                badges.append(badge)
        
        # Wrap in a container that displays 3 per row
        result = f'''<div style="display: grid; grid-template-columns: repeat(4, auto); gap: 3px; max-width: 380px; justify-items: start;">{''.join(badges)}</div>'''
        
        if channels.count() > 12:
            result += f'''<span style="color: #14b8a6; font-size: 11px; margin-left: 5px;">+{channels.count() - 12} more</span>'''
        
        return mark_safe(result)

    channel_summary.short_description = 'Channels'

    

    def duplicate_beltpacks(self, request, queryset):
        """Duplicate selected belt packs with all their channels"""
        project = request.current_project
        duplicated_count = 0
        
        for original_pack in queryset:
            # Get the highest bp_number for this project to assign new numbers
            max_bp = CommBeltPack.objects.filter(project=project).aggregate(
                models.Max('bp_number')
            )['bp_number__max'] or 0
            
            # Store the original channels before duplicating
            original_channels = list(original_pack.channels.all())
            
            # Duplicate the belt pack
            original_pack.pk = None  # This will create a new record
            original_pack.bp_number = max_bp + 1
            original_pack.checked_out = False  # Reset checked out status
            original_pack.save()
            
            # Duplicate all channels
            for channel in original_channels:
                CommBeltPackChannel.objects.create(
                    beltpack=original_pack,
                    channel_number=channel.channel_number,
                    channel=channel.channel
                )
            
            duplicated_count += 1
        
        self.message_user(
            request,
            f"Successfully duplicated {duplicated_count} belt pack(s) with all channels.",
            messages.SUCCESS
        )
                            
    duplicate_beltpacks.short_description = "Duplicate selected belt packs"
        
    class Media:
        css = {
            'all': ('admin/css/comm_admin_v2.css',)
        }
        js = ('admin/js/comm_beltpack_admin.js',)





    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter dropdown options by current project for multi-tenancy"""
        
        # Get the current project from the request
        current_project = getattr(request, 'current_project', None)
        
        if current_project:
            # Filter location dropdown
            if db_field.name == "unit_location":
                kwargs["queryset"] = Location.objects.filter(project=current_project).order_by('name')
            
            # Filter position dropdown
            elif db_field.name == "position":
                kwargs["queryset"] = CommPosition.objects.filter(project=current_project).order_by('name')
            
            # Filter name dropdown
            elif db_field.name == "name":
                kwargs["queryset"] = CommCrewName.objects.filter(project=current_project).order_by('name')
            
            # Filter channel dropdowns (all 6 channels)
            elif db_field.name in ['channel_a', 'channel_b', 'channel_c', 'channel_d', 'channel_e', 'channel_f']:
                kwargs["queryset"] = CommChannel.objects.filter(project=current_project).order_by('input_designation')
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


    
    
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
        if obj.channel_e:
            channels.append(f"E:{obj.channel_e.abbreviation}")
        if obj.channel_f:
            channels.append(f"F:{obj.channel_f.abbreviation}")
        return " | ".join(channels) if channels else "-"
    display_channels.short_description = "Channels"
    
    def get_fieldsets(self, request, obj=None):
        """Dynamic fieldsets based on system type"""
        # Base fieldsets without checked_out
        base_fieldsets = [
            ('System Configuration', {
                'fields': ('system_type', 'manufacturer', 'bp_number', 'unit_location', 'ip_address')
            }),
            ('Assignment', {
                'fields': ('position', 'name', 'headset'),
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
    

    def changelist_view(self, request, extra_context=None):
        """Add summary information grouped by system type"""
        extra_context = extra_context or {}
        
        # Get current project
        current_project = getattr(request, 'current_project', None)
        
        if current_project:
            # Get counts by system type - FILTERED BY PROJECT
            wireless_total = CommBeltPack.objects.filter(
                project=current_project, 
                system_type='WIRELESS'
            ).count()
            wireless_checked = CommBeltPack.objects.filter(
                project=current_project,
                system_type='WIRELESS', 
                checked_out=True
            ).count()
            hardwired_total = CommBeltPack.objects.filter(
                project=current_project,
                system_type='HARDWIRED'
            ).count()
            hardwired_checked = CommBeltPack.objects.filter(
                project=current_project,
                system_type='HARDWIRED', 
                checked_out=True
            ).count()
            
            # Group counts by system
            wireless_groups = {}
            hardwired_groups = {}
            
            for choice_key, choice_name in CommBeltPack.GROUP_CHOICES:
                if choice_key:
                    w_count = CommBeltPack.objects.filter(
                        project=current_project,
                        system_type='WIRELESS', 
                        group=choice_key
                    ).count()
                    h_count = CommBeltPack.objects.filter(
                        project=current_project,
                        system_type='HARDWIRED', 
                        group=choice_key
                    ).count()
                    
                    if w_count > 0:
                        wireless_groups[choice_name] = w_count
                    if h_count > 0:
                        hardwired_groups[choice_name] = h_count
            
            extra_context.update({
                'wireless_total': wireless_total,
                'wireless_checked': wireless_checked,
                'wireless_available': wireless_total - wireless_checked,
                'hardwired_total': hardwired_total,
                'hardwired_available': hardwired_total - hardwired_checked,
                'wireless_groups': wireless_groups,
                'hardwired_groups': hardwired_groups,
            })
        
        return super().changelist_view(request, extra_context)
    

    def get_queryset(self, request):
            """Filter by current project"""
            qs = super().get_queryset(request)
            if hasattr(request, 'current_project') and request.current_project:
                return qs.filter(project=request.current_project)
            return qs.none()
    

    def save_model(self, request, obj, form, change):
        """Auto-assign current project when creating new belt pack"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)
        

    
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
    
   
    

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    

    
    
    


# Add a custom admin action to populate default channels
@admin.action(description='Populate default channels')
def populate_default_channels(modeladmin, request, queryset):
    """Create the default 10 FS II channels"""
    # Get current project
    if not hasattr(request, 'current_project') or not request.current_project:
        modeladmin.message_user(request, "No project selected", level=messages.ERROR)
        return
    
    from planner.models import Project
    if isinstance(request.current_project, Project):
        project = request.current_project
    else:
        try:
            project = Project.objects.get(id=request.current_project)
        except Project.DoesNotExist:
            modeladmin.message_user(request, "Invalid project", level=messages.ERROR)
            return
    
    default_channels = [
        ('1 4W', '1', 'Production', 'PROD', 1),
        ('2 4W', '2', 'Audio', 'AUDIO', 2),
        ('3 4W', '3', 'Video', 'VIDEO', 3),
        ('4 4W', '4', 'Lights', 'LIGHTS', 4),
        ('A 2W', '5', 'Camera', 'CAMS', 5),
        ('B 2W', '6', 'Graphics', 'GFX', 6),
        ('C 2W', '7', 'Stage Mgr', 'SM', 7),
        ('D 2W', '8', 'Carps', 'CARP', 8),
        ('', '9', 'ALL', 'ALL', 9),
        ('', '10', 'Program', 'PGM', 10),
    ]
    
    for input_des, channel_num, name, abbr, order in default_channels:
        CommChannel.objects.get_or_create(
            channel_number=channel_num,
            project=project,
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
    
class MicAssignmentInline(BaseEquipmentInline):
    model = MicAssignment
    form = MicAssignmentForm
    extra = 0
    fields = ['rf_number', 'mic_type', 'presenter', 'is_micd', 'is_d_mic', 'notes']
    ordering = ['rf_number']
    readonly_fields = ['rf_number']

    

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter presenter dropdown by current project"""
        if db_field.name == "presenter":
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = Presenter.objects.filter(project=request.current_project)
            else:
                kwargs["queryset"] = Presenter.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Filter shared presenters by current project"""
        if db_field.name == "shared_presenters":
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = Presenter.objects.filter(project=request.current_project)
            else:
                kwargs["queryset"] = Presenter.objects.none()
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class ShowDayAdmin(BaseEquipmentAdmin):
    list_display = ('date', 'name', 'session_count', 'total_mics', 'mics_used', 'view_day_link')
    list_filter = ('date',)
    search_fields = ('name',)
    ordering = ['date']
    exclude = ['project']
    
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
        url = reverse('planner:mic_tracker') + f'?day={obj.id}'
        return format_html('<a href="{}" class="button">View Day</a>', url)
    view_day_link.short_description = "View"


    def get_queryset(self, request):
        """Filter by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)  

    class Media:
        css = {
            'all': ('admin/css/show_mic_tracker_buttons.css',)
        }  


class PresenterAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    ordering = ['name']
    exclude = ['project']


    def save_model(self, request, obj, form, change):
        """Auto-assign current project when adding presenter"""
        if not change:  # Only for new presenters
            if hasattr(request, 'current_project') and request.current_project:
                from planner.models import Project
                try:
                    # Check if it's already a Project object or if it's an ID
                    if isinstance(request.current_project, Project):
                        obj.project = request.current_project
                    else:
                        obj.project = Project.objects.get(id=request.current_project)
                except Project.DoesNotExist:
                    pass
        super().save_model(request, obj, form, change)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_url'] = '/audiopatch/api/presenters/import/'
        return super().changelist_view(request, extra_context=extra_context)
    

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/presenter_buttons.css',)
        }
    
   



class MicSessionAdmin(BaseEquipmentAdmin):
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(day__project=request.current_project)
        return qs.none()
    
    def mic_usage(self, obj):
        stats = obj.get_mic_usage_stats()
        return f"{stats['micd']}/{stats['total']}"
    mic_usage.short_description = "Mics Used"
    
    def edit_mics_link(self, obj):
        url = f'/audiopatch/mic-tracker/?session={obj.id}'
        return format_html('<a href="{}" class="button">Quick Edit</a>', url)
        edit_mics_link.short_description = "Quick Edit"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Update mic assignments if num_mics changed
        if 'num_mics' in form.changed_data:
            obj.create_mic_assignments()


    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key dropdowns by current project"""
        if db_field.name == "day":
            current_project = getattr(request, 'current_project', None)
            if current_project:
                from .models import ShowDay
                kwargs["queryset"] = ShowDay.objects.filter(project=current_project)
            else:
                from .models import ShowDay
                kwargs["queryset"] = ShowDay.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)    

    class Media:
        css = {
            'all': ('admin/css/mic_session_buttons.css',)
        }
        js = ('admin/js/mic_tracker_auto_refresh.js',)


class MicAssignmentAdmin(BaseEquipmentAdmin):
    form = MicAssignmentForm
    list_display = ('rf_display', 'session', 'mic_type', 'presenter_display', 'is_micd', 'is_d_mic', 'last_modified')
    list_filter = ('session__day', 'session', 'mic_type', 'is_micd', 'is_d_mic')
    search_fields = ('presenter__name', 'session__name', 'notes')
    list_editable = ('is_micd', 'is_d_mic')
    ordering = ['session__day__date', 'session__order', 'rf_number']
    
    fieldsets = (
        ('Assignment Details', {
            'fields': ('session', 'rf_number', 'mic_type')
        }),
        ('Presenter Information', {
            'fields': ('presenter', 'shared_presenters')
        }),
        ('Status', {
            'fields': ('is_micd', 'is_d_mic')
        }),
        ('Additional Info', {
            'fields': ('notes', 'modified_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(session__day__project=request.current_project)
        return qs.none()
    
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



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/mic_assignment_buttons.css',)
        }




class MicShowInfoAdmin(BaseEquipmentAdmin):
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
    
    class Media:
        css = {
            'all': ('admin/css/mic_show_info_buttons.css',)
        }
    



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)


# ===== ADD TO planner/urls.py (or create if doesn't exist) =====


from . import views

app_name = 'planner'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('mic-tracker/', views.mic_tracker_view, name='mic_tracker'),
    path('api/mic/update/', views.update_mic_assignment, name='update_mic_assignment'),
    path('api/mic/bulk-update/', views.bulk_update_mics, name='bulk_update_mics'),
    path('api/session/duplicate/', views.duplicate_session, name='duplicate_session'),
    path('api/day/toggle/', views.toggle_day_collapse, name='toggle_day_collapse'),
    path('mic-tracker/export/', views.export_mic_tracker, name='export_mic_tracker'),
]


#--------Power Estimator---------


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



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/amplifier_profile_buttons.css',)
        }


class AmplifierAssignmentInline(admin.TabularInline):
    model = AmplifierAssignment
    extra = 1
    can_delete = False  # Disable the checkbox
    fields = [
        'amplifier', 'quantity', 'zone', 'position', 
        'duty_cycle', 'phase_assignment', 
        'calculated_current_per_unit', 'calculated_total_current', 'delete_link'
    ]
    readonly_fields = ['calculated_current_per_unit', 'calculated_total_current', 'delete_link']
    autocomplete_fields = ['amplifier']

    def delete_link(self, obj):
        if obj.pk:
            url = reverse('admin:planner_amplifierassignment_delete', args=[obj.pk])
            return format_html(
                '<a href="{}" style="color: #ff6b6b; font-weight: bold;">Delete</a>',
                url
            )
        return "-"
    delete_link.short_description = "Delete"


# Update your PowerDistributionPlanAdmin class in planner/admin.py


class PowerDistributionPlanAdmin(BaseEquipmentAdmin):
    list_display = [
        'venue_name', 'service_type', 
        'available_amperage_per_leg', 'get_total_current', 'created_at', 'view_calculator_button',
    ]
    list_filter = ['service_type', 'created_at']
    search_fields = ['venue_name', 'notes']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Venue Information', {
            'fields': ('venue_name',)
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

    exclude = ['project', 'show_day']
    
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

    def get_queryset(self, request):
        """Filter by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)





    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)   

    class Media:
        css = {
            'all': ('admin/css/power_distribution_buttons.css',)
        } 



class AmplifierAssignmentAdmin(BaseEquipmentAdmin):
    list_display = [
        'distribution_plan', 'zone', 'amplifier', 'quantity', 
        'duty_cycle', 'phase_assignment', 'calculated_total_current'
    ]



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/amplifier_power_plan_buttons.css',)
    }


class AudioChecklistAdmin(BaseEquipmentAdmin):
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
    


    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    



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


class SoundvisionPredictionAdmin(BaseEquipmentAdmin):
    list_display = ['show_day', 'file_name', 'version', 'date_generated', 'created_at', 'array_summary', 'view_detail_link']
    list_filter = ['show_day', 'created_at', 'date_generated']
    search_fields = ['file_name', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'parsed_data_display']
    change_form_template = 'admin/planner/soundvisionprediction/change_form.html'

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


    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter show_day dropdown to current project only"""
        if db_field.name == "show_day":
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = ShowDay.objects.filter(project=request.current_project)
            else:
                kwargs["queryset"] = ShowDay.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
        
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
        """Auto-assign current project AND parse PDF if uploaded"""
        
        # Auto-assign project if new
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        
        # Save the object first
        super().save_model(request, obj, form, change)
        
        # Debug output
        print(f"DEBUG: pdf_file exists: {bool(obj.pdf_file)}")
        print(f"DEBUG: pdf_file in changed_data: {'pdf_file' in form.changed_data}")
        print(f"DEBUG: change value: {change}")
        print(f"DEBUG: Condition met: {obj.pdf_file and ('pdf_file' in form.changed_data or not change)}")
        
        # If a PDF file was uploaded, parse it
        if obj.pdf_file and ('pdf_file' in form.changed_data or not change):
            print("DEBUG: About to call parser...")
            try:
                from .soundvision_parser import import_soundvision_prediction
                print("DEBUG: Parser imported successfully")
                import_soundvision_prediction(obj, obj.pdf_file)
                print("DEBUG: Parser completed")
                messages.success(request, f'Successfully parsed {obj.file_name}')
            except Exception as e:
                print(f"DEBUG: Parser exception: {str(e)}")
                import traceback
                traceback.print_exc()
                messages.error(request, f'Error parsing PDF: {str(e)}')


    def get_queryset(self, request):
        """Filter by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()
    



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)   

    
     

    class Media:
        css = {
            'all': ('admin/css/soundvision_prediction_buttons.css',)
        }

class SpeakerArrayAdmin(BaseEquipmentAdmin):
    list_display = ['source_name', 'prediction', 'configuration','display_mbar_hole', 'display_weight', 
                   'display_trim', 'display_rigging', 'cabinet_count']
    list_filter = ['configuration', 'bumper_type', 'num_motors']
    search_fields = ['source_name', 'array_base_name']
    readonly_fields = ['bumper_angle', 'total_motor_load', 'trim_height', 'cabinet_summary']
    
    inlines = [SpeakerCabinetInline]
    
    def display_weight(self, obj):
        if obj.total_weight_lb:
            return format_html('<strong>{} lb</strong>', int(obj.total_weight_lb))
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

    def display_mbar_hole(self, obj):
        """Display MBar hole setting for KARA arrays"""
        if obj.mbar_hole:
            return format_html('<strong>Hole {}</strong>', obj.mbar_hole)
        return "-"
    display_mbar_hole.short_description = "MBar Hole"


    
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



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/speaker_array_buttons.css',)
        }


class SpeakerCabinetAdmin(BaseEquipmentAdmin):
    list_display = ['position_number', 'speaker_model', 'array', 'angle_to_next', 
                   'site_angle', 'panflex_setting']
    list_filter = ['speaker_model', 'panflex_setting']
    search_fields = ['array__source_name', 'speaker_model']
    ordering = ['array', 'position_number']   



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj) 
    

    class Media:
        css = {
            'all': ('admin/css/speaker_cabinet_buttons.css',)
        }




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








    


    # ==================== REGISTER ALL MODELS ====================
from planner.admin_site import showstack_admin_site

# Register all equipment admin classes
showstack_admin_site.register(Console, ConsoleAdmin)
showstack_admin_site.register(Device, DeviceAdmin)
showstack_admin_site.register(AmpModel, AmpModelAdmin)
showstack_admin_site.register(Amp, AmpAdmin)
showstack_admin_site.register(Location, LocationAdmin)
showstack_admin_site.register(SystemProcessor, SystemProcessorAdmin)
showstack_admin_site.register(P1Processor, P1ProcessorAdmin)
showstack_admin_site.register(GalaxyProcessor, GalaxyProcessorAdmin)
showstack_admin_site.register(PAZone, PAZoneAdmin)
showstack_admin_site.register(PACableSchedule, PACableAdmin)  
showstack_admin_site.register(CommChannel, CommChannelAdmin)
showstack_admin_site.register(CommPosition, CommPositionAdmin)
showstack_admin_site.register(CommCrewName, CommCrewNameAdmin)
showstack_admin_site.register(CommBeltPack, CommBeltPackAdmin)
showstack_admin_site.register(ShowDay, ShowDayAdmin)
showstack_admin_site.register(Presenter, PresenterAdmin)
showstack_admin_site.register(MicSession, MicSessionAdmin)
showstack_admin_site.register(MicAssignment, MicAssignmentAdmin)
showstack_admin_site.register(MicShowInfo, MicShowInfoAdmin)
showstack_admin_site.register(AmplifierProfile, AmplifierProfileAdmin)
showstack_admin_site.register(PowerDistributionPlan, PowerDistributionPlanAdmin)
showstack_admin_site.register(AmplifierAssignment, AmplifierAssignmentAdmin)
showstack_admin_site.register(AudioChecklist, AudioChecklistAdmin)  
showstack_admin_site.register(SoundvisionPrediction, SoundvisionPredictionAdmin)
showstack_admin_site.register(SpeakerArray, SpeakerArrayAdmin)
showstack_admin_site.register(SpeakerCabinet, SpeakerCabinetAdmin)