from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .forms import WaitlistForm, ContactForm, RegistrationForm
from .models import WaitlistSignup


def home(request):
    """
    Landing page / homepage.
    """
    # Handle waitlist form submission
    if request.method == 'POST':
        form = WaitlistForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "You're on the list! We'll be in touch soon.")
            return redirect('marketing:home')
        else:
            if 'email' in form.errors and 'unique' in str(form.errors['email']):
                messages.info(request, "You're already on the waitlist!")
            else:
                messages.error(request, "Please check your information and try again.")
    else:
        form = WaitlistForm()
    
    return render(request, 'marketing/home.html', {'waitlist_form': form})


def features(request):
    """
    Features page - detailed breakdown of capabilities.
    """
    return render(request, 'marketing/features.html')


def pricing(request):
    """
    Pricing page with plan comparison.
    """
    return render(request, 'marketing/pricing.html')


def contact(request):
    """
    Contact page.
    """
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thanks for reaching out! We'll get back to you soon.")
            return redirect('marketing:contact')
    else:
        form = ContactForm()
    
    return render(request, 'marketing/contact.html', {'form': form})


def register(request):
    """
    User registration page.
    """
    if request.user.is_authenticated:
        return redirect('admin:index')
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to ShowStack, {user.first_name}!")
            return redirect('admin:index')
    else:
        form = RegistrationForm()
    
    return render(request, 'marketing/register.html', {'form': form})


def user_login(request):
    """
    User login page.
    """
    if request.user.is_authenticated:
        return redirect('admin:index')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'admin:index')
                return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    
    return render(request, 'marketing/login.html', {'form': form})


def user_logout(request):
    """
    Log out and redirect to home.
    """
    logout(request)
    messages.info(request, "You've been logged out.")
    return redirect('marketing:home')


@require_POST
def waitlist_ajax(request):
    """
    AJAX endpoint for waitlist signup.
    """
    form = WaitlistForm(request.POST)
    if form.is_valid():
        form.save()
        return JsonResponse({'success': True, 'message': "You're on the list!"})
    else:
        if 'email' in form.errors:
            return JsonResponse({'success': False, 'message': "This email is already on the waitlist."})
        return JsonResponse({'success': False, 'message': "Please enter a valid email."})


def about(request):
    """
    About page.
    """
    return render(request, 'marketing/about.html')


def privacy(request):
    """
    Privacy policy page.
    """
    return render(request, 'marketing/privacy.html')


def terms(request):
    """
    Terms of service page.
    """
    return render(request, 'marketing/terms.html')
