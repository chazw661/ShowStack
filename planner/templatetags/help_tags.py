from urllib.parse import urlencode

from django import template
from django.urls import reverse

from planner.help.context import page_key

register = template.Library()


@register.simple_tag(takes_context=True)
def help_href(context):
    """URL of the help page, led by the topics for the page being rendered."""
    url = reverse('help:index')
    request = context.get('request')
    key = page_key(request) if request is not None else ''
    if key:
        url += '?' + urlencode({'for': key})
    return url
