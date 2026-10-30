import logging

from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import WaitlistForm, ContactForm, RegistrationForm
from .models import WaitlistSignup

logger = logging.getLogger(__name__)


@login_not_required
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


@login_not_required
def features(request):
    """
    Features page - detailed breakdown of capabilities.
    """
    return render(request, 'marketing/features.html')


@login_not_required
def pricing(request):
    """
    Pricing page with plan comparison.
    """
    return render(request, 'marketing/pricing.html')


@login_not_required
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


def _invitation_from(token):
    """The Invitation a signup link carries (``?invite=<token>``), or None."""
    from planner.models import Invitation
    try:
        return Invitation.objects.select_related('project').get(token=token)
    except (Invitation.DoesNotExist, ValidationError, ValueError):
        return None


@login_not_required
def register(request):
    """
    User registration page.

    Arriving from an invitation (the preview page's "Create Free Account"
    passes the token as ``invite``), a signup with the invited address is
    accepted on the spot: the account is logged in and opens on the invited
    project with the invited role. Every other signup -- no token, an
    expired or used one, or a different address -- is a plain free account
    with no projects.
    """
    from accounts.views import landing_url

    if request.user.is_authenticated:
        return redirect(landing_url(request))

    token = request.POST.get('invite') or request.GET.get('invite')
    invitation = _invitation_from(token) if token else None
    if invitation is not None and not invitation.is_valid():
        if request.method == 'GET':
            messages.warning(
                request,
                'This invitation has expired or has already been used. You can still '
                'create an account; ask the project owner to send you a new invitation.')
        invitation = None

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        terms_accepted = request.POST.get('terms')
        if not terms_accepted:
            messages.error(request, 'You must accept the Terms of Service and Privacy Policy to create an account.')
            return render(request, 'marketing/register.html', {'form': form, 'invitation': invitation})
        if form.is_valid():
            # D-11 (Phase 6): form.save() + auto-claim are atomic so a claim failure
            # rolls back the User row cleanly and lets the user re-register.
            from planner.crew import claim_pending_crew_memberships
            from accounts.views import accept_invitation_for, send_crew_added_email
            accepted = False
            with transaction.atomic():
                user = form.save()
                # D-07: inline call (no Django signals). Rebinds pending CrewMember
                # rows and materializes ProjectMember rows for every project the crew
                # has been bulk-added to (D-09 via CrewProjectAdd).
                new_pms = claim_pending_crew_memberships(user)
                if invitation is not None:
                    accepted = accept_invitation_for(user, invitation)

            # D-10/D-11: email sends happen OUTSIDE the atomic block — a Resend
            # hiccup must not roll back the user account. Log + swallow per row.
            for pm in new_pms:
                try:
                    send_crew_added_email(pm, request)
                except Exception:
                    logger.exception(
                        "Crew-added email failed on register for %s",
                        getattr(pm.user, 'email', '<unknown>'),
                    )

            if accepted:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                request.session['current_project_id'] = invitation.project_id
                messages.success(
                    request,
                    f'Welcome to {invitation.project.name}! You have been added as '
                    f'{invitation.get_role_display()}.')
                return redirect(landing_url(request))

            if invitation is not None:
                messages.warning(
                    request,
                    f'You signed up with a different email address from the one the '
                    f'invitation to {invitation.project.name} was sent to, so you have not '
                    f'been added to it. Ask the project owner to invite {user.email}.')

            # Auto-assign to Viewer group
            from django.contrib.auth.models import Group
            try:
                viewer_group = Group.objects.get(name='Viewer')
                user.groups.add(viewer_group)
            except Group.DoesNotExist:
                pass
            # Don't log them in yet — send to the registered page
            return redirect('marketing:pending')
        return render(request, 'marketing/register.html', {'form': form, 'invitation': invitation})
    else:
        initial = {'email': invitation.email} if invitation is not None else None
        form = RegistrationForm(initial=initial)

    return render(request, 'marketing/register.html', {'form': form, 'invitation': invitation})


@login_not_required
def user_login(request):
    """
    User login page.
    """
    from accounts.views import landing_url

    if request.user.is_authenticated:
        return redirect(landing_url(request))
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                        next_url, allowed_hosts={request.get_host()},
                        require_https=request.is_secure()):
                    return redirect(next_url)
                return redirect(landing_url(request))
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    
    return render(request, 'marketing/login.html', {'form': form})


@login_not_required
def user_logout(request):
    """
    Log out and redirect to home.
    """
    logout(request)
    messages.info(request, "You've been logged out.")
    return redirect('marketing:home')


@login_not_required
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


@login_not_required
def about(request):
    """
    About page.
    """
    return render(request, 'marketing/about.html')

@login_not_required
def pending(request):
    """
    Post-registration page for a plain signup (no invitation).
    """
    return render(request, 'marketing/pending.html')


@login_not_required
def privacy(request):
    """
    Privacy policy page.
    """
    return render(request, 'marketing/privacy.html')


@login_not_required
def terms(request):
    """
    Terms of service page.
    """
    return render(request, 'marketing/terms.html')
