from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import WaitlistSignup, ContactSubmission


class WaitlistForm(forms.ModelForm):
    """
    Simple waitlist signup form.
    """
    class Meta:
        model = WaitlistSignup
        fields = ['email', 'name', 'company', 'role']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'you@company.com',
                'required': True,
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Your name',
            }),
            'company': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Company name',
            }),
            'role': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., A1, Production Manager',
            }),
        }


class ContactForm(forms.ModelForm):
    """
    Contact form for inquiries.
    """
    class Meta:
        model = ContactSubmission
        fields = ['name', 'email', 'company', 'inquiry_type', 'message']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Your name',
                'required': True,
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'you@company.com',
                'required': True,
            }),
            'company': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Company name (optional)',
            }),
            'inquiry_type': forms.Select(attrs={
                'class': 'form-input',
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'How can we help?',
                'rows': 5,
                'required': True,
            }),
        }


class RegistrationForm(UserCreationForm):
    """
    User registration form with additional fields.
    """
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'you@company.com',
        })
    )
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'First name',
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Last name',
        })
    )
    company = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Company name (optional)',
        })
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Choose a username',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'Password',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'Confirm password',
        })
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user
