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