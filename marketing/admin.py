from django.contrib import admin
from django.utils import timezone
from .models import WaitlistSignup, ContactSubmission


@admin.register(WaitlistSignup)
class WaitlistSignupAdmin(admin.ModelAdmin):
    list_display = ['email', 'name', 'company', 'role', 'created_at']
    list_filter = ['created_at']
    search_fields = ['email', 'name', 'company']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    def has_add_permission(self, request):
        # Signups come from the website, not admin
        return False


@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'inquiry_type', 'created_at', 'responded']
    list_filter = ['inquiry_type', 'responded', 'created_at']
    search_fields = ['name', 'email', 'company', 'message']
    readonly_fields = ['name', 'email', 'company', 'inquiry_type', 'message', 'created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Submission Details', {
            'fields': ('name', 'email', 'company', 'inquiry_type', 'message', 'created_at')
        }),
        ('Response Tracking', {
            'fields': ('responded', 'responded_at', 'notes')
        }),
    )
    
    actions = ['mark_as_responded']
    
    @admin.action(description="Mark selected as responded")
    def mark_as_responded(self, request, queryset):
        count = queryset.update(responded=True, responded_at=timezone.now())
        self.message_user(request, f"{count} submission(s) marked as responded.")
    
    def has_add_permission(self, request):
        # Submissions come from the website, not admin
        return False
