from django import forms
from planner.models import Invitation, Project
from django.contrib.auth.models import User


class InviteUserForm(forms.ModelForm):
    """
    Form for project owners to invite users via email.
    """
    class Meta:
        model = Invitation
        fields = ['email', 'role']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'user@example.com'
            }),
            'role': forms.Select(attrs={
                'class': 'form-control'
            }),
        }
    
    def __init__(self, *args, project=None, invited_by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.invited_by = invited_by
        
        # Customize help text
        self.fields['email'].help_text = 'Enter the email address of the person you want to invite.'
        self.fields['role'].help_text = 'Editor: Can edit existing equipment. Viewer: Read-only access.'
    
    def clean_email(self):
        """Validate email and check for duplicates"""
        email = self.cleaned_data.get('email').lower()
        
        if not self.project:
            raise forms.ValidationError('Project not specified.')
        
        # Check if user is already a member
        user = User.objects.filter(email__iexact=email).first()
        if user:
            from planner.models import ProjectMember
            if ProjectMember.objects.filter(project=self.project, user=user).exists():
                raise forms.ValidationError('This user is already a member of this project.')
        
        # Check if there's already a pending invitation
        if Invitation.objects.filter(
            project=self.project,
            email__iexact=email,
            status='pending'
        ).exists():
            raise forms.ValidationError('An invitation has already been sent to this email address.')
        
        return email
    
    def save(self, commit=True):
        """Create invitation with project and invited_by"""
        invitation = super().save(commit=False)
        invitation.project = self.project
        invitation.invited_by = self.invited_by
        invitation.email = invitation.email.lower()
        
        if commit:
            invitation.save()
        
        return invitation