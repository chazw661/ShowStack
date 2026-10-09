# planner/templatetags/custom_tags.py

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def get_range(value):
    """
    Given an integer N, returns range(0, N) so you can do:
       {% for i in some_number|get_range %}
    """
    try:
        n = int(value)
    except (ValueError, TypeError):
        return []
    return range(n)


@register.filter
def add_class(bound_field, css_class):
    """
    Given a BoundField, render its widget with the extra class appended.
    Usage in your template:
        {{ form.console_output|add_class:"w-20 text-center" }}
    """
    widget = bound_field.field.widget
    existing = widget.attrs.get("class", "")
    # append our new class onto any existing ones
    widget.attrs["class"] = (existing + " " + css_class).strip()
    # re-render the field with the updated attrs
    return mark_safe(bound_field.as_widget())

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def chunk(lst, n):
    lst = list(lst)
    return [lst[i:i+n] for i in range(0, len(lst), n)]


@register.simple_tag
def filter_choices(changelist, spec):
    """The choices for one changelist filter.

    `spec.choices(cl)` takes the changelist as an argument, so a template
    cannot call it: Django's engine only calls zero-argument callables. The
    admin's own filter.html gets around this because the `admin_list_filter`
    tag prepares the list for it, but that tag renders the sidebar markup too.
    The Comm Devices list wants Django's filtering with its own compact row of
    dropdowns, so it asks for just the choices.
    """
    return list(spec.choices(changelist))


@register.filter
def photo_url_in(slot, photo_index):
    """``{{ slot|photo_url_in:photo_index }}`` -- the URL a Mic Tracker slot's
    photo zone shows: its presenter's headshot, else (transitional) the slot's
    legacy photo, else ''. See planner.utils.presenter_photos.PhotoIndex."""
    if not slot or photo_index is None:
        return ''
    return photo_index.for_slot(slot)
