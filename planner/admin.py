# At the TOP of admin.py, organize all imports together (lines 1-25):

# Django imports
from django.contrib.contenttypes.models import ContentType
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse, path
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.shortcuts import render, redirect  
from django.contrib.admin.views.decorators import staff_member_required  
from django.views.decorators.http import require_POST  
from django import forms
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Max
from .models import AmplifierProfile, PowerDistributionPlan, AmplifierAssignment
from django.db.models import Sum 
from .models import SoundvisionPrediction, SpeakerArray, SpeakerCabinet
from django.contrib.admin import AdminSite
from . import admin_ordering
from .models import ConsoleStereoOutput
from .models import MonitorSession, DiscoveredDevice, PollResult, DeviceEvent, ProjectSNMPConfig, SwitchPortSnapshot
from django.urls import path

# Python standard library imports
import csv
import math
import json  
from datetime import datetime, timedelta  

from planner.models import Project, ProjectMember
from planner.utils import pa_cable_math
from django.db import models

# Model imports (add the mic tracking models to your existing model imports)
from .models import Device, DeviceInput, DeviceOutput
from .models import Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput, SourceHardwareOption
from .models import ConsoleImport
from .models import MultitrackSession, MultitrackTrack
from .models import MultitrackTemplate, MultitrackTemplateSlot
from .models import SignalFlowDiagram
from .models import Location, AmpLocation, Amp, AmpChannel, AmpDivider, AMP_PRESET_SUGGESTIONS
from .models import SystemProcessor, P1Processor, P1Input, P1Output
from .models import GalaxyProcessor, GalaxyInput, GalaxyOutput
from .models import ShowDay, MicSession, MicAssignment, MicShowInfo, MicGroup
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


from django.db.models import Max, Count
from .models import CommBeltPack, CommBeltPackChannel

from .models import DanteConsoleConfig, DanteDeviceConfig, DanteSubscription







class BaseAdmin(admin.ModelAdmin):
    """Common base for ShowStack ModelAdmins.

    This used to pull in `css/dark-admin.css` on every admin page. That file
    was committed empty in March 2026 as a placeholder to silence a 404 and
    never held a rule; the dark theme lives in planner/static/css/surfaces.css
    and templates/admin/base_site.html. With hashed static files an empty
    stylesheet is still a request per page, so the reference is gone.
    """


class BaseEquipmentAdmin(BaseAdmin):
    """Base admin for equipment models with project filtering and role-based permissions"""


    def _get_user_role_for_project(self, request, project):
        """Get user's role for a specific project (returns 'owner', 'editor', 'viewer', or None)"""
        if project is None:
            return None
        if project.owner == request.user:
            return 'owner'
        
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
    

    # ------------------------------------------------------------------
    # Project-scoped dropdowns
    # ------------------------------------------------------------------
    # A relation field left out of this map renders Django's default
    # queryset: the whole table. That is correct for the global hardware
    # catalogues (AmpModel, CommDeviceModel) and wrong for everything else,
    # and eleven admins were silently relying on the default -- offering
    # other tenants' consoles, processors, sessions, predictions and devices
    # in their dropdowns. A dropdown is a read surface: whatever is
    # selectable is also visible.
    #
    # Keys are field names on this model; values are the ORM path from the
    # *related* model to its Project.
    project_scoped_fks = {}

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Narrow any field named in `project_scoped_fks` to the current project.

        Subclasses that override this for one specific field should call
        `super()` (they all do) so the declarative map still applies to the
        rest.
        """
        scoped = getattr(self, 'project_scoped_fks', None) or {}
        if db_field.name in scoped and 'queryset' not in kwargs:
            related_project_path = scoped[db_field.name]
            current_project = getattr(request, 'current_project', None)
            base = db_field.remote_field.model._default_manager.all()
            kwargs['queryset'] = (
                base.filter(**{related_project_path: current_project})
                if current_project else base.none()
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
        
        # Map child models to the ORM path from them to their project.
        #
        # A model that is neither keyed here nor carrying a direct `project`
        # field falls through to `qs.filter(project_id=...)` below and raises
        # FieldError -- an HTTP 500 on that changelist, which is how
        # MultitrackTemplate, ConsoleImport and MicGroup were broken. Adding a
        # model to the admin means adding it here; see `MODELS_WITHOUT_PROJECT`
        # for the one deliberate exception.
        child_model_paths = {
            'PAFanOut': 'cable_schedule__project_id',
            'MicSession': 'day__project_id',
            'MicAssignment': 'session__day__project_id',
            'MicGroup': 'session__day__project_id',
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
            'ConsoleImport': 'console__project_id',
            # Network Health Monitor children reach their project via device.
            'PollResult': 'device__project_id',
            'DeviceEvent': 'device__project_id',
            'SwitchPortSnapshot': 'device__project_id',
        }

        # Models with no project at all, scoped by their owner instead.
        # MultitrackTemplate is a personal template library keyed on
        # created_by, so "the current project" is not the right question for
        # it -- but "anyone's templates" is definitely the wrong answer, which
        # is what the FieldError-ing fall-through used to produce once the
        # crash was fixed naively.
        owner_scoped_paths = {
            'MultitrackTemplate': 'created_by',
        }

        # Get the model name
        model_name = self.model.__name__

        # If this is a child model, filter through parent
        if model_name in child_model_paths:
            filter_path = child_model_paths[model_name]
            filter_kwargs = {filter_path: current_project_id}
            return qs.filter(**filter_kwargs)

        if model_name in owner_scoped_paths:
            if request.user.is_superuser:
                return qs
            return qs.filter(**{owner_scoped_paths[model_name]: request.user})

        # Otherwise, filter directly by project_id -- but only if the model
        # actually has one. It used to filter unconditionally, so a model that
        # was neither keyed above nor carrying `project` raised FieldError and
        # 500ed its changelist. Returning none() instead keeps a forgotten
        # registration fail-closed rather than either crashing or, worse,
        # showing everything.
        if any(f.name == 'project' for f in self.model._meta.get_fields()):
            return qs.filter(project_id=current_project_id)
        return qs.none()


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
        if obj.__class__.__name__ == 'Project':
            project = obj
        elif obj.__class__.__name__ == 'MicSession':
            project = obj.day.project
        else:
            project = obj.project
        role = self._get_user_role_for_project(request, project)
        return role in ['owner', 'editor']  # Viewers can't edit
    
    def has_delete_permission(self, request, obj=None):
        """Allow delete if user is owner or editor (NOT viewer)"""
        if request.user.is_superuser:
            return True
        
        if obj is None:
            return (
                self._is_premium_owner(request) or 
                self._user_has_editor_access(request) or
                ProjectMember.objects.filter(user=request.user, role='owner').exists()
            )
        
        # Check specific object permission
        if obj.__class__.__name__ == 'Project':
            project = obj
        elif obj.__class__.__name__ == 'MicSession':
            project = obj.day.project
        elif obj.__class__.__name__ == 'MicAssignment':
            project = obj.session.day.project
        elif obj.__class__.__name__ == 'MicGroup':
            project = obj.session.day.project
        elif hasattr(obj, 'project'):
            project = obj.project
        elif hasattr(obj, 'array'):  # SpeakerCabinet
            project = obj.array.prediction.project
        elif hasattr(obj, 'prediction'):  # SpeakerArray
            project = obj.prediction.project
        else:
            project = None

        role = self._get_user_role_for_project(request, project)
        return role in ['owner', 'editor']
    


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
                import traceback
                tb = traceback.format_exc()
                print(f"DUPLICATE ERROR: {tb}")
                modeladmin.message_user(
                    request,
                    f'Error duplicating project: {str(e)} | Line: {tb.splitlines()[-3]}',
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


def project_scoped_filter(title, parameter_name, related_model,
                          related_project_path='project', label=str,
                          queryset_path=None, ordering='name'):
    """Build a ``list_filter`` entry that only lists the current project's rows.

    A bare relation in ``list_filter`` -- ``list_filter = ['location']`` --
    gets Django's ``RelatedFieldListFilter``, and that calls
    ``field.get_choices()``
    (django/contrib/admin/filters.py:271-273), which reads the **entire**
    related table. It does not consult the ModelAdmin's ``get_queryset``, so a
    correctly scoped changelist still rendered every other tenant's location
    names, show-day names and project names down the filter rail -- names, on
    pages users legitimately have.

    Issue #21 fixed this once by hand for the Amp changelist
    (``AmpLocationFilter``). Nine other admins had the same entry and were
    missed, which is the argument for a factory rather than a tenth copy.

    Arguments:
        title: sidebar heading.
        parameter_name: query-string key, conventionally the field path.
        related_model: model whose rows become the options.
        related_project_path: ORM path from ``related_model`` to its Project.
        label: option text from an instance; defaults to ``str``.
        queryset_path: ORM path from the *filtered* model to ``related_model``
            when it differs from ``parameter_name`` (e.g. a nested path).
        ordering: field to order the options by.
    """
    _filter_path = (queryset_path or parameter_name)

    class _ProjectScopedFilter(admin.SimpleListFilter):
        pass

    _ProjectScopedFilter.title = title
    _ProjectScopedFilter.parameter_name = parameter_name

    def lookups(self, request, model_admin):
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return []
        rows = related_model.objects.filter(
            **{related_project_path: current_project}
        ).order_by(ordering)
        return [(row.pk, label(row)) for row in rows]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        # The option ids came from the scoped lookups above, but a
        # hand-typed query string can name anything -- so re-scope here too
        # rather than trusting the parameter.
        allowed = related_model.objects.filter(
            **{related_project_path: getattr(request, 'current_project', None)}
        ).values_list('pk', flat=True)
        try:
            value = int(value)
        except (TypeError, ValueError):
            return queryset.none()
        if value not in set(allowed):
            return queryset.none()
        return queryset.filter(**{f'{_filter_path}_id': value})

    _ProjectScopedFilter.lookups = lookups
    _ProjectScopedFilter.queryset = queryset
    _ProjectScopedFilter.__name__ = f'ProjectScoped_{parameter_name}_Filter'
    return _ProjectScopedFilter


@admin.register(Project, site=showstack_admin_site)
class ProjectAdmin(admin.ModelAdmin):
    """Admin for Project model - doesn't use BaseEquipmentAdmin filtering"""
    list_display = ['name', 'owner', 'start_date', 'end_date', 'venue', 'is_archived']
    list_filter = ['is_archived', 'start_date', 'end_date']
    search_fields = ['name', 'venue', 'client']
    actions = [duplicate_project_action]
    readonly_fields = ['owner', 'created_at', 'updated_at','invite_link']  
    exclude = []  # We'll set this dynamically


    def invite_link(self, obj):
        from django.urls import reverse
        url = f"/projects/request/{obj.invite_token}/"
        full_url = f"https://showstack-production.up.railway.app{url}"
        return mark_safe(f'<input type="text" value="{full_url}" readonly style="width:420px;padding:4px 8px;background:#111;color:#fff;border:1px solid #444;border-radius:4px;margin-right:8px;" /> <button onclick="navigator.clipboard.writeText(\'{full_url}\');this.textContent=\'Copied!\';setTimeout(()=>this.textContent=\'Copy\',2000);return false;" style="padding:4px 10px;background:#4a9eff;color:white;border:none;border-radius:4px;cursor:pointer;">Copy</button>')
    invite_link.short_description = "Shareable Access Request Link"

    def access_request_count(self, obj):
        count = obj.access_requests.filter(status='pending').count()
        if count:
            url = f"/projects/{obj.id}/requests/"
            return mark_safe(f'<a href="{url}" style="color:#ffaa44;">{count} pending</a>')
        return "0"
    access_request_count.short_description = "Access Requests"
    
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
        ('Access & Sharing', {
            'fields': ('invite_link',),
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
        from django.db.models import Case, When, IntegerField, Value
        from django.db.models.functions import Cast
        # Safe cast - non-numeric input_ch values sort to end
        return qs.annotate(
            input_ch_int=Case(
                When(input_ch__regex=r'^\d+$',
                     then=Cast('input_ch', IntegerField())),
                default=Value(99999),
                output_field=IntegerField()
            )
        ).order_by('input_ch_int', 'input_ch')

    def get_extra(self, request, obj=None, **kwargs):
        """Return 144 for new consoles, 0 for existing"""
        if obj is None:  # Creating new console
            return 144
        return 0  # Editing existing console

    

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        from planner.models import SourceHardwareOption

        class PrepopulatedFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                source_hardware_options = list(
                    SourceHardwareOption.objects.values_list('label', flat=True)
                )
                base_choices = [(o, o) for o in source_hardware_options]

                for form in self.forms:
                    for field in form.fields.values():
                        field.required = False

                    for hw_field in ('source_hardware', 'source_hardware_b'):
                        if hw_field not in form.fields:
                            continue
                        current = getattr(form.instance, hw_field) if form.instance.pk else None
                        choices = list(base_choices)
                        if current and current not in source_hardware_options:
                            choices.append((current, current))
                        form.fields[hw_field].choices = (
                            [('', '---------')]
                            + choices
                            + [('__add_new__', '+ Add new…')]
                        )

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


class DanteConsoleConfigInline(admin.StackedInline):
    model = DanteConsoleConfig
    extra = 0
    max_num = 1
    can_delete = True
    verbose_name = "Dante Configuration"
    verbose_name_plural = "Dante Configuration"
    fields = ['dante_name', 'sample_rate', 'encoding', 'tx_channel_count', 'rx_channel_count', 'tx_channel_labels', 'rx_channel_labels', 'is_clock_master', 'clock_subdomain']

class DanteDeviceConfigInline(admin.StackedInline):
    model = DanteDeviceConfig
    extra = 0
    max_num = 1
    can_delete = True
    verbose_name = "Dante Configuration"
    verbose_name_plural = "Dante Configuration"
    fields = ['dante_name', 'sample_rate', 'encoding', 'tx_channel_count', 'rx_channel_count', 'tx_channel_labels', 'rx_channel_labels', 'is_clock_master', 'clock_subdomain']
    


class ConsoleAdmin(BaseEquipmentAdmin):
    # "Is template" is deliberately absent from both of these. Templates are
    # managed in the Console Template Library (/console-template-library/),
    # which is what the toolbar button beside Add Console opens, so the column
    # restated a fact the list has somewhere better to say. It was not free:
    # 68px of a table that has to fit its columns into the 628px a 1280
    # viewport leaves once both sidebars are open -- see the column budget in
    # admin/css/console_list_buttons.css.
    #
    # Nothing about the flag itself changes. It is still on the add/change
    # form, Console.Meta.ordering still lists templates first, and template
    # consoles still appear in this list -- they simply no longer carry a
    # marker here. ConsoleAdmin.name_with_template_badge is still defined and
    # unused if that marker is ever wanted back in the Name column.
    list_display = ['name', 'location', 'primary_ip_address', 'secondary_ip_address', 'export_buttons']
    list_filter = [project_scoped_filter('Location', 'location', Location)]
    
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

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Show the console's name as the page header instead of the generic
        'Change console' title."""
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj is not None:
            extra_context['title'] = str(obj)
            extra_context['subtitle'] = None
        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)
    
    def name_with_template_badge(self, obj):
        if obj.is_template:
            return format_html('<strong>📋 {}</strong>', obj.name)
        return obj.name
    name_with_template_badge.short_description = 'Name'
    name_with_template_badge.admin_order_field = 'name'


    def export_buttons(self, obj):
        """The two per-console exports, as one row of buttons that cannot wrap.

        Styling is by class, not by `style=`. The inline colours these two
        used to carry (#4a9eff and #2a9d8f) never reached the page:
        base_site.html paints `.button` #417690 with !important, and an
        !important declaration outranks a plain inline style, so both
        buttons rendered in the steel blue the rest of the admin is moving
        away from. They now take the shared secondary-button tokens from
        css/surfaces.css, sized for a table cell.

        .ss-btn-row is what holds them on one line -- in a 108px column
        "Yamaha CSV" wrapped inside its own button. The column is given
        room for the pair in admin/css/console_list_buttons.css.
        """
        pdf_url = reverse('planner:console_pdf_export', args=[obj.id])

        # Left as a literal path rather than reverse()d: this ModelAdmin is
        # registered on ShowStackAdminSite, so the route's namespace is not
        # simply "admin". This is the path get_urls() builds, unchanged.
        yamaha_url = f'/admin/planner/console/{obj.pk}/export-yamaha/'

        return format_html(
            '<span class="ss-btn-row">'
            '<a class="ss-btn ss-btn--secondary ss-btn--compact" '
            'href="{}" target="_blank">📄 PDF</a>'
            '<a class="ss-btn ss-btn--secondary ss-btn--compact" '
            'href="{}" target="_blank">📊 Yamaha CSV</a>'
            '</span>',
            pdf_url,
            yamaha_url,
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
            # The destination is request.current_project, so importing is a
            # WRITE to it. CurrentProjectMiddleware only proves the user may
            # *reach* that project -- a viewer-role member passes it -- so the
            # per-project edit role is checked separately. _can_edit_current_project
            # deliberately ignores the global 'Viewer' Django group; see its
            # docstring for why. Imported locally to match how this file already
            # defers its `views` import to the bottom of the module.
            from planner.views import _can_edit_current_project
            if not _can_edit_current_project(request):
                messages.error(
                    request,
                    "You have read-only access to this project, so you cannot "
                    "import a template into it.",
                )
                return redirect('admin:console_template_library')

            template_id = request.POST.get('template_id')
            if template_id:
                try:
                    # Scoped to the caller's OWN projects, matching the GET
                    # listing below. Unscoped, this was an IDOR: the id came
                    # straight from the form body and the only other condition
                    # was is_template, so any logged-in user could POST any
                    # other tenant's template id and copy that console -- every
                    # input, its source names and its IPs -- into their own
                    # project. The response even named the victim's project, via
                    # the "(from {project.name})" suffix below.
                    #
                    # Superusers are exempt so support can still copy a
                    # template between tenants by id; everyone else is held to
                    # the same set the GET lists.
                    if request.user.is_superuser:
                        source_projects = Project.objects.all()
                    else:
                        source_projects = Project.objects.filter(owner=request.user)
                    original = Console.objects.get(
                        id=template_id,
                        is_template=True,
                        project__in=source_projects,
                    )

                    # `project__in` above cannot match a NULL project, so
                    # original.project is non-null from here. It used to be
                    # reachable with project=None, and this next line was then
                    # an AttributeError -> HTTP 500.
                    #
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
        # Scope to projects the current user OWNS only (issue #4).
        # Member-only access to someone else's project does not surface their
        # templates here; only the project owner's own templates are visible.
        owned_projects = Project.objects.filter(owner=request.user)
        all_templates = Console.objects.filter(is_template=True, project__in=owned_projects).select_related('project').annotate(
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
        # reverse() rather than the literal '/console-template-library/' this
        # used to carry: the library now lives on this ModelAdmin (see
        # get_urls), and the old root path is only kept as a redirect for
        # bookmarks. Reversing means the button follows the route rather than
        # depending on that redirect staying.
        extra_context['template_library_url'] = reverse(
            'admin:console_template_library'
        )
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
            # The Template Library used to be routed from audiopatch/urls.py by a
            # lambda that built a ConsoleAdmin by hand and called this method
            # directly. That route had no `admin_view()` wrapper, so the view's
            # only gate was the global LoginRequiredMiddleware -- no staff check,
            # no permission check of its own -- and it was built against
            # `admin.site` rather than this site, so the three
            # `redirect('admin:console_template_library')` calls inside it raised
            # NoReverseMatch: the name was registered in the ROOT urlconf with no
            # namespace, and nothing answered to `admin:`.
            #
            # Registering it here fixes both at once. `admin_view` applies the
            # staff gate, and the name now resolves under the `admin:` namespace,
            # which is what those redirects already asked for.
            path('template-library/',
                 self.admin_site.admin_view(self.console_template_library_view),
                 name='console_template_library'),
        ]
        return custom_urls + urls
    
    def export_yamaha_view(self, request, pk):
        """View to handle Yamaha CSV export"""
        from .utils.yamaha_export import export_yamaha_csvs
        console = Console.objects.get(pk=pk)
        return export_yamaha_csvs(console)
    
    class Media:
        js = ['planner/js/mono_stereo_handler.js',
            'planner/js/global_nav.js',
            'admin/js/console_autofill.js',
            'admin/js/console_source_hardware.js',
            'admin/js/console_ab_toggle.js',]
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
        """Consoles in the current project only.

        There were two methods with this name here: an empty stub (returning
        None) and this one. Python keeps the last, so the stub was dead --
        harmless by luck rather than design, which is the same hazard as the
        duplicated formfield_for_foreignkey in AmpAdmin.

        The four debug prints this used to carry are gone too. One of them ran
        `qs.count()` on the *unfiltered* queryset purely to log "Total
        consoles: N" -- an extra query per render whose only output was a
        cross-tenant total in the server log.
        """
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(project=request.current_project)
        return qs.none()  # No project selected = show nothing
    

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
        if obj is None:
            return ['name', 'location', 'primary_ip_address', 'secondary_ip_address', 'input_count', 'output_count']
        return ['name', 'location', 'primary_ip_address', 'secondary_ip_address']
    
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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
            'fields': ('nl4_connector_count', 'nl8_connector_count', 'cacom_output_count','sc32_connector_count'),
            'classes': ('collapse',)
        }),
    )



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)


class AmpChannelInlineForm(forms.ModelForm):
    class Meta:
        model = AmpChannel
        fields = '__all__'


           
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.amp_id and self.instance.amp.amp_model_id:
            # An amp with no model yet has no capabilities to read, so
            # every input field stays visible rather than crashing the
            # inline. planner/forms.py's copy of this form already
            # guarded it; this one did not.
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


class AmpPresetInput(forms.TextInput):
    """Issue #26: text input backed by a <datalist> of common L-Acoustics
    presets. Users can either pick a suggestion or type anything custom."""

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html, format_html_join
        list_id = f'id_{name}_datalist'
        attrs = dict(attrs or {})
        attrs['list'] = list_id
        attrs.setdefault('autocomplete', 'off')
        input_html = super().render(name, value, attrs, renderer)
        options_html = format_html_join(
            '', '<option value="{}"></option>',
            ((p,) for p in AMP_PRESET_SUGGESTIONS),
        )
        return format_html(
            '{}<datalist id="{}">{}</datalist>',
            input_html, list_id, options_html,
        )


class AmpAdminForm(forms.ModelForm):
    class Meta:
        model = Amp
        fields = '__all__'
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color', 'value': '#FFFFFF'}),
            'preset': AmpPresetInput(attrs={'class': 'vTextField'}),
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

                # Hide SC32 fields if amp doesn't have SC32 connector
                if not hasattr(amp_model, 'sc32_connector_count') or amp_model.sc32_connector_count == 0:
                    for field in ['sc32_ch1', 'sc32_ch2', 'sc32_ch3', 'sc32_ch4',
                                  'sc32_ch5', 'sc32_ch6', 'sc32_ch7', 'sc32_ch8',
                                  'sc32_ch9', 'sc32_ch10', 'sc32_ch11', 'sc32_ch12',
                                  'sc32_ch13', 'sc32_ch14', 'sc32_ch15', 'sc32_ch16']:
                        if field in self.fields:
                            self.fields[field].widget = forms.HiddenInput()            
                    
            except (ValueError, AmpModel.DoesNotExist):
                pass



class AmpLocationFilter(admin.SimpleListFilter):
    """Project-scoped 'By location' filter on the Amp changelist (#21).

    The default ``list_filter = ('location', ...)`` used Django's
    RelatedFieldListFilter, which queries every Location row regardless of
    the current project — a multi-tenancy leak. This scopes the dropdown to
    locations belonging to ``request.current_project`` only.
    """
    title = 'Location'
    parameter_name = 'location'

    def lookups(self, request, model_admin):
        current_project = getattr(request, 'current_project', None)
        if current_project:
            locations = AmpLocation.objects.filter(project=current_project).order_by('name')
            return [(loc.id, loc.name) for loc in locations]
        return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(location_id=self.value())
        return queryset


class AmpAdmin(BaseEquipmentAdmin):
    form = AmpAdminForm
    list_display = ('name', 'location', 'amp_model', 'ip_address', 'color_preview')
    list_filter = (AmpLocationFilter, 'amp_model__manufacturer', 'amp_model__model_name')
    search_fields = ('name', 'ip_address')
    ordering = ['location', 'name']
    actions = ['assign_color_to_amps']
    # Issue #27: rack view is the new edit page — replaces the old changelist.
    change_list_template = 'admin/planner/amp/rack_view.html'

    class Media:
        css = {
            'all': ('admin/css/amp_list_buttons.css',)
        }
        js = ()



    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        
        # Handle AJAX location requests
        if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            import json
            action = request.POST.get('action')
            
            if action == 'add_location':
                name = request.POST.get('name', '').strip()
                if name and hasattr(request, 'current_project') and request.current_project:
                    # Get max sort_order
                    max_order = AmpLocation.objects.filter(
                        project=request.current_project
                    ).aggregate(models.Max('sort_order'))['sort_order__max'] or 0
                    loc = AmpLocation.objects.create(
                        name=name,
                        project=request.current_project,
                        sort_order=max_order + 1
                    )
                    from django.http import JsonResponse
                    return JsonResponse({'success': True, 'id': loc.id, 'name': loc.name})
                from django.http import JsonResponse
                return JsonResponse({'success': False, 'error': 'Invalid name or no project'})

            elif action == 'rename_location':
                loc_id = request.POST.get('id')
                name = request.POST.get('name', '').strip()
                if loc_id and name:
                    try:
                        loc = AmpLocation.objects.get(
                            id=loc_id,
                            project=request.current_project
                        )
                        loc.name = name
                        loc.save()
                        from django.http import JsonResponse
                        return JsonResponse({'success': True})
                    except AmpLocation.DoesNotExist:
                        pass
                from django.http import JsonResponse
                return JsonResponse({'success': False})

            elif action == 'delete_location':
                # Issue #27: the previous handler tried to NULL out amps'
                # location FK before delete, but Amp.location is NOT NULL —
                # the IntegrityError surfaced to the user as a silent failure.
                # Refuse the delete if amps still live there and tell the
                # client what to do.
                from django.http import JsonResponse
                loc_id = request.POST.get('id')
                if not loc_id:
                    return JsonResponse({'success': False, 'error': 'Missing id'})
                try:
                    loc = AmpLocation.objects.get(
                        id=loc_id,
                        project=request.current_project,
                    )
                except AmpLocation.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Not found'})
                amp_count = Amp.objects.filter(location=loc).count()
                if amp_count:
                    return JsonResponse({
                        'success': False,
                        'error': (
                            f'"{loc.name}" still has {amp_count} amp'
                            f'{"s" if amp_count != 1 else ""}. '
                            'Move or delete the amps before deleting the location.'
                        ),
                    })
                # Clean up any dividers anchored to this empty location.
                AmpDivider.objects.filter(location=loc).delete()
                loc.delete()
                return JsonResponse({'success': True})
            
            elif action == 'reorder_amp':
                # Issue #18: swap an amp's sort_order with an adjacent amp in
                # the same location. The template's JS passes both IDs so we
                # don't have to re-derive the visual order here — that keeps
                # the swap correct even when many existing rows still share
                # sort_order=0 from before this change.
                amp_id = request.POST.get('id')
                other_id = request.POST.get('other_id')
                from django.http import JsonResponse
                if amp_id and other_id and hasattr(request, 'current_project') and request.current_project:
                    try:
                        amp = Amp.objects.get(id=amp_id, project=request.current_project)
                        other = Amp.objects.get(id=other_id, project=request.current_project)
                        if amp.location_id == other.location_id:
                            amp.sort_order, other.sort_order = other.sort_order, amp.sort_order
                            if amp.sort_order == other.sort_order:
                                other.sort_order = amp.sort_order + 1
                            amp.save(update_fields=['sort_order'])
                            other.save(update_fields=['sort_order'])
                            return JsonResponse({'success': True})
                    except Amp.DoesNotExist:
                        pass
                return JsonResponse({'success': False})

            elif action == 'set_amp_order':
                # Issue #18: persist the order from a header-click sort. The
                # JS sorts client-side (it knows how to compare IPs by octet)
                # and sends back the new ordered list of IDs for one location.
                ids_raw = request.POST.get('ids', '')
                from django.http import JsonResponse
                try:
                    id_list = [int(x) for x in ids_raw.split(',') if x]
                except ValueError:
                    id_list = []
                if id_list and hasattr(request, 'current_project') and request.current_project:
                    amps = list(Amp.objects.filter(
                        id__in=id_list,
                        project=request.current_project,
                    ))
                    if len(amps) == len(id_list) and len({a.location_id for a in amps}) == 1:
                        amp_map = {a.id: a for a in amps}
                        for i, amp_id in enumerate(id_list):
                            amp = amp_map[amp_id]
                            amp.sort_order = i + 1
                            amp.save(update_fields=['sort_order'])
                        return JsonResponse({'success': True})
                return JsonResponse({'success': False})

            elif action == 'reorder_location':
                loc_id = request.POST.get('id')
                direction = request.POST.get('direction')
                if loc_id and direction:
                    try:
                        loc = AmpLocation.objects.get(
                            id=loc_id,
                            project=request.current_project
                        )
                        locations = list(AmpLocation.objects.filter(
                            project=request.current_project
                        ).order_by('sort_order', 'name'))
                        idx = next((i for i, l in enumerate(locations) if l.id == loc.id), None)
                        if idx is not None:
                            if direction == 'up' and idx > 0:
                                swap = locations[idx - 1]
                                loc.sort_order, swap.sort_order = swap.sort_order, loc.sort_order
                                # Ensure they differ
                                if loc.sort_order == swap.sort_order:
                                    loc.sort_order = swap.sort_order - 1
                                loc.save()
                                swap.save()
                            elif direction == 'down' and idx < len(locations) - 1:
                                swap = locations[idx + 1]
                                loc.sort_order, swap.sort_order = swap.sort_order, loc.sort_order
                                if loc.sort_order == swap.sort_order:
                                    loc.sort_order = swap.sort_order + 1
                                loc.save()
                                swap.save()
                        from django.http import JsonResponse
                        return JsonResponse({'success': True})
                    except AmpLocation.DoesNotExist:
                        pass
                from django.http import JsonResponse
                return JsonResponse({'success': False})
        
        # Build grouped data for template
        if hasattr(request, 'current_project') and request.current_project:
            from django.db.models import Count
            locations = AmpLocation.objects.filter(
                project=request.current_project
            ).annotate(
                amp_count=Count('amps')
            ).order_by('sort_order', 'name')
            
            active_locations = []
            for loc in locations:
                amps = list(
                    Amp.objects.filter(location=loc, project=request.current_project)
                    .select_related('amp_model')
                    .prefetch_related('channels')
                    .order_by('sort_order', 'name')
                )
                dividers = list(
                    AmpDivider.objects.filter(location=loc, project=request.current_project)
                    .order_by('sort_order')
                )
                # Issue #27: build per-card data so the unified rack template
                # can render every amp's front-panel fields inline.
                cards = []
                for amp in amps:
                    channels = sorted(amp.channels.all(), key=lambda c: c.channel_number)
                    model = amp.amp_model
                    # An LA12X renders 16 AVB rows whether 1 or 16 are patched,
                    # so an 18-amp location scrolled for pages of "None". Flag
                    # the empty ones and let the template fold them behind a
                    # "+ N unused" toggle.
                    #
                    # A row carries both the AVB stream and the Analogue Input
                    # Label, so "unused" has to mean both are empty -- keying
                    # off avb_stream alone would hide analogue labels that are
                    # filled in.
                    avb_unused_count = 0
                    for ch in channels:
                        ch.avb_unused = not (
                            (ch.avb_stream or '').strip()
                            or (ch.analog_input or '').strip()
                        )
                        if ch.avb_unused:
                            avb_unused_count += 1
                    # Issue #31: NL4 Out block now renders as four generic
                    # numbered rows from Amp.output_1..output_4 (matches the
                    # original spreadsheet). CaCom Out keeps its model-driven
                    # per-channel rendering as before.
                    nl4_rows = [
                        {'label': str(n), 'field': f'output_{n}', 'value': getattr(amp, f'output_{n}', '')}
                        for n in (1, 2, 3, 4)
                    ]
                    cacom_rows = []
                    if model and model.cacom_output_count:
                        for ci in range(1, min(model.cacom_output_count + 1, 5)):
                            base = (ci - 1) * 4
                            for n in range(1, 5):
                                cacom_rows.append({
                                    'ch': base + n,
                                    'field': f'cacom_{ci}_ch{n}',
                                    'value': getattr(amp, f'cacom_{ci}_ch{n}', ''),
                                })
                    # Issue #41: LA7.16i and similar amps expose 16 outs over a
                    # single SC32 connector; render those as their own block
                    # instead of the generic four-output NL4 block.
                    sc32_rows = []
                    sc32_count = getattr(model, 'sc32_connector_count', 0) if model else 0
                    if sc32_count:
                        for n in range(1, 17):
                            sc32_rows.append({
                                'ch': n,
                                'field': f'sc32_ch{n}',
                                'value': getattr(amp, f'sc32_ch{n}', ''),
                            })
                    has_nl4 = bool(model and model.nl4_connector_count)
                    cards.append({
                        'amp': amp,
                        'channels': channels,
                        'nl4_rows': nl4_rows,
                        'cacom_rows': cacom_rows,
                        'sc32_rows': sc32_rows,
                        'has_nl4': has_nl4,
                        'avb_unused_count': avb_unused_count,
                    })
                # Items list — for divider rendering anchored to amp index.
                items_order = []
                divs_at = {}
                for d in dividers:
                    divs_at.setdefault(d.sort_order, []).append(d)
                for after_idx in sorted(k for k in divs_at if k < 0):
                    for d in divs_at[after_idx]:
                        items_order.append({'type': 'divider', 'obj': d})
                for idx, card in enumerate(cards):
                    items_order.append({'type': 'card', 'card': card})
                    for d in divs_at.get(idx, []):
                        items_order.append({'type': 'divider', 'obj': d})
                last_idx = len(cards) - 1
                for after_idx in sorted(k for k in divs_at if k > last_idx):
                    for d in divs_at[after_idx]:
                        items_order.append({'type': 'divider', 'obj': d})

                active_locations.append({
                    'location': loc,
                    'amps': amps,
                    'cards': cards,
                    'items': items_order,
                    'amp_count': len(amps),
                })

            all_locations = list(locations)
            from .models import AmpModel, P1Output, GalaxyOutput
            extra_context['grouped_amps'] = active_locations
            extra_context['all_locations'] = all_locations
            extra_context['all_amp_models'] = list(
                AmpModel.objects.all().order_by('manufacturer', 'model_name')
            )
            extra_context['has_grouped_layout'] = True

            # Issue #43: surface processor output labels as datalist
            # suggestions on the amp's Analogue / AES / AVB input fields.
            # Unlabeled outputs are skipped; entries get a "(<processor>)"
            # suffix only when two processors expose the same label at the
            # same slot, so a single-processor setup stays terse.
            from collections import defaultdict

            p1_outs = P1Output.objects.filter(
                p1_processor__system_processor__project=request.current_project
            ).select_related('p1_processor__system_processor')
            gal_outs = GalaxyOutput.objects.filter(
                galaxy_processor__system_processor__project=request.current_project
            ).select_related('galaxy_processor__system_processor')

            tagged = []  # (output_type, channel_number, label, processor_name)
            for o in p1_outs:
                label = (o.label or '').strip()
                if not label:
                    continue
                tagged.append((
                    o.output_type, o.channel_number, label,
                    o.p1_processor.system_processor.name,
                ))
            for o in gal_outs:
                label = (o.label or '').strip()
                if not label:
                    continue
                tagged.append((
                    o.output_type, o.channel_number, label,
                    o.galaxy_processor.system_processor.name,
                ))

            def _build_simple(kind):
                # by_label[label] -> set of processor names
                by_label = defaultdict(set)
                for t, _ch, lbl, proc in tagged:
                    if t == kind:
                        by_label[lbl].add(proc)
                out = []
                for lbl, procs in by_label.items():
                    if len(procs) == 1:
                        out.append(lbl)
                    else:
                        for proc in procs:
                            out.append(f'{lbl} ({proc})')
                return sorted(out)

            def _build_avb():
                # Group by (channel_number, label) so two processors that
                # emit the same labeled stream collapse, and only ambiguous
                # ones grow the "(proc)" suffix.
                by_slot = defaultdict(set)
                for t, ch, lbl, proc in tagged:
                    if t == 'AVB':
                        by_slot[(ch, lbl)].add(proc)
                rows = []  # (channel_number, display_string) so sort is numeric
                for (ch, lbl), procs in by_slot.items():
                    if len(procs) == 1:
                        rows.append((ch, f'AVB {ch} - {lbl}'))
                    else:
                        for proc in procs:
                            rows.append((ch, f'AVB {ch} - {lbl} ({proc})'))
                rows.sort()  # (channel_number, display) — numeric primary
                return [s for _ch, s in rows]

            extra_context['analog_input_options'] = _build_simple('ANALOG')
            extra_context['aes_input_options'] = _build_simple('AES')
            extra_context['avb_input_options'] = _build_avb()

        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        # Issue #27: the changelist URL is the rack view now. Keep
        # `rack-view/` as a redirect so old bookmarks still land.
        urls = super().get_urls()
        custom = [
            path(
                'rack-view/',
                self.admin_site.admin_view(self._rack_view_redirect),
                name='planner_amp_rack_view',
            ),
        ]
        return custom + urls

    def _rack_view_redirect(self, request):
        return HttpResponseRedirect(reverse('admin:planner_amp_changelist'))

    def color_preview(self, obj):
        """Show a small color preview in the list"""
        if obj.color:
            return format_html(
                '<div style="width: 30px; height: 20px; background-color: {}; border: 1px solid #000;"></div>',
                obj.color
            )
        return '-'
    color_preview.short_description = 'Color'



    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            ('Basic Information', {
                'fields': ('location', 'amp_model', 'name', 'ip_address', 'preset', 'color')
            }),
        ]
        
        # `obj.amp_model` needs the same guard `obj` gets: the field is
        # nullable, so an amp awaiting a model reaches this page and the
        # bare deref made the change form itself a 500. The SC32 block
        # below always had the guard; these three did not.
        if obj and obj.amp_model and obj.amp_model.nl4_connector_count > 0:
            nl4_fields = []
            if obj.amp_model.nl4_connector_count >= 1:
                nl4_fields.append(('nl4_a_pair_1', 'nl4_a_pair_2'))
            if obj.amp_model.nl4_connector_count >= 2:
                nl4_fields.append(('nl4_b_pair_1', 'nl4_b_pair_2'))
            
            fieldsets.append(('NL4 Connectors', {
                'fields': nl4_fields,
                
            }))
        
        if obj and obj.amp_model and obj.amp_model.cacom_output_count > 0:
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


        if obj and obj.amp_model and obj.amp_model.nl8_connector_count > 0:
            nl8_fields = []
            if obj.amp_model.nl8_connector_count >= 1:
                nl8_fields.extend(['nl8_a_pair_1', 'nl8_a_pair_2', 'nl8_a_pair_3', 'nl8_a_pair_4'])
            if obj.amp_model.nl8_connector_count >= 2:
                nl8_fields.extend(['nl8_b_pair_1', 'nl8_b_pair_2', 'nl8_b_pair_3', 'nl8_b_pair_4'])
            
            fieldsets.append(('NL8 Connectors', {
                'fields': nl8_fields,
                'classes': ('collapse',)
            })) 

        if obj and obj.amp_model and hasattr(obj.amp_model, 'sc32_connector_count') and obj.amp_model.sc32_connector_count > 0:
            sc32_fields = [
                'sc32_ch1', 'sc32_ch2', 'sc32_ch3', 'sc32_ch4',
                'sc32_ch5', 'sc32_ch6', 'sc32_ch7', 'sc32_ch8',
                'sc32_ch9', 'sc32_ch10', 'sc32_ch11', 'sc32_ch12',
                'sc32_ch13', 'sc32_ch14', 'sc32_ch15', 'sc32_ch16'
            ]
            
            fieldsets.append(('SC32 Output', {
                'fields': sc32_fields,
            }))   

        return fieldsets
    
    inlines = [AmpChannelInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """The single dropdown hook for Amp (#100).

        There were two methods with this name in this class. Python keeps the
        last one defined, so the first was dead code -- and the dead one was
        the one that handled `amp_model`. Merged here, with the live
        behaviour preserved exactly:

        - `location` is project-specific: only AmpLocations in
          `request.current_project`, and `none()` rather than everything when
          there is no project (issue #29).

          Note the model. `Amp.location` points at **AmpLocation**; the dead
          copy filtered `Location`, a different table. Had the definition
          order been reversed, the dropdown would have been populated from
          the wrong model entirely -- so this is the half to keep.

        - `amp_model` is a global hardware catalogue and stays unfiltered.
          Stating it costs nothing and records that the omission is deliberate
          rather than another oversight.
        """
        if db_field.name == "location":
            if hasattr(request, 'current_project') and request.current_project:
                kwargs["queryset"] = AmpLocation.objects.filter(
                    project=request.current_project
                )
            else:
                kwargs["queryset"] = AmpLocation.objects.none()
        elif db_field.name == "amp_model":
            # Global catalogue, the same for every show. Not project-scoped.
            kwargs["queryset"] = AmpModel.objects.all()
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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
    list_display = ['name', 'description', 'export_pdf_button']
    search_fields = ['name', 'description']
    ordering = ['sort_order', 'name']

    fieldsets = (
        ('Location Information', {
            'fields': ('name', 'description', 'sort_order')
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
    export_pdf_button.short_description = 'Export Inventory'
    export_pdf_button.allow_tags = True
    
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)    


        #------------Processor------

class SystemProcessorAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'device_type', 'location', 'ip_address', 'created_at', 'configure_button']
    list_filter = [
        'device_type',
        project_scoped_filter('Location', 'location', Location),
        'created_at',
    ]
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)    




# ========== P1 Processor Admin ==========

class P1InputInline(admin.TabularInline):
    model = P1Input
    form = P1InputInlineForm
    extra = 0
    fields = ['input_type', 'channel_number', 'label']
    readonly_fields = ['input_type', 'channel_number']
    can_delete = False
    template = 'admin/planner/p1_input_inline.html'  # Use custom template

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by('input_type', 'channel_number')
    

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
    project_scoped_fks = {'system_processor': 'project'}
    form = P1ProcessorAdminForm
    change_form_template = 'admin/planner/p1processor/change_form.html'
    list_display = ['system_processor', 'get_location', 'get_ip_address', 'input_count', 'output_count']
    list_filter = [project_scoped_filter(
        'Location', 'system_processor__location', Location,
        queryset_path='system_processor__location',
    )]
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)    
    


        # ========== GALAXY Processor Admin ==========

class GalaxyInputInline(admin.TabularInline):
    model = GalaxyInput
    form = GalaxyInputInlineForm
    extra = 0
    fields = ['input_type', 'channel_number', 'label']
    readonly_fields = ['input_type', 'channel_number']
    can_delete = False
    template = 'admin/planner/galaxy_input_inline.html'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by('input_type', 'channel_number')
    

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
    project_scoped_fks = {'system_processor': 'project'}
    form = GalaxyProcessorAdminForm
    change_form_template = 'admin/planner/galaxyprocessor/change_form.html'
    list_display = ['system_processor', 'get_location', 'get_ip_address', 'input_count', 'output_count']
    list_filter = [project_scoped_filter(
        'Location', 'system_processor__location', Location,
        queryset_path='system_processor__location',
    )]
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)    
    




#-----------P.A, Cable------


# Add these to your admin.py file

from .models import PACableSchedule, PAZone, PAFanOut, PAFanOutExtension, PACoupler
from .forms import PACableChangelistForm, PACableInlineForm, PAZoneForm

class PACableInline(admin.TabularInline):
    """Inline admin for PA cables - spreadsheet-like entry"""
    model = PACableSchedule
    form = PACableInlineForm
    extra = 5
    fields = [
            'label', 'destination', 'count', 'length', 'cable', 
            'notes', 'drawing_ref', 'color'
        ]
    
    class Media:
        css = {
            'all': ('planner/css/pa_cable_admin.css',)
        }

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
    list_display = ['name', 'zone_type', 'sort_order']
    list_filter = ['zone_type']
    search_fields = ['name']
    list_editable = ['sort_order']
    ordering = ['sort_order', 'name']
    
    actions = ['create_default_zones']

    

    def get_queryset(self, request):
        """Filter zones by current project"""
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            from django.db.models import Q
            return qs.filter(project=request.current_project)
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project and handle duplicate names"""
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        
        # Check for duplicate zone name in this project before saving
        if hasattr(request, 'current_project') and request.current_project:
            existing = PAZone.objects.filter(
                project=request.current_project,
                name=obj.name
            )
            if change and obj.pk:
                existing = existing.exclude(pk=obj.pk)
            if existing.exists():
                from django.contrib import messages
                messages.error(request, f'A zone with the name "{obj.name}" already exists in this project.')
                return  # Don't save
        
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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


class PAFanOutExtensionInline(admin.TabularInline):
    """Issue #23: extensions live in their own table so a fan-out can have
    multiple. The fan_out dropdown is scoped to the current cable's fan-outs
    so the engineer doesn't see (or accidentally pick) fan-outs from a
    different cable / project.
    """
    model = PAFanOutExtension
    fk_name = 'cable_schedule'  # the model has two FKs; Django needs to know which is the parent link
    extra = 1
    fields = ['fan_out', 'extension_cable', 'extension_length', 'quantity']
    verbose_name = 'Fan-out Extension'
    # Issue #23 follow-up: this text is the section header. Putting the
    # save-first workflow note here (server-rendered) so it's never missed
    # — JS-injected hints have proven flaky in this admin theme.
    verbose_name_plural = (
        'Fan-out Extensions  '
        '(after adding fan-outs above, click Save below — '
        'they then become selectable in the Fan Out dropdown here)'
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'fan_out':
            cable_id = request.resolver_match.kwargs.get('object_id') if request.resolver_match else None
            if cable_id:
                kwargs['queryset'] = PAFanOut.objects.filter(cable_schedule_id=cable_id)
            else:
                kwargs['queryset'] = PAFanOut.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PACouplerInline(admin.TabularInline):
    """Issue #23 follow-up: couplers are their own row type on a cable run.

    Engineers used to pick coupler types from the PAFanOut dropdown, which
    confused the fan-out aggregation (a coupler isn't a fan-out). Listed
    here as a third inline below fan-outs and extensions.
    """
    model = PACoupler
    extra = 1
    fields = ['coupler_type', 'quantity']
    verbose_name = 'PA Coupler'
    verbose_name_plural = 'PA Couplers'


class CableTypeFilter(admin.SimpleListFilter):
    """Cable filter that can also reach rows with an unrecognised value.

    Django's default filter for a field with choices lists only the declared
    choices. `PACableSchedule.cable` defaulted to '100_NL4' until migration
    0197 -- not one of them -- so rows carrying that (or any other legacy
    value) had no option that selected them: they sat in the list under
    "All" with no way to filter to them and no sign they existed.

    Declared choices are always offered, in their declared order. Any other
    value actually present in this project is offered after them, flagged,
    so it can be found and fixed. Nothing is hidden either way -- an
    unselected filter still shows every row.
    """

    title = 'Cable'
    parameter_name = 'cable'

    def lookups(self, request, model_admin):
        known = list(PACableSchedule.CABLE_TYPE_CHOICES)
        known_values = {value for value, _ in known}

        qs = model_admin.get_queryset(request)
        present = set(qs.values_list('cable', flat=True).distinct())
        unknown = sorted(v for v in present if v and v not in known_values)

        return known + [
            (value, pa_cable_math.cable_type_label(value)) for value in unknown
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(cable=value)


class PACableAdmin(BaseEquipmentAdmin):
    """Admin for PA Cable Schedule"""
    form = PACableInlineForm

    plain_title_plural = "PA Cable"
    plain_title = "PA Cable Entry"
    inlines = [PAFanOutInline, PAFanOutExtensionInline, PACouplerInline]

    def response_post_save_change(self, request, obj):
        """Issue #23: keep the engineer on the cable edit page after Save so
        a newly-added fan-out becomes available in the Fan-out Extensions
        dropdown without a manual page refresh. The ``?saved=1`` query
        param is picked up by ``pa_cable_inlines.js`` to render a visible
        confirmation banner — without it the default 'changed successfully'
        message is small and easy to miss, which made the save+reload feel
        like nothing had happened.
        """
        return HttpResponseRedirect(request.path + '?saved=1')

    def response_post_save_add(self, request, obj):
        """Mirror of response_post_save_change for the add flow — land on
        the new cable's edit page so the engineer can immediately add
        fan-outs and extensions."""
        url = reverse(
            'admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name),
            args=[obj.pk],
            current_app=self.admin_site.name,
        )
        return HttpResponseRedirect(url + '?saved=1')
    list_display = [
    'array_speaker_col', 'destination_col', 'count', 'length',
    'cable_display', 'fan_outs_col', 'couplers_col', 'extensions_col',  # issue #73: broken out
    'notes', 'drawing_ref','color_display'
]
    list_filter = [CableTypeFilter]
    search_fields = ['destination', 'notes', 'drawing_ref']
    list_editable = ['count' ,'length']  
    
    change_list_template = 'admin/planner/pacableschedule/change_list.html'
    
    readonly_fields = ('array_speaker_reference',)

    fieldsets = (
        ('Array / Speaker & Destination', {
            'fields': ('entry_mode', 'speaker_array', 'amp', 'label', 'destination',
                       'array_speaker_reference'),
            'description': (
                "Choose <strong>From Soundvision / Amps</strong> to pick a Speaker "
                "Array (or single Speaker) and an Amp from the imported report, or "
                "<strong>Free text</strong> to type the Array/Speaker and Destination "
                "by hand. Existing cables stay on Free text."
            ),
        }),
        ('Cable Configuration', {
            'fields': ('count', 'length', 'cable', 'color')
        }),
        ('Documentation', {
            'fields': ('notes', 'drawing_ref')
        })
    )
    
    actions = ['export_cable_schedule', 'assign_color', 'duplicate_cable_runs']

    @admin.action(description='Duplicate selected cable runs')
    def duplicate_cable_runs(self, request, queryset):
        """Issue #22: clone each selected PACableSchedule row (including its
        PAFanOut children) so engineers can use a similar cable definition
        as a starting point for a new run."""
        n_cables = 0
        n_fans = 0
        for cable in queryset:
            fan_outs = list(cable.fan_outs.all())
            cable.pk = None
            cable._state.adding = True
            cable.save()
            for fan in fan_outs:
                fan.pk = None
                fan._state.adding = True
                fan.cable_schedule = cable
                fan.save()
            n_cables += 1
            n_fans += len(fan_outs)
        suffix = f' with {n_fans} fan-out(s).' if n_fans else '.'
        self.message_user(
            request,
            f'Duplicated {n_cables} cable run(s)' + suffix,
            messages.SUCCESS,
        )

    def color_display(self, obj):
        """Show a small color preview in the list"""
        if obj.color:
            return format_html(
                '<div style="width: 30px; height: 20px; background-color: {}; border: 1px solid #000;"></div>',
                obj.color
            )
        return '-'
    color_display.short_description = 'Color'

    def assign_color(self, request, queryset):
        """Bulk assign color to selected cables"""
        if 'apply' in request.POST:
            color = request.POST.get('color')
            if color:
                count = queryset.update(color=color)
                self.message_user(request, f'Color assigned to {count} cable(s).')
                return None
        
        from django.template.response import TemplateResponse
        return TemplateResponse(request, 'admin/planner/assign_color.html', {
            'cables': queryset,
            'action_checkbox_name': 'ACTION_CHECKBOX_NAME',
            'queryset': queryset,
        })
    assign_color.short_description = 'Assign color to selected cables'



    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter dropdown options based on current project"""
        current_project = getattr(request, 'current_project', None)
        if db_field.name == "label":
            kwargs["queryset"] = (
                PAZone.objects.filter(project=current_project)
                if current_project else PAZone.objects.none()
            )
        elif db_field.name == "speaker_array":
            # Issue #73: linked Array/Speaker dropdown = every speaker array and
            # single speaker in the project's imported Soundvision report(s).
            from planner.models import SpeakerArray
            kwargs["queryset"] = (
                SpeakerArray.objects.filter(prediction__project=current_project)
                if current_project else SpeakerArray.objects.none()
            )
        elif db_field.name == "amp":
            # Issue #73: linked Destination dropdown = every amp in the project's
            # Amplifier Reference module.
            from planner.models import Amp
            kwargs["queryset"] = (
                Amp.objects.filter(project=current_project)
                if current_project else Amp.objects.none()
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


   
    
    
    def array_speaker_col(self, obj):
        """Issue #73: unified Array/Speaker column (linked array/speaker or text label)."""
        return obj.array_speaker_display or "-"
    array_speaker_col.short_description = 'Array/Speaker'

    def destination_col(self, obj):
        """Issue #73: unified Destination column (linked amp or free text)."""
        return obj.destination_display or "-"
    destination_col.short_description = 'Destination'

    def array_speaker_reference(self, obj):
        """Issue #73 (Phase 2): a container the JS fills with the selected
        array's speakers (vertical list) and the cable assigned to it. Rendered
        for both add and change; populated live from the speaker_array dropdown.

        Data attributes seed the JS: the endpoint base (mount-path aware), the
        currently-saved array id, and the saved cable summary shown on the right."""
        from django.urls import reverse
        sample = reverse('planner:pa_cable_array_speakers', args=[999999])
        base = sample.rsplit('999999/speakers/', 1)[0]  # '.../pa-cables/array/'
        array_id = obj.speaker_array_id if (obj and obj.entry_mode == 'linked') else ''
        cable_label = obj.get_cable_display() if (obj and obj.cable) else ''
        count = obj.count if obj else ''
        fanout = (obj.fan_out_summary if obj else '') or ''
        return format_html(
            '<div id="pa-array-ref" class="pa-array-ref" '
            'data-endpoint-base="{}" data-array-id="{}" '
            'data-cable="{}" data-count="{}" data-fanout="{}">'
            '<em class="pa-array-ref__hint">Select an Array/Speaker in linked mode '
            'to list its speakers here.</em>'
            '</div>',
            base, array_id, cable_label, count, fanout,
        )
    array_speaker_reference.short_description = 'Array speakers & assigned cable'

    def cable_display(self, obj):
        # The data-* is what pa_cable_jumpers.js reads to blank the Length
        # input on a jumper row -- the server says what the row is, the JS
        # paints it, so the grid and the form agree without a second copy of
        # the jumper list in JavaScript.
        return format_html(
            '<span class="pa-cable-type" data-jumper="{}">{}</span>',
            'true' if pa_cable_math.is_jumper(obj.cable) else 'false',
            obj.get_cable_display())
    cable_display.short_description = 'Cable'
    cable_display.admin_order_field = 'cable'

    # Issue #73: fan-outs / couplers / extensions shown as chips directly in the
    # editable list (Count/Length stay editable), so there's one combined table
    # instead of a separate breakdown section.
    def _chips(self, items, css_class):
        if not items:
            return format_html('<span style="color:#777;">—</span>')
        html = format_html_join(
            '', '<span class="cb-chip {}">{}</span>',
            ((css_class, text) for text in items),
        )
        return html

    def fan_outs_col(self, obj):
        items = [f"{fo.get_fan_out_type_display()} × {fo.quantity}"
                 for fo in obj.fan_outs.all() if fo.fan_out_type]
        return self._chips(items, 'cb-fanout')
    fan_outs_col.short_description = 'Fan-outs'

    def couplers_col(self, obj):
        items = [f"{c.get_coupler_type_display()} × {c.quantity}"
                 for c in obj.couplers.all()]
        return self._chips(items, 'cb-coupler')
    couplers_col.short_description = 'Couplers'

    def extensions_col(self, obj):
        items = []
        for fo in obj.fan_outs.all():
            for ext in fo.extensions.all():
                items.append(f"{ext.get_extension_cable_display()} "
                             f"{ext.get_extension_length_display()} × {ext.quantity}")
        return self._chips(items, 'cb-ext')
    extensions_col.short_description = 'Extensions'

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
        
        # Calculate cable summaries.
        #
        # The breakdown rule lives in planner/utils/pa_cable_math.py and
        # nowhere else -- this view and the PDF Quick Order List both call it,
        # so the screen and the export cannot drift. That module states the
        # rule and carries the worked examples.
        cable_summary = {}

        # Keyed by stock length, so a spool size is one line here rather than
        # a set of parallel counters kept in step by hand. Stock is 100'/50'/
        # 25' -- 10' and 5' are not carried, and a shorter run takes a 25'.
        stock_keys = {100: 'hundreds', 50: 'fifties', 25: 'twenty_fives'}

        def empty_entry(is_jumper=False):
            entry = {'total_runs': 0, 'total_length': 0,
                     # A jumper is ordered by quantity, so it has no length
                     # and no stock breakdown. The template reads this to
                     # print "-" in those columns instead of a misleading 0.
                     'is_jumper': is_jumper,
                     'quantity_with_safety': 0,
                     # Issue #23 follow-up: couplers are an explicit PACoupler
                     # entity. The legacy hundreds-1 "between consecutive 100'
                     # runs" estimate would double up with the user-added
                     # rows, so this starts at 0 and the coupler loop fills it.
                     'couplers': 0}
            for key in stock_keys.values():
                entry[key] = 0
                entry['%s_with_safety' % key] = 0
            return entry

        def add_cables(entry, cables):
            for stock, qty in cables.items():
                key = stock_keys.get(stock)
                if key:
                    entry[key] += qty

        def apply_safety(entry):
            if entry['is_jumper']:
                # Nothing to break down -- the margin goes on the quantity.
                entry['quantity_with_safety'] = pa_cable_math.with_safety(
                    entry['total_runs'])
                return
            for key in stock_keys.values():
                entry['%s_with_safety' % key] = pa_cable_math.with_safety(
                    entry[key])

        # Group by each row's own cable value instead of iterating
        # CABLE_TYPE_CHOICES and filtering. PACableSchedule.cable defaults to
        # '100_NL4', which is not one of those choices, so the old loop
        # dropped any such row from the summary entirely: it counted toward
        # nothing on screen while a hand count of the drawing still included
        # it. An unrecognised value now appears under its raw name rather
        # than silently disappearing.
        display_names = dict(PACableSchedule.CABLE_TYPE_CHOICES)

        for cable in qs:
            name = display_names.get(cable.cable, cable.cable)
            if not name:
                continue
            jumper = pa_cable_math.is_jumper(cable.cable)
            entry = cable_summary.setdefault(name, empty_entry(jumper))
            entry['total_runs'] += cable.count or 0
            if jumper:
                # Whatever length is stored against a jumper is ignored, not
                # rewritten -- old rows keep theirs, they just stop counting.
                continue
            entry['total_length'] += (cable.length or 0) * (cable.count or 0)
            add_cables(entry, pa_cable_math.run_breakdown(
                cable.length, cable.count, cable.cable))

        # A 0' row contributes a run but no cable. Drop a type only when it
        # has neither, which is what the old `total_length > 0` guard meant.
        cable_summary = {
            name: entry for name, entry in cable_summary.items()
            if entry['total_runs'] or entry['total_length']
        }

        # Calculate fan out totals with 20% overage and merge extensions into cable counts
        fan_out_summary = {}
        
        for cable in qs.prefetch_related('fan_outs__extensions'):
            for fan_out in cable.fan_outs.all():
                # Count fan outs
                if fan_out.fan_out_type:
                    fan_out_name = fan_out.get_fan_out_type_display()
                    if fan_out_name not in fan_out_summary:
                        fan_out_summary[fan_out_name] = {
                            'total_quantity': 0,
                            'with_overage': 0
                        }
                    fan_out_summary[fan_out_name]['total_quantity'] += fan_out.quantity

                # Merge each extension into cable_summary (issue #23: extensions
                # now have their own quantity field — fan-out qty is no longer
                # the multiplier).
                #
                # An extension is a cable like any other, so it goes through
                # the same rule. It used to have one of its own that rounded
                # the wrong way -- `ext_length >= 100` put a 150' extension
                # down as a single 100' cable, short by a 50'. Anything
                # stored below 25' (the old 5'/6'/10' options) now rounds up
                # to a 25', the shortest length actually carried.
                ext_cable_map = {'NL4': 'NL 4', 'NL8': 'NL 8'}
                for ext in fan_out.extensions.all():
                    ext_length = ext.extension_length
                    ext_qty = ext.quantity
                    cable_name = ext_cable_map.get(ext.extension_cable, ext.extension_cable)
                    entry = cable_summary.setdefault(cable_name, empty_entry())
                    add_cables(entry, pa_cable_math.run_breakdown(
                        ext_length, ext_qty))
                    entry['total_runs'] += ext_qty
                    entry['total_length'] += (ext_length or 0) * ext_qty

        # Issue #23 follow-up: add explicit PACoupler counts into the
        # 'COUPLERS' column of the corresponding cable-type row. These are
        # user-managed coupler items, distinct from the auto-derived
        # 'between 100' runs' estimate calculated above.
        coupler_cable_map = {
            'NL4_COUPLER': 'NL 4',
            'NL8_COUPLER': 'NL 8',
            'CACOM_COUPLER': 'CA-COM',
        }
        coupler_summary = {}  # for the Quick Order List row group
        for cable in qs.prefetch_related('couplers'):
            for c in cable.couplers.all():
                cable_name = coupler_cable_map.get(c.coupler_type)
                if not cable_name:
                    continue
                entry = cable_summary.setdefault(cable_name, empty_entry())
                entry['couplers'] += c.quantity

                label = c.get_coupler_type_display()
                if label not in coupler_summary:
                    coupler_summary[label] = {'total_quantity': 0, 'with_overage': 0}
                coupler_summary[label]['total_quantity'] += c.quantity

        # The 20% ordering margin goes on ONCE, here, now that runs and
        # extensions have both been counted. It used to be reapplied after
        # every extension, which meant un-ceiling a subtotal to add to it --
        # and ceil() does not survive that round trip.
        for entry in cable_summary.values():
            apply_safety(entry)

        # Keep the table in CABLE_TYPE_CHOICES order, with any unrecognised
        # cable value after the known ones rather than wherever the rows
        # happened to fall.
        choice_order = [label for _, label in PACableSchedule.CABLE_TYPE_CHOICES]
        cable_summary = dict(sorted(
            cable_summary.items(),
            key=lambda kv: (choice_order.index(kv[0])
                            if kv[0] in choice_order else len(choice_order),
                            kv[0])))

        # Calculate 20% overage for each fan out type
        for fan_out_type in fan_out_summary:
            total = fan_out_summary[fan_out_type]['total_quantity']
            fan_out_summary[fan_out_type]['with_overage'] = math.ceil(total * 1.2)

        # ... and for each coupler type
        for coupler_label in coupler_summary:
            total = coupler_summary[coupler_label]['total_quantity']
            coupler_summary[coupler_label]['with_overage'] = math.ceil(total * 1.2)

        # Add to context
        response.context_data['cable_summary'] = cable_summary
        response.context_data['fan_out_summary'] = fan_out_summary
        response.context_data['coupler_summary'] = coupler_summary
        # Jumpers have no length, so they are not part of a length total.
        response.context_data['grand_total'] = sum(
            s['total_length'] for s in cable_summary.values()
            if not s['is_jumper'])
        response.context_data['cable_rule_text'] = pa_cable_math.RULE_TEXT

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
        
        # Eight headings over seven values put every column after 'Cable'
        # one cell to the left of its own name: the fan-outs landed under
        # 'Count2', the notes under 'Fan Out', the drawing ref under
        # 'Notes', and 'Drawing Ref' was always empty. 'Count2' is the
        # phantom -- there is no count2 field on PACableSchedule and
        # nothing has ever written one.
        writer.writerow([
            'Array/Speaker', 'Destination', 'Count', 'Cable',
            'Fan Out', 'Notes', 'Drawing Ref'
        ])
        
        # Group by cable type for summary
        cable_totals = {}
        fan_out_totals = {}
        
        
        # Write data rows
        for cable in (queryset
                      .select_related('label', 'speaker_array', 'amp')
                      .prefetch_related('fan_outs')
                      .order_by('label__sort_order', 'cable')):
            # Build fan out summary string for this cable
            fan_out_display = ''
            if cable.fan_outs.exists():
                fan_out_items = []
                for fan_out in cable.fan_outs.all():
                    if fan_out.fan_out_type:
                        fan_out_items.append(f'{fan_out.get_fan_out_type_display()} x{fan_out.quantity}')
                fan_out_display = ', '.join(fan_out_items)
            
            # array_speaker_display / destination_display, not the raw
            # label and destination columns: a cable entered in "From
            # Soundvision / Amps" mode leaves both of those empty and
            # carries its array and amp in speaker_array / amp instead
            # (issue #73), so the raw reads exported a run with no
            # indication of what it ran from or to. Same two properties
            # as the changelist columns and the System Report (#99).
            writer.writerow([
                cable.array_speaker_display or '',
                cable.destination_display or '',
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

            # Track fan out totals. This loop used to sit one level out,
            # in the method body rather than in the per-cable loop, so it
            # ran once on whichever cable the loop happened to leave
            # behind: the FAN OUT SUMMARY at the foot of the CSV counted
            # the last row's fan-outs and no others. (On an empty
            # queryset it also read an unbound `cable`, though an admin
            # action always has rows selected.)
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

        # Issue #23 follow-up: tally explicit PACoupler rows by cable-type
        # display name so the CSV's 'Couplers Needed' column matches the
        # admin summary (no more legacy hundreds-1 auto-calc).
        coupler_totals = {}
        _coupler_cable_map = {
            'NL4_COUPLER': 'NL 4',
            'NL8_COUPLER': 'NL 8',
            'CACOM_COUPLER': 'CA-COM',
        }
        for cable in queryset.prefetch_related('couplers'):
            for c in cable.couplers.all():
                name = _coupler_cable_map.get(c.coupler_type)
                if name:
                    coupler_totals[name] = coupler_totals.get(name, 0) + c.quantity

        for cable_type, totals in cable_totals.items():
            total = totals['total_length']
            overage = total * 0.2
            total_with_overage = total * 1.2

            hundreds = int(total_with_overage / 100)
            twenty_fives = int((total_with_overage % 100) / 25)
            remainder = total_with_overage % 25
            couplers = coupler_totals.get(cable_type, 0)
            
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)
    
    def get_changelist_form(self, request, **kwargs):
        """The list_editable grid uses the jumper-aware form.

        Without this the grid's Length input stays model-required, and a
        jumper row -- whose input the JS blanks -- could not be saved.
        """
        kwargs.setdefault('form', PACableChangelistForm)
        return super().get_changelist_form(request, **kwargs)

    class Media:
        css = {
            'all': ('planner/css/pa_cable_admin.css',)
        }
        # Issue #23: pa_cable_inlines.js handles the X-button delete UX and
        # the post-save banner. MUST be defined together with the other
        # assets here — a second `class Media` further up would silently
        # overwrite this one (Python class-body semantics).
        js = (
            'admin/js/pa_cable_inlines.js',
            'admin/js/pa_cable_entry_mode.js',
            'admin/js/pa_cable_array_speakers.js',
            'admin/js/pa_cable_jumpers.js',
        )


    def get_queryset(self, request):
        """Filter by current project"""
        qs = super().get_queryset(request)
        # Issue #73: the list now renders fan-outs / couplers / extensions per
        # row, so prefetch them to avoid N+1 queries in the changelist.
        qs = qs.prefetch_related('fan_outs__extensions', 'couplers')
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



from .models import (CommChannel, CommPosition, CommCrewName, CommBeltPack,
                     CommConfig, CommDeviceModel)
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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

def has_module_permission(self, request):
    return False


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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/comm_position_buttons.css',)
        }
    
def has_module_permission(self, request):
    return False   


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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)
    
    def save_model(self, request, obj, form, change):
        """Auto-assign current project, and flag a name that is really a position.

        Crew Names and Positions are two separate pick lists on the belt pack
        form, and they are only useful while they hold different kinds of
        thing. In practice a crew list drifts: "GFX 1" and "LED 2" get typed in
        here, and then the Name dropdown is half people and half positions.

        This does not block the save -- sometimes a position really is the best
        label available on the day -- it says so once, when the name is written.
        """
        if not change and hasattr(request, 'current_project') and request.current_project:
            obj.project = request.current_project
        super().save_model(request, obj, form, change)

        project = getattr(obj, 'project', None)
        if project and obj.name and CommPosition.objects.filter(
                project=project, name__iexact=obj.name).exists():
            self.message_user(
                request,
                '"%s" is also a Position in this project. Crew Names are for '
                'people; keeping positions in the Positions list is what stops '
                'the Name dropdown on a belt pack filling up with them.'
                % obj.name,
                messages.WARNING,
            )

        
    class Media:
        css = {
            'all': ('admin/css/comm_crew_name_buttons.css',)
        }


def has_module_permission(self, request):
        return False


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
    # Named here rather than on the model: it is what this section is called
    # in the admin, matching the Channels column on the list, and an admin
    # label costs no migration.
    verbose_name = 'Channel'
    verbose_name_plural = 'Channels'
    extra = 0  # Don't show empty forms by default
    # Issue #66: one-click "×" delete in place of Django's default "Delete?"
    # checkbox column, which rendered as a tiny near-invisible checkbox on the
    # dark admin theme. The X posts to comm_beltpack_channel_delete and removes
    # the row immediately (no Save required). Mirrors MicAssignmentInline (#36).
    fields = ['channel_number', 'channel', 'delete_x']
    readonly_fields = ['delete_x']
    can_delete = False
    ordering = ['channel_number']

    class Media:
        js = ('admin/js/comm_beltpack_channel_delete.js',)

    def delete_x(self, obj):
        if not obj.pk:
            return ''
        return format_html(
            '<a href="#" class="bpchannel-delete-x" data-bpchannel-id="{}" '
            'title="Delete this channel" '
            'style="color:#ff4d4d;text-decoration:none;font-weight:bold;'
            'font-size:18px;line-height:1;padding:2px 8px;">×</a>',
            obj.pk,
        )
    delete_x.short_description = ''

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

    device_model = None   # replaced in __init__; see comm_device_model_field

        
    class Meta:
        model = CommBeltPack
        fields = '__all__'
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The Model dropdown, grouped by manufacturer. System Type is not on
        # this form any more: it follows from the chosen model's device type
        # (CommBeltPack.save), and each option carries a data-system-type for
        # the conditional rows below.
        if 'device_model' in self.fields:
            self.fields['device_model'] = comm_device_model_field(
                label='Model',
                help_text='System Type follows from the device type.')
            _keep_current_model(self.fields['device_model'], self.instance)

        # checked_out is NOT swapped for a HiddenInput on a hardwired pack
        # any more: it has to stay a normal row so the bp-sys-* CSS can
        # show it again the moment System Type is switched back to
        # Wireless. The model still forces it False for hardwired on save.

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

    def clean(self):
        """A hardwired pack is simply not checked out -- it is not an error.

        `checked_out` is a real checkbox now rather than a HiddenInput, and a
        checkbox that CSS has hidden still posts if it was ticked. So ticking
        "Checked out" on a wireless pack and then switching System Type to
        Hardwired used to reach `CommBeltPack.clean()` and come back as
        "Hardwired belt packs cannot be checked out." -- an error about a field
        the user could no longer see, with nothing on screen to fix.

        Model.save() already drops the flag for a hardwired pack without
        complaint; this makes the form agree with it instead of refusing the
        save.
        """
        cleaned = super().clean()
        model = cleaned.get('device_model')
        system_type = model.system_type if model else cleaned.get('system_type')
        if system_type == 'HARDWIRED':
            cleaned['checked_out'] = False
        return cleaned

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
            # Every position in the project, not only the ones already in use.
            # Django drops a filter whose lookups are empty, so listing only
            # positions already assigned meant the Position dropdown vanished
            # from the filter row entirely until somebody had assigned one --
            # which is exactly when you want to filter by it. Matches what the
            # Location filter does.
            positions = CommPosition.objects.filter(
                project=current_project).order_by('name')
            return [(p.id, p.name) for p in positions]
        return []
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(position_id=self.value())
        return queryset


class SystemFilter(admin.RelatedFieldListFilter):
    """device_model, titled "System" rather than Django's "model"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = 'System'


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


class _DeviceModelSelect(forms.Select):
    """A model dropdown whose options say which System Type they imply.

    The conditional IP Address / "Checked out" rows used to watch the System
    Type select. There is no System Type select any more -- it follows from the
    device type -- so each option carries the answer and the JS reads it off
    the chosen one.
    """

    def create_option(self, name, value, label, selected, index,
                      subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index,
                                       subindex=subindex, attrs=attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-system-type'] = instance.system_type
        return option


class _GroupedModelChoiceIterator(forms.models.ModelChoiceIterator):
    """Yields (group label, [choices]) so Django renders <optgroup>s.

    ModelChoiceField has no grouping of its own, and a flat list of every
    device across every manufacturer is the thing this was meant to replace.
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        groups = {}
        order = []
        for obj in self.queryset:
            key = self.field.group_by(obj)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(self.choice(obj))
        for key in order:
            yield (key, groups[key])


class GroupedModelChoiceField(forms.ModelChoiceField):
    # A CLASS attribute, not something assigned after super().__init__():
    # ModelChoiceField's queryset setter runs during __init__ and hands
    # `self.choices` to the widget there and then, so an iterator assigned
    # afterwards is never the one the widget renders. Setting it here renders
    # flat options with no <optgroup> at all -- which is what happened.
    iterator = _GroupedModelChoiceIterator

    def __init__(self, *args, group_by=None, label_for=None, **kwargs):
        # Both of these are read by the iterator, so they have to exist before
        # super().__init__() gets as far as building choices.
        self.group_by = group_by or (lambda obj: '')
        self._label_for = label_for
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        if self._label_for is not None:
            return self._label_for(obj)
        return super().label_from_instance(obj)


def comm_device_model_field(**kwargs):
    """The Model dropdown, grouped by manufacturer, used by both forms.

    Only active rows are offered, but the queryset deliberately does not filter
    out the row a device already points at -- see `_keep_current_model`.
    """
    kwargs.setdefault('queryset', CommDeviceModel.objects.filter(is_active=True))
    kwargs.setdefault('required', False)
    kwargs.setdefault('empty_label', '---------')
    kwargs.setdefault('widget', _DeviceModelSelect)
    kwargs.setdefault('group_by', lambda obj: obj.manufacturer)
    # The manufacturer is already the optgroup heading, so repeating it on
    # every option just makes the list harder to scan.
    kwargs.setdefault(
        'label_for',
        lambda obj: f"{obj.name} ({obj.get_device_type_display()})")
    return GroupedModelChoiceField(**kwargs)


def _keep_current_model(field, instance):
    """Make sure a device still lists the model it already has.

    A model that has been retired (is_active False) is out of the dropdown, so
    a device pointing at one would otherwise silently re-save as "no model" --
    editing a crew name would quietly erase the hardware.
    """
    current = getattr(instance, 'device_model_id', None)
    if current and not field.queryset.filter(pk=current).exists():
        field.queryset = CommDeviceModel.objects.filter(
            models.Q(is_active=True) | models.Q(pk=current))


class CommDeviceModelAdmin(BaseAdmin):
    """The hardware catalogue.

    Superuser-only to edit: the table is shared by every tenant, so an owner
    adding "our FSII" to it would be editing everyone's dropdown. Everyone
    still picks from it on a device.
    """

    plain_title_plural = "Comm Device Models"
    plain_title = "Comm Device Model"

    list_display = ['name', 'manufacturer', 'device_type',
                    'system_type_display', 'default_channel_count',
                    'is_active', 'devices_using']
    list_filter = ['manufacturer', 'device_type', 'is_active']
    list_editable = ['default_channel_count', 'is_active']
    search_fields = ['manufacturer', 'name']
    ordering = ['manufacturer', 'name']

    fieldsets = (
        (None, {
            'fields': ('manufacturer', 'name', 'device_type',
                       'default_channel_count', 'is_active'),
        }),
    )

    @admin.display(description='System Type')
    def system_type_display(self, obj):
        return obj.system_type

    @admin.display(description='In use')
    def devices_using(self, obj):
        """How many devices point here -- what a delete would be taking out."""
        return obj.devices.count()

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser


showstack_admin_site.register(CommDeviceModel, CommDeviceModelAdmin)


class CommBeltPackBulkRowForm(forms.ModelForm):
    """One row of the "Add multiple" grid.

    Deliberately the six columns and no more: BP #, System, Position, Name,
    Headset, Group. System Type is not a column because a batch is realistically
    all wireless or all hardwired -- it is chosen once in the toolbar above the
    grid and applied to every row the formset creates.

    Position and Name stay two separate pick lists, reading CommPosition and
    CommCrewName respectively. That separation is the point of the grid as much
    as the speed is: one combined "name" column is how a crew list ends up
    holding "GFX 1" and "LED 2" alongside people.
    """

    # What makes a row real. BP # is excluded on purpose: every row arrives
    # with one prefilled, so counting it would turn twenty untouched rows into
    # twenty numbered empty devices on the first save. Model can be counted
    # plainly now -- it has no default, so a row only has one because somebody
    # chose it.
    CONTENT_FIELDS = ('device_model', 'position', 'name', 'headset', 'group')

    class Meta:
        model = CommBeltPack
        fields = ('bp_number', 'device_model', 'position', 'name', 'headset',
                  'group')

    def __init__(self, *args, **kwargs):
        project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)

        # Multi-tenancy: both pick lists are this project's, same as the
        # single-pack form does.
        if project is not None:
            self.fields['position'].queryset = CommPosition.objects.filter(
                project=project).order_by('name')
            self.fields['name'].queryset = CommCrewName.objects.filter(
                project=project).order_by('name')
        else:
            self.fields['position'].queryset = CommPosition.objects.none()
            self.fields['name'].queryset = CommCrewName.objects.none()

        self.fields['position'].empty_label = '---'
        self.fields['name'].empty_label = '---'

        # Same grouped Model dropdown as the single-device form.
        self.fields['device_model'] = comm_device_model_field(
            label='Model', empty_label='---')
        _keep_current_model(self.fields['device_model'], self.instance)

        # Blank is the normal state of most of this grid.
        for field_name in ('bp_number',) + self.CONTENT_FIELDS:
            self.fields[field_name].required = False

    def is_filled(self):
        """True if the user put something in this row.

        Called after validation; an unvalidated or untouched form has no
        cleaned_data and is simply not a row.
        """
        cleaned = getattr(self, 'cleaned_data', None) or {}
        return any(cleaned.get(f) for f in self.CONTENT_FIELDS)

    def clean(self):
        cleaned = super().clean()
        if self.is_filled() and cleaned.get('bp_number') in (None, ''):
            self.add_error('bp_number', 'BP # is required for a filled row.')
        return cleaned


class CommBeltPackAdmin(BaseEquipmentAdmin):
    form = CommBeltPackAdminForm

    # Page headings only -- the sidebar keeps reading Meta.verbose_name_plural,
    # so this needs no model change.
    plain_title_plural = "Comm Devices"
    plain_title = "Comm Device"
    
    # Add autocomplete for better UX (optional but recommended)
    #autocomplete_fields = ['position', 'name', 'channel_a', 'channel_b', 'channel_c', 'channel_d', 'channel_e', 'channel_f']
    
    # Right after autocomplete_fields, add:
    # Headset Type and IP Address are deliberately not here. Nine columns
    # plus the filter sidebar did not fit at 1280 (let alone 1024) and these
    # two were the least useful to scan: a headset type is a per-person detail
    # and an IP only ever applies to a hardwired device and was blank on most
    # rows. Both are still on the device form and still searchable.
    list_display = [
        'bp_number',
        'system_type_icon',  # Custom method
        'device_model',
        'position',  # Keep as field for inline editing
        'name',
        'unit_location',  # Location column
        'channel_summary',
        'checkout_control',
    ]




      # ← Line 3324 - end of list_display
    
    # ADD THIS RIGHT HERE:
    # checked_out left on purpose: it is a one-tap toggle that saves on its
    # own now (see checkout_control / toggle_checkout_view), so putting it in
    # the formset as well would give it a second, slower way to change that
    # could disagree with the button.
    list_editable = [
        'position',
        'name',
        'unit_location',
    ]
    
        
    
    # Rendered as one compact row above the table, not a sidebar -- see the
    # `filters` block in commbeltpack/change_list.html. Still Django's own
    # filter machinery, so the query strings are unchanged.
    #
    # System Type and Headset dropped from the set: the rows are already
    # grouped into Wireless / Hardwired with counts, and headset is not
    # something a list gets filtered by in practice.
    list_filter = [
        ('device_model', SystemFilter),
        'device_model__device_type',
        ProjectFilteredLocationFilter,
        ProjectFilteredPositionFilter,
        'checked_out',
    ]


    inlines = [CommBeltPackChannelInline]
    search_fields = ['bp_number', 'name__name', 'position__name', 'notes',
                     'unit_location__name', 'ip_address',
                     'device_model__manufacturer', 'device_model__name']
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

    # manufacturer_display is gone with the legacy column: the list shows
    # device_model, which is a FK and sorts on its own Meta ordering.

    def channel_summary(self, obj):
        """Display summary of assigned channels with clickable badges"""
        from django.utils.safestring import mark_safe
        
        channels = obj.channels.all()
        if not channels:
            return mark_safe('<span style="color: #666;">No channels</span>')
        
        # Styling moved to comm_admin_v2.css (.ch-badge / .ch-badge-grid):
        # a 380px-wide four-column grid of 75px badges was the widest column
        # on the page by far and is what stopped everything fitting at 1024.
        # The badges keep their classes and data-* attributes, so the channel
        # assignment popup still finds them.
        badges = []
        for ch in channels[:12]:
            if ch.channel:
                ch_abbrev = ch.channel.abbreviation if hasattr(ch.channel, 'abbreviation') and ch.channel.abbreviation else ch.channel.name[:4]
                badge = (f'<span class="ch-badge assigned" data-bpc-id="{ch.id}" '
                         f'data-ch-num="{ch.channel_number}" data-bp-id="{obj.id}" '
                         f'title="Channel {ch.channel_number}: {ch_abbrev}">'
                         f'{ch.channel_number}: {ch_abbrev}</span>')
            else:
                badge = (f'<span class="ch-badge unassigned" data-bpc-id="{ch.id}" '
                         f'data-ch-num="{ch.channel_number}" data-bp-id="{obj.id}" '
                         f'title="Channel {ch.channel_number}: unassigned">'
                         f'{ch.channel_number}: —</span>')
            badges.append(badge)

        result = f'''<div class="ch-badge-grid">{''.join(badges)}</div>'''

        if channels.count() > 12:
            result += f'''<span class="ch-badge-more">+{channels.count() - 12}</span>'''

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
        js = (
            'admin/js/comm_beltpack_admin.js',
            'admin/js/comm_checkout.js',
        )





    # Related models reachable from a belt pack, and the field each one is
    # offered under. Declared as data so the two concerns below -- scoping the
    # queryset and stripping the widget's add/edit buttons -- cannot drift
    # apart again.
    _SCOPED_FK_SOURCES = {
        'unit_location': (Location, 'name'),
        'position': (CommPosition, 'name'),
        'name': (CommCrewName, 'name'),
        'channel_a': (CommChannel, 'input_designation'),
        'channel_b': (CommChannel, 'input_designation'),
        'channel_c': (CommChannel, 'input_designation'),
        'channel_d': (CommChannel, 'input_designation'),
        'channel_e': (CommChannel, 'input_designation'),
        'channel_f': (CommChannel, 'input_designation'),
    }

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """The single dropdown hook for CommBeltPack (#100 follow-on).

        This class also had two methods with this name, the same bug as
        AmpAdmin. The later one -- the project scoping -- won, so the earlier
        one's job was silently never done: the add/edit/delete buttons it
        meant to strip from the `position`, `name` and `unit_location` widgets
        have always been rendered. Both halves now live here.

        The scoping itself also had a fail-open shape::

            if current_project:
                if db_field.name == ...: kwargs['queryset'] = ...

        With no current project every branch was skipped and each dropdown
        fell back to Django's default -- the entire table, so every tenant's
        crew names and positions. The filter is now unconditional, with
        ``none()`` as the no-project answer.
        """
        current_project = getattr(request, 'current_project', None)
        source = self._SCOPED_FK_SOURCES.get(db_field.name)
        if source and 'queryset' not in kwargs:
            model, order_by = source
            kwargs['queryset'] = (
                model.objects.filter(project=current_project).order_by(order_by)
                if current_project else model.objects.none()
            )

        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)

        # Crew names, positions and locations are managed on their own pages;
        # the little green plus/pencil next to the belt pack row only invites
        # half-populated rows. (This is the half that was dead code.)
        if formfield is not None and db_field.name in ('position', 'name', 'unit_location'):
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
            formfield.widget.can_delete_related = False
            formfield.widget.can_view_related = False
        return formfield


    
    
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
        """Fieldsets carrying the current system type as a CSS hook.

        IP Address is a hardwired-only field and "Checked out" a wireless-only
        one, and this used to express that by leaving `checked_out` out of the
        fieldset entirely for a saved hardwired pack. That cannot toggle: the
        field is not in the DOM, so changing System Type did nothing until the
        page was saved and reloaded, and IP Address showed for every pack
        regardless.

        Both fields are always rendered now, and which one is visible is a
        `bp-sys-WIRELESS` / `bp-sys-HARDWIRED` class on the fieldsets that hold
        them (see comm_admin_v2.css). The class is set here from the saved
        value, so the right field is hidden on first paint with no JavaScript;
        comm_beltpack_admin.js only has to swap the class when the select
        changes. The model still forces checked_out False for a hardwired pack
        on save, so a hidden field cannot carry a wrong value into the data.
        """
        system_class = 'bp-sys-HARDWIRED' if (
            obj and obj.system_type == 'HARDWIRED') else 'bp-sys-WIRELESS'

        return [
            ('System Configuration', {
                # No system_type: it is derived from the model's device type,
                # so offering it as a second control would only let the two
                # disagree until the next save.
                'fields': ('device_model', 'bp_number',
                           'unit_location', 'ip_address'),
                'classes': (system_class,),
            }),
            ('Assignment', {
                'fields': ('position', 'name', 'headset'),
            }),
            ('Settings', {
                'fields': ('audio_pgm', 'group', 'checked_out'),
                'classes': (system_class,),
            }),
            ('Notes', {
                'fields': ('notes',),
                'classes': ('collapse',),
            }),
        ]
    

    def get_urls(self):
        """Add custom AJAX URL for channel assignment"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('assign-channel/', self.admin_site.admin_view(self.assign_channel_view), name='commbeltpack_assign_channel'),
            path('get-channels/', self.admin_site.admin_view(self.get_channels_view), name='commbeltpack_get_channels'),
            path('add-multiple/', self.admin_site.admin_view(self.add_multiple_view), name='commbeltpack_add_multiple'),
            path('toggle-checkout/', self.admin_site.admin_view(self.toggle_checkout_view), name='commbeltpack_toggle_checkout'),
        ]
        return custom_urls + urls

    # ------------------------------------------------------------------
    # Check-out toggle
    # ------------------------------------------------------------------

    @staticmethod
    def duplicate_device_numbers(project):
        """Device #s that more than one device in this project is using.

        One query, one caller-facing shape -- the changelist banner and the
        post-save warning both read this, so they cannot disagree about what
        counts as a duplicate.
        """
        rows = (CommBeltPack.objects
                .filter(project=project)
                .values('bp_number')
                .annotate(n=Count('pk'))
                .filter(n__gt=1)
                .order_by('bp_number'))
        return {row['bp_number']: row['n'] for row in rows}

    def warn_duplicate_device_numbers(self, request, project, only=None):
        """Say which Device #s are doubled up. A warning, never a block.

        Deliberately not a validation error. Two devices really do share a
        number for a few minutes during load-in while a rack is being
        renumbered, and a save that refuses at that moment costs more than it
        saves. `only` narrows the warning to one number, for the case where a
        single save is what created the clash.
        """
        if not project:
            return
        dups = self.duplicate_device_numbers(project)
        if only is not None:
            dups = {n: c for n, c in dups.items() if n == only}
        if not dups:
            return

        url = reverse('admin:planner_commbeltpack_changelist')
        # Each number links to the list searched for it, so the clash is one
        # click away rather than something to go hunting for in 50 rows.
        links = format_html_join(
            ', ', '<a href="{}?q={}">#{}</a> ({} devices)',
            ((url, number, number, count) for number, count in dups.items()))
        self.message_user(
            request,
            format_html(
                'Duplicate Device {}: {}. Device numbers are not required to '
                'be unique, so nothing was blocked \u2014 but a repeated number '
                'makes a pack impossible to identify on a run sheet.',
                'number' if len(dups) == 1 else 'numbers', links),
            messages.WARNING)

    @staticmethod
    def wireless_counters(project):
        """Total / out / available for this project's wireless devices.

        One function so the numbers the page loads with and the numbers a
        toggle sends back cannot drift apart -- they are the same query.
        """
        wireless = CommBeltPack.objects.filter(
            project=project, system_type='WIRELESS')
        total = wireless.count()
        out = wireless.filter(checked_out=True).count()
        return {'total': total, 'out': out, 'avail': total - out}

    @admin.display(description='Checked out')
    def checkout_control(self, obj):
        """An empty cell carrying state; comm_checkout.js paints the button.

        Deliberately not rendering the button here. The Mic Tracker learned
        this the hard way: when the server paints one version of a control and
        the script paints another after a change, the two drift and a reloaded
        screen stops matching a live one. There is one renderer, it is in the
        JS, and it runs over this cell on load and again after every toggle.
        """
        return format_html(
            '<span class="comm-checkout" data-device-id="{}" '
            'data-system-type="{}" data-checked-out="{}"></span>',
            obj.pk, obj.system_type, 'true' if obj.checked_out else 'false')

    def toggle_checkout_view(self, request):
        """Flip one wireless device's checked-out flag and report the state."""
        from django.http import JsonResponse

        if request.method != 'POST':
            return JsonResponse({'error': 'POST required'}, status=405)

        project = getattr(request, 'current_project', None)
        if not project:
            return JsonResponse({'error': 'No project selected'}, status=400)
        if not self._bulk_can_edit(request):
            return JsonResponse({'error': 'Read-only access'}, status=403)

        try:
            payload = json.loads(request.body or '{}')
            device_id = int(payload.get('device_id'))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Bad device id'}, status=400)

        # Scoped to the current project: an id from another tenant's page must
        # not be togglable just because it is a valid id.
        device = CommBeltPack.objects.filter(
            pk=device_id, project=project).first()
        if device is None:
            return JsonResponse({'error': 'Not found'}, status=404)
        if device.system_type != 'WIRELESS':
            return JsonResponse(
                {'error': 'Only a wireless device can be checked out'},
                status=400)

        device.checked_out = not device.checked_out
        device.save(update_fields=['checked_out', 'updated_at'])

        return JsonResponse({
            'ok': True,
            'device_id': device.pk,
            'checked_out': device.checked_out,
            'system_type': device.system_type,
            'counters': self.wireless_counters(project),
        })

    # ------------------------------------------------------------------
    # "Add multiple" grid
    # ------------------------------------------------------------------

    BULK_ROWS = 20

    def _bulk_can_edit(self, request):
        """Per-project gate for the bulk grid.

        `has_add_permission` on the base admin answers "may this user add
        equipment *somewhere*" -- it is satisfied by editor access on any
        project at all. That is the global-group-versus-per-project-role trap,
        so the role on the project actually being written to is checked here as
        well, the same pair of roles the single-pack form allows.
        """
        if request.user.is_superuser:
            return True
        if not self.has_add_permission(request):
            return False
        project = getattr(request, 'current_project', None)
        return self._get_user_role_for_project(request, project) in (
            'owner', 'editor')

    def _bulk_formset_class(self):
        return forms.modelformset_factory(
            CommBeltPack,
            form=CommBeltPackBulkRowForm,
            extra=self.BULK_ROWS,
            can_delete=False,
        )

    def _bulk_initial(self, project):
        """Sequential BP #s continuing from the project's highest.

        BP # is the only prefilled column, which is what lets `is_filled` treat
        every other column as evidence that somebody typed in this row.
        """
        start = (CommBeltPack.objects.filter(project=project).aggregate(
            models.Max('bp_number'))['bp_number__max'] or 0) + 1
        return [{'bp_number': start + i} for i in range(self.BULK_ROWS)]

    def add_multiple_view(self, request):
        """Create a screenful of belt packs in one save."""
        from django.shortcuts import redirect, render

        project = getattr(request, 'current_project', None)
        if not project:
            self.message_user(
                request, 'Select a project before adding comm devices.',
                messages.ERROR)
            return redirect('admin:planner_commbeltpack_changelist')

        if not self._bulk_can_edit(request):
            raise PermissionDenied

        FormSet = self._bulk_formset_class()
        queryset = CommBeltPack.objects.none()
        initial = self._bulk_initial(project)

        if request.method == 'POST':
            formset = FormSet(
                request.POST, queryset=queryset, initial=initial,
                form_kwargs={'project': project},
            )
            if formset.is_valid():
                # Not formset.save(): that keys off has_changed(), and every
                # row here arrives with a prefilled BP # and system, so all
                # twenty would count as changed and twenty empty packs would
                # appear. is_filled() asks the narrower question.
                packs = []
                for form in formset.forms:
                    if not form.is_filled():
                        continue
                    pack = form.save(commit=False)
                    pack.project = project
                    # No system_type to set: Model.save() derives it from the
                    # chosen model's device type, and forces checked_out False
                    # for anything hardwired.
                    pack.save()
                    packs.append(pack)

                if packs:
                    self.message_user(
                        request,
                        'Added %d comm device%s.' % (
                            len(packs), '' if len(packs) == 1 else 's'),
                        messages.SUCCESS)
                    # Twenty prefilled Device #s is where duplicates actually
                    # come from, so the grid says so on the way out.
                    self.warn_duplicate_device_numbers(request, project)
                    return redirect('admin:planner_commbeltpack_changelist')

                # Nothing filled in: say so rather than bouncing the user back
                # to the list as though something had happened.
                self.message_user(
                    request, 'No rows were filled in, so nothing was added.',
                    messages.WARNING)
        else:
            formset = FormSet(
                queryset=queryset, initial=initial,
                form_kwargs={'project': project},
            )

        context = {
            **self.admin_site.each_context(request),
            'title': 'Add multiple comm devices',
            'formset': formset,
            'opts': self.model._meta,
            'current_project': project,
            'has_view_permission': True,
            # Six columns of data entry want the window. With the module
            # sidebar taking ~460px there is not enough left at 1280 for the
            # grid to show Headset and Group without scrolling sideways, and
            # this page is a destination you arrive at from the belt pack list
            # and leave again, not somewhere you navigate onward from.
            'is_nav_sidebar_enabled': False,
        }
        return render(
            request, 'admin/planner/commbeltpack/add_multiple.html', context)

    def get_channels_view(self, request):
        """Return available channels as JSON for the popup"""
        import json
        from django.http import JsonResponse
        
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'channels': []})
        
        channels = CommChannel.objects.filter(project=current_project).order_by('order', 'name')
        channel_list = [{'id': ch.id, 'name': str(ch), 'abbreviation': ch.abbreviation} for ch in channels]
        return JsonResponse({'channels': channel_list})

    def assign_channel_view(self, request):
        """AJAX endpoint to assign a channel to a belt pack channel slot"""
        import json
        from django.http import JsonResponse
        
        if request.method != 'POST':
            return JsonResponse({'error': 'POST required'}, status=405)
        
        try:
            data = json.loads(request.body)
            beltpack_channel_id = data.get('beltpack_channel_id')
            channel_id = data.get('channel_id')  # None means unassign
            
            bp_channel = CommBeltPackChannel.objects.get(id=beltpack_channel_id)
            
            # Verify project access
            current_project = getattr(request, 'current_project', None)
            if bp_channel.beltpack.project != current_project:
                return JsonResponse({'error': 'Access denied'}, status=403)
            
            if channel_id:
                channel = CommChannel.objects.get(id=channel_id, project=current_project)
                bp_channel.channel = channel
                bp_channel.save()
                return JsonResponse({
                    'success': True,
                    'abbreviation': channel.abbreviation,
                    'channel_number': bp_channel.channel_number
                })
            else:
                bp_channel.channel = None
                bp_channel.save()
                return JsonResponse({
                    'success': True,
                    'abbreviation': None,
                    'channel_number': bp_channel.channel_number
                })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    def changelist_view(self, request, extra_context=None):
        """Add summary information grouped by system type"""
        extra_context = extra_context or {}
        # Every column has to be readable at 1024 without scrolling sideways.
        # The filter sidebar is gone (see the change_list template) and the
        # module nav would otherwise still take ~460px of the window, so this
        # page drops it the way the Add multiple grid does.
        extra_context.setdefault('is_nav_sidebar_enabled', False)
        
        # Get current project
        current_project = getattr(request, 'current_project', None)
        
        if current_project:
            # Same function the toggle endpoint answers with, so a freshly
            # loaded page and a page that has been toggled show numbers that
            # were produced the same way.
            counters = self.wireless_counters(current_project)
            wireless_total = counters['total']
            wireless_checked = counters['out']
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
                'wireless_available': counters['avail'],
                'hardwired_total': hardwired_total,
                'hardwired_available': hardwired_total - hardwired_checked,
                'wireless_groups': wireless_groups,
                'hardwired_groups': hardwired_groups,
            })

            self.warn_duplicate_device_numbers(request, current_project)

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
        # Warn at the moment the clash is made, not only next time the list is
        # opened -- this is the save that caused it, and the one the user can
        # still undo from memory.
        #
        # Only when the save keeps the user off the changelist, though
        # ("Save and continue editing", "Save and add another"). A plain Save
        # lands on the list, which warns on its own, and stacking both would
        # show the same warning twice on one screen.
        if '_continue' in request.POST or '_addanother' in request.POST:
            self.warn_duplicate_device_numbers(
                request, obj.project, only=obj.bp_number)
        

    
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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
        # Extract channel_type from input_designation (e.g., '1 4W' -> '4W', 'A 2W' -> '2W')
        channel_type = '4W' if '4W' in input_des else '2W' if '2W' in input_des else '4W'
        
        CommChannel.objects.get_or_create(
            channel_number=channel_num,
            project=project,
            defaults={
                'channel_type': channel_type,
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

        # Issue #44: rf_number is in the admin's readonly_fields so the
        # user has no input box for it, but the model column is NOT NULL
        # with MinValueValidator(1). Without this opt-out, every new row
        # added via "Add another Mic Assignment" fails ModelForm validation
        # and the whole MicSession save is rejected silently. The
        # MicAssignmentInlineFormSet below auto-assigns a value before save.
        if 'rf_number' in self.fields:
            self.fields['rf_number'].required = False

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
    
class MicAssignmentInlineFormSet(forms.BaseInlineFormSet):
    """Issue #44: auto-assign rf_number to MicAssignment rows that the
    user adds via the inline's "Add another" button. The admin marks
    rf_number as readonly so the user can't type one — without this
    every new row fails ModelForm validation and the whole MicSession
    save is silently rejected.

    Existing rows are untouched; new rows get max(existing rf_number)+i+1.
    MicSession.renumber_assignments() in save_formset collapses to 1..N
    and syncs num_mics afterwards.

    save_new_objects is overridden too: Django's default skips extra
    forms whose form fields weren't touched, but the engineer's mental
    model is "click Add another = create a real slot I'll fill in later
    from the rack view". Once clean() has stamped an rf_number on the
    instance, we save the row regardless of has_changed.
    """

    def clean(self):
        super().clean()
        session = self.instance
        if not session or not session.pk:
            return
        existing_max = MicAssignment.objects.filter(session=session).aggregate(
            m=Max('rf_number')
        )['m'] or 0
        next_n = existing_max + 1
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            if not form.instance.pk and not form.instance.rf_number:
                form.instance.rf_number = next_n
                form.cleaned_data['rf_number'] = next_n
                next_n += 1

    def save_new_objects(self, commit=True):
        self.new_objects = []
        for form in self.extra_forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            # Field-level errors → don't try to save (e.g. invalid mic_type).
            if form.errors:
                continue
            # Only save rows that survived clean()'s rf_number assignment.
            if not getattr(form.instance, 'rf_number', None):
                continue
            self.new_objects.append(self.save_new(form, commit=commit))
        if not commit:
            self.saved_forms.extend(self.new_objects)
        return self.new_objects


class MicAssignmentInline(BaseEquipmentInline):
    model = MicAssignment
    form = MicAssignmentForm
    formset = MicAssignmentInlineFormSet
    extra = 0
    # Issue #36: one-click "×" delete in place of Django's default
    # "Delete?" checkbox column. The X posts to mic_assignment_delete
    # and removes the row immediately (no Save required).
    fields = ['rf_number', 'mic_type', 'is_micd', 'is_d_mic', 'notes', 'delete_x']
    ordering = ['rf_number']
    readonly_fields = ['rf_number', 'delete_x']
    can_delete = False

    class Media:
        js = ('admin/js/mic_assignment_delete.js',)

    def delete_x(self, obj):
        if not obj.pk:
            return ''
        return format_html(
            '<a href="#" class="mic-delete-x" data-mic-id="{}" '
            'title="Delete this mic" '
            'style="color:#ff4d4d;text-decoration:none;font-weight:bold;'
            'font-size:18px;line-height:1;padding:2px 8px;">×</a>',
            obj.pk,
        )
    delete_x.short_description = ''

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


class ShowDayAdminForm(forms.ModelForm):
    """Validates the ShowDay (project, date) uniqueness in-form.

    `project` is excluded from the admin form and assigned in save_model, so
    Django's built-in uniqueness check can't cover the unique_together on
    (project, date). Without this, adding a Day for a date that already exists
    in the project raises an IntegrityError → 500 instead of a form error.
    """
    class Meta:
        model = ShowDay
        fields = ['date', 'name', 'is_collapsed', 'order']

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get('date')
        # On edit the instance already carries its project; on add the admin
        # injects request.current_project onto the form as `current_project`.
        project = self.instance.project if self.instance.project_id else getattr(self, 'current_project', None)
        if date and project:
            dupes = ShowDay.objects.filter(project=project, date=date)
            if self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                self.add_error('date', 'A day already exists for this date in this project. '
                                       'Pick a different date, or edit the existing day.')
        return cleaned


class ShowDayAdmin(BaseEquipmentAdmin):
    form = ShowDayAdminForm

    plain_title_plural = "Show Days"
    plain_title = "Show Day"
    list_display = ('date', 'name', 'session_count', 'total_mics', 'mics_used', 'view_day_link')
    list_filter = ('date',)
    search_fields = ('name',)
    ordering = ['date']
    exclude = ['project']

    def get_form(self, request, obj=None, **kwargs):
        """Inject the current project so the form can validate uniqueness on add."""
        form_class = super().get_form(request, obj, **kwargs)
        current_project = getattr(request, 'current_project', None)

        class _ProjectAwareForm(form_class):
            def __init__(self, *args, **inner_kwargs):
                super().__init__(*args, **inner_kwargs)
                self.current_project = current_project

        return _ProjectAwareForm

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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if ProjectMember.objects.filter(user=request.user, role='owner').exists():
            return True
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/presenter_buttons.css',)
        }
    
   



class MicSessionAdmin(BaseEquipmentAdmin):
    list_display = ('name', 'day', 'session_type', 'start_time', 'location', 'mic_usage', 'edit_mics_link')
    list_filter = (
        project_scoped_filter('Day', 'day', ShowDay, ordering='date'),
        'session_type',
    )
    search_fields = ('name', 'location')
    ordering = ['day__date', 'order', 'start_time']
    inlines = [MicAssignmentInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('day', 'name', 'name_color', 'session_type', 'location')
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

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return self.has_module_permission(request)
        return (obj.day.project.owner == request.user or
                ProjectMember.objects.filter(user=request.user, project=obj.day.project).exists())

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return (obj.day.project.owner == request.user or
                ProjectMember.objects.filter(user=request.user, project=obj.day.project, role='editor').exists())
    
    def mic_usage(self, obj):
        stats = obj.get_mic_usage_stats()
        return f"{stats['micd']}/{stats['total']}"
    mic_usage.short_description = "Mics Used"
    
    def edit_mics_link(self, obj):
        # Issue #33: renamed from "Quick Edit" — the link actually opens the
        # full Mic Tracker show view, not an inline edit form.
        url = f'/audiopatch/mic-tracker/?session={obj.id}'
        return format_html('<a href="{}" class="button">Show View</a>', url)
    edit_mics_link.short_description = "Show View"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Update mic assignments if num_mics changed
        if 'num_mics' in form.changed_data:
            obj.create_mic_assignments()

    def save_formset(self, request, form, formset, change):
        # Issue #44: after the inline formset saves (which now auto-
        # assigns rf_number to new rows via MicAssignmentInlineFormSet),
        # collapse the assignments back to 1..N and sync num_mics so a
        # subsequent num_mics-driven create_mic_assignments doesn't
        # delete the row we just added.
        super().save_formset(request, form, formset, change)
        if formset.model is MicAssignment and form.instance and form.instance.pk:
            form.instance.renumber_assignments()


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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if ProjectMember.objects.filter(user=request.user, role='owner').exists():
            return True
        return super().has_delete_permission(request, obj)

    class Media:
        css = {
            'all': ('admin/css/mic_session_buttons.css',)
        }
        js = ('admin/js/mic_tracker_auto_refresh.js',)


class MicAssignmentAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'session': 'day__project', 'group': 'session__day__project'}
    form = MicAssignmentForm
    list_display = ('rf_display', 'session', 'mic_type', 'presenter_display', 'is_micd', 'is_d_mic', 'last_modified')
    list_filter = (
        project_scoped_filter(
            'Day', 'session__day', ShowDay,
            queryset_path='session__day', ordering='date',
        ),
        project_scoped_filter(
            'Session', 'session', MicSession,
            related_project_path='day__project', ordering='day__date',
        ),
        'mic_type', 'is_micd', 'is_d_mic',
    )
    search_fields = ('presenter__name', 'session__name', 'notes')
    list_editable = ('is_micd', 'is_d_mic')
    ordering = ['session__day__date', 'session__order', 'rf_number']
    
    fieldsets = (
        ('Assignment Details', {
            'fields': ('session', 'rf_number', 'mic_type')
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        if ProjectMember.objects.filter(user=request.user, role='owner').exists():
            return True
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/mic_assignment_buttons.css',)
        }

class MicGroupAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'session': 'day__project'}
    list_display = ['name', 'color', 'session']
    list_filter = ['color']
    exclude = ['project']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request, 'current_project') and request.current_project:
            return qs.filter(session__day__project=request.current_project)
        return qs.none()




class MicShowInfoAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'show_day': 'project'}
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)   

    class Media:
        css = {
            'all': ('admin/css/power_distribution_buttons.css',)
        } 



class AmplifierAssignmentAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'distribution_plan': 'project'}
    list_display = [
        'distribution_plan', 'zone', 'amplifier', 'quantity', 
        'duty_cycle', 'phase_assignment', 'calculated_total_current'
    ]



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
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
    list_filter = [
        project_scoped_filter('Show day', 'show_day', ShowDay, ordering='date'),
        'created_at', 'date_generated',
    ]
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)   

    
     

    class Media:
        css = {
            'all': ('admin/css/soundvision_prediction_buttons.css',)
        }

class SpeakerArrayAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'prediction': 'project'}
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
            angle_str = f"→ {cab.angle_to_next}°" if cab.angle_to_next is not None else ""
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
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)
    
    class Media:
        css = {
            'all': ('admin/css/speaker_array_buttons.css',)
        }


class SpeakerCabinetAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'array': 'prediction__project'}
    list_display = ['position_number', 'speaker_model', 'array', 'angle_to_next', 
                   'site_angle', 'panflex_setting']
    list_filter = ['speaker_model', 'panflex_setting']
    search_fields = ['array__source_name', 'speaker_model']
    ordering = ['array', 'position_number']   



    def has_add_permission(self, request):
        """Only editors and owners can add"""
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Only editors and owners can edit"""
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Only editors and owners can delete"""
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj) 
    

    class Media:
        css = {
            'all': ('admin/css/speaker_cabinet_buttons.css',)
        }




# The DarkThemeAdminMixin that used to sit here was never applied to any
# ModelAdmin, and all three files it declared (admin/css/custom.css,
# audiopatch/css/dark_theme.css, audiopatch/js/dark_theme.js) are absent.
# Admin theming lives in planner/static/css/surfaces.css.








    


# ──────────────────────────────────────────────────────────────────
# Multitrack Session Builder admin (Phase 1 of v2.0)
# Subclasses BaseEquipmentAdmin so save_model auto-fills project from
# request.current_project (admin.py:98). Bounces to the custom UI at
# /audiopatch/multitrack/ — the rich editor lives there, not in admin.
# ──────────────────────────────────────────────────────────────────

class MultitrackSessionAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'console': 'project'}
    list_display = ['name', 'console', 'target_daw', 'feed_source', 'updated_at']
    list_filter = ['target_daw', 'feed_source', 'track_order_mode']
    search_fields = ['name', 'console__name']
    fieldsets = (
        ('Session', {
            'fields': ('name', 'console', 'target_daw', 'feed_source',
                       'track_order_mode', 'recorder_capacity', 'notes'),
        }),
    )

    def changelist_view(self, request, extra_context=None):
        """Bounce admin changelist to the custom UI (matches CommConfigAdmin)."""
        from django.shortcuts import redirect
        return redirect('planner:multitrack_dashboard')

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)


class ConsoleImportAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'console': 'project'}
    """Read-mostly audit-history admin for ConsoleImport rows (Phase 2 Console CSV Import).

    Per CONTEXT D-08 / D-09: imports are immutable audit history; every field is
    readonly. Viewer-group users are blocked at all three permission methods,
    mirroring MultitrackSessionAdmin (planner/admin.py:5904-5939).
    """
    list_display = ['console', 'original_filename', 'uploaded_by', 'uploaded_at', 'committed']
    list_filter = [
        'committed',
        project_scoped_filter('Console', 'console', Console),
    ]
    search_fields = ['original_filename', 'console__name']
    readonly_fields = ['console', 'uploaded_by', 'uploaded_at', 'original_filename',
                       'raw_file', 'parsed_sections', 'summary', 'committed']

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)


# ──────────────────────────────────────────────────────────────────
# MultitrackTemplate — Phase 3 (v3.0) admin registration
# ──────────────────────────────────────────────────────────────────
# CONTEXT D-05: owner-scoped via created_by FK (NOT project-scoped).
# CONTEXT specifics line 195: engineers must NOT edit slot lists from
# Django admin — the multitrack module is the source of truth. Slot
# inline is fully read-only (every field readonly, can_delete=False,
# has_add_permission=False). Mirrors ConsoleImportAdmin's readonly
# audit-history pattern (admin.py:5943-5976).
# ──────────────────────────────────────────────────────────────────

class MultitrackTemplateSlotInline(admin.TabularInline):
    """Read-only inline for slots on the MultitrackTemplate admin.

    CONTEXT specifics line 195: engineers must NOT edit slot lists from Django
    admin. The multitrack module is the source of truth for slot data.
    Mirrors ConsoleImportAdmin's readonly approach (admin.py:5943-5975).
    """
    model = MultitrackTemplateSlot
    extra = 0
    can_delete = False
    fields = ('position', 'source_type', 'source_number', 'label_override', 'color_override')
    readonly_fields = ('position', 'source_type', 'source_number', 'label_override', 'color_override')

    def has_add_permission(self, request, obj=None):
        return False


class MultitrackTemplateAdmin(BaseEquipmentAdmin):
    """Read-mostly admin for MultitrackTemplate (Phase 3, v3.0).

    D-05: owner-scoped via created_by FK. NOT project-scoped — the admin sees
    all templates across all users (back-office only).
    """
    list_display = ['name', 'created_by', 'target_daw', 'feed_source', 'slot_count', 'updated_at']
    list_filter = ['target_daw', 'feed_source', 'track_order_mode']
    search_fields = ['name', 'created_by__username']
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MultitrackTemplateSlotInline]

    def slot_count(self, obj):
        return obj.slots.count()
    slot_count.short_description = 'Slots'

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)


    # ==================== REGISTER ALL MODELS ====================
from planner.admin_site import showstack_admin_site


class SourceHardwareOptionAdmin(BaseAdmin):
    list_display = ['label', 'sort_order']
    list_editable = ['sort_order']
    search_fields = ['label']
    ordering = ['sort_order', 'label']

    class Media:
        js = ['admin/js/source_hardware_back_button.js']

    def has_module_permission(self, request):
        return request.user.is_authenticated

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def _user_can_edit(self, request):
        if request.user.is_superuser:
            return True
        if not request.user.is_authenticated:
            return False
        if Project.objects.filter(owner=request.user).exists():
            return True
        return ProjectMember.objects.filter(
            user=request.user, role='editor'
        ).exists()

    def has_add_permission(self, request):
        return self._user_can_edit(request)

    def has_change_permission(self, request, obj=None):
        return self._user_can_edit(request)

    def has_delete_permission(self, request, obj=None):
        return self._user_can_edit(request)


# Register all equipment admin classes
showstack_admin_site.register(Console, ConsoleAdmin)
showstack_admin_site.register(SourceHardwareOption, SourceHardwareOptionAdmin)
showstack_admin_site.register(MultitrackSession, MultitrackSessionAdmin)
showstack_admin_site.register(MultitrackTemplate, MultitrackTemplateAdmin)
showstack_admin_site.register(ConsoleImport, ConsoleImportAdmin)
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
showstack_admin_site.register(MicGroup, MicGroupAdmin)
showstack_admin_site.register(MicShowInfo, MicShowInfoAdmin)
showstack_admin_site.register(AmplifierProfile, AmplifierProfileAdmin)
showstack_admin_site.register(PowerDistributionPlan, PowerDistributionPlanAdmin)
showstack_admin_site.register(AmplifierAssignment, AmplifierAssignmentAdmin)
showstack_admin_site.register(AudioChecklist, AudioChecklistAdmin)  
showstack_admin_site.register(SoundvisionPrediction, SoundvisionPredictionAdmin)
showstack_admin_site.register(SpeakerArray, SpeakerArrayAdmin)
showstack_admin_site.register(SpeakerCabinet, SpeakerCabinetAdmin)


# ============================================================
# COMM CONFIG - Base Station Configuration Editor
# ============================================================
class CommConfigAdmin(BaseEquipmentAdmin):
    """COMM Config admin.

    This was `admin.ModelAdmin` with five permission hooks that each returned
    a bare `request.user.is_staff`, and no `get_queryset` override at all.
    Every invited user is made `is_staff` (accounts/views.py:301), so any
    editor or viewer on any project could open
    `/admin/planner/commconfig/<id>/change/` for *any* tenant and read or
    rewrite their Arcadia/FreeSpeak configuration -- crew names, roles,
    partyline labels, pins. It was the one admin leak that needed no extra
    permissions, and a test pins it shut:
    `InvitedMemberScopingTests.test_editor_cannot_open_another_tenants_comm_config_change_form`.

    Inheriting BaseEquipmentAdmin is the fix rather than hand-written hooks:
    its `get_queryset` filters to `request.current_project` and returns
    `none()` when there is none, and because `ModelAdmin.get_object` runs
    through `get_queryset`, a cross-project change URL 404s. Its permission
    hooks also give the role model (owner/editor can write, viewer is
    read-only) that the `is_staff` checks threw away, and keep the superuser
    short-circuit.
    """

    # The changelist redirects to the user-facing editor, so no list_filter
    # here -- and deliberately not `['project']`, which would render every
    # tenant's project name in the sidebar (see the F5 findings).


    def get_urls(self):
        from django.urls import path as urlpath
        urls = super().get_urls()
        custom_urls = [
            urlpath(
                'comm-config/',
                self.admin_site.admin_view(self.comm_config_redirect),
                name='planner_commconfig_redirect',
            ),
        ]
        return custom_urls + urls

    def comm_config_redirect(self, request):
        from django.shortcuts import redirect
        return redirect('planner:comm_config')

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('planner:comm_config')
showstack_admin_site.register(CommConfig, CommConfigAdmin)


# --- Network Health Monitor Admin ---
#
# All six of these were plain `admin.ModelAdmin` with no get_queryset
# override, so each changelist listed every tenant's rows: device labels, IP
# addresses, port state, and -- worst -- ProjectSNMPConfig.community_string,
# the SNMP credential for another project's switches. Today they are gated by
# model permissions that setup_user_groups does not grant to Editor or Viewer,
# so they were latent rather than live; they become live the moment anyone is
# granted those permissions, which is exactly the kind of footgun to remove
# while it is still cheap.
#
# Each now subclasses BaseEquipmentAdmin, whose get_queryset scopes to
# request.current_project. The three child models reach their project through
# `device`, which BaseEquipmentAdmin resolves via its child_model_paths map
# (extended below for them).
#
# `list_filter` entries naming `project` or `session` are gone: Django's
# RelatedFieldListFilter renders the whole related table in the sidebar
# regardless of get_queryset, so those enumerated every project name. The
# remaining filters are all plain choice fields, which enumerate nothing.

class MonitorSessionAdmin(BaseEquipmentAdmin):
    list_display = ('__str__', 'project', 'started_at', 'ended_at')
    readonly_fields = ('started_at',)

class DiscoveredDeviceAdmin(BaseEquipmentAdmin):
    list_display = ('label', 'ip_address', 'domain', 'last_known_state', 'consecutive_failures', 'is_active', 'project')
    list_filter = ('domain', 'last_known_state', 'is_active')
    search_fields = ('label', 'ip_address')

class PollResultAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'device': 'project', 'session': 'project'}
    list_display = ('device', 'is_reachable', 'latency_ms', 'polled_at')
    list_filter = ('is_reachable',)
    readonly_fields = ('device', 'session', 'polled_at', 'is_reachable', 'latency_ms')

    def has_add_permission(self, request):
        return False  # Append-only — created by run_monitor

    def has_change_permission(self, request, obj=None):
        return False

class DeviceEventAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'device': 'project', 'session': 'project'}
    list_display = ('event_type', 'device', 'occurred_at', 'session')
    list_filter = ('event_type',)
    readonly_fields = ('device', 'session', 'occurred_at', 'event_type', 'details')

    def has_add_permission(self, request):
        return False  # Append-only — created by run_monitor

    def has_change_permission(self, request, obj=None):
        return False

showstack_admin_site.register(MonitorSession, MonitorSessionAdmin)
showstack_admin_site.register(DiscoveredDevice, DiscoveredDeviceAdmin)
showstack_admin_site.register(PollResult, PollResultAdmin)
showstack_admin_site.register(DeviceEvent, DeviceEventAdmin)


class ProjectSNMPConfigAdmin(BaseEquipmentAdmin):
    """Per-project SNMP community string.

    `list_display` puts a credential on screen, so this is the one of the six
    where an unscoped changelist mattered most: it listed every project's SNMP
    community string. `search_fields` is dropped too -- it fed
    `/admin/autocomplete/`, which serves the *remote* admin's get_queryset for
    any FK naming this model.
    """

    list_display = ('project', 'community_string', 'updated_at')


class SwitchPortSnapshotAdmin(BaseEquipmentAdmin):
    project_scoped_fks = {'device': 'project', 'session': 'project'}
    list_display = ('device', 'port_index', 'oper_status', 'speed_mbps', 'bandwidth_pct', 'error_count', 'polled_at')
    list_filter = ('oper_status',)
    readonly_fields = ('device', 'session', 'port_index', 'port_description', 'oper_status', 'speed_mbps', 'bandwidth_pct', 'error_count', 'polled_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


showstack_admin_site.register(ProjectSNMPConfig, ProjectSNMPConfigAdmin)
showstack_admin_site.register(SwitchPortSnapshot, SwitchPortSnapshotAdmin)


# ──────────────────────────────────────────────────────────────────────────────
# Signal Flow Diagrammer (v2.2) — Phase 7
# Mirrors MultitrackSessionAdmin pattern (admin.py:5906-5941).
# Always hidden from sidebar (admin_ordering.py always_hidden set).
# Changelist redirects to /audiopatch/signal-flow/ (plan 03).
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(SignalFlowDiagram, site=showstack_admin_site)
class SignalFlowDiagramAdmin(BaseEquipmentAdmin):
    """Signal Flow Diagram admin — superuser inspection only.

    Changelist redirects to the user-facing list page at /audiopatch/signal-flow/.
    canvas_state is shown as a collapsible JSON display (read-only).
    Always hidden from the sidebar (see admin_ordering.py always_hidden).
    """

    list_display = ['name', 'project', 'updated_at']
    # No list_filter: 'project' would render every tenant's project name
    # in the sidebar (RelatedFieldListFilter ignores get_queryset), and a
    # project filter on a project-scoped changelist filters nothing.
    readonly_fields = ['canvas_state_display', 'version', 'created_at', 'updated_at']
    exclude = ['canvas_state', 'viewport']

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('planner:signal_flow_list')

    def canvas_state_display(self, obj):
        import json
        from django.utils.html import format_html
        pretty = json.dumps(obj.canvas_state, indent=2)
        cell_count = len(obj.canvas_state.get('cells', []))
        return format_html(
            '<details><summary>{} cells</summary>'
            '<pre style="max-height:400px;overflow:auto">{}</pre></details>',
            cell_count, pretty
        )
    canvas_state_display.short_description = 'Canvas State'

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)









