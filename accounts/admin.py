from django.contrib import admin

from planner.models import Project, ProjectMember, Invitation, UserProfile 
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin


# ======================== PROJECT SYSTEM ADMIN ========================


class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'show_date', 'venue', 'get_member_count', 'updated_at', 'is_archived']
    list_filter = ['is_archived', 'show_date', 'owner']
    search_fields = ['name', 'venue', 'client']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        ('Project Details', {
            'fields': ['name', 'owner', 'show_date', 'venue', 'client']
        }),
        ('Notes', {
            'fields': ['notes'],
            'classes': ['collapse']
        }),
        ('Status', {
            'fields': ['is_archived', 'created_at', 'updated_at']
        }),
    ]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Show projects owned by user or where they're a member
        return qs.filter(owner=request.user) | qs.filter(projectmember__user=request.user)


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 1
    fields = ['user', 'role', 'invited_at', 'invited_by']
    readonly_fields = ['invited_at', 'invited_by']



class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'role', 'invited_by', 'invited_at']
    list_filter = ['role', 'invited_at']
    search_fields = ['project__name', 'user__username', 'user__email']



class InvitationAdmin(admin.ModelAdmin):
    list_display = ['email', 'project', 'role', 'status', 'invited_by', 'invited_at']
    list_filter = ['status', 'role', 'invited_at']
    search_fields = ['email', 'project__name']
    readonly_fields = ['token', 'invited_at', 'accepted_at']
    
    fieldsets = [
        ('Invitation Details', {
            'fields': ['project', 'email', 'role', 'invited_by']
        }),
        ('Status', {
            'fields': ['status', 'token', 'invited_at', 'accepted_at']
        }),
    ]
    
    def get_readonly_fields(self, request, obj=None):
        """Make fields readonly after creation"""
        if obj:  # Editing existing invitation
            return self.readonly_fields + ('project', 'email', 'invited_by')
        return self.readonly_fields



class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'account_type', 'can_create_projects', 'subscription_start', 'subscription_end']
    list_filter = ['account_type', 'can_create_projects']
    search_fields = ['user__username', 'user__email']
    
    fieldsets = [
        ('User Information', {
            'fields': ['user']
        }),
        ('Account Settings', {
            'fields': ['account_type', 'can_create_projects']
        }),
        ('Subscription', {
            'fields': ['subscription_start', 'subscription_end']
        }),
    ]


# ==================== REGISTER ALL MODELS ====================
from planner.admin_site import showstack_admin_site
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin


# Register User with our custom admin
showstack_admin_site.register(User, BaseUserAdmin)

# Register accounts models with their admin classes
showstack_admin_site.register(Project, ProjectAdmin)
showstack_admin_site.register(ProjectMember, ProjectMemberAdmin)
showstack_admin_site.register(Invitation, InvitationAdmin)
showstack_admin_site.register(UserProfile, UserProfileAdmin)