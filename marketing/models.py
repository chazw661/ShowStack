from django.db import models
from django.utils import timezone


class WaitlistSignup(models.Model):
    """
    Collect email signups for launch waitlist.
    """
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=100, blank=True)
    company = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=100, blank=True, help_text="e.g., A1, Audio Engineer, Production Manager")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Waitlist Signup"
        verbose_name_plural = "Waitlist Signups"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.email} ({self.created_at.strftime('%Y-%m-%d')})"


class ContactSubmission(models.Model):
    """
    Contact form submissions.
    """
    INQUIRY_TYPES = [
        ('general', 'General Inquiry'),
        ('demo', 'Request a Demo'),
        ('support', 'Support'),
        ('partnership', 'Partnership'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=100)
    email = models.EmailField()
    company = models.CharField(max_length=100, blank=True)
    inquiry_type = models.CharField(max_length=20, choices=INQUIRY_TYPES, default='general')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    responded = models.BooleanField(default=False)
    responded_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Internal notes about this inquiry")
    
    class Meta:
        verbose_name = "Contact Submission"
        verbose_name_plural = "Contact Submissions"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.inquiry_type} ({self.created_at.strftime('%Y-%m-%d')})"
    
    def mark_responded(self):
        self.responded = True
        self.responded_at = timezone.now()
        self.save()
