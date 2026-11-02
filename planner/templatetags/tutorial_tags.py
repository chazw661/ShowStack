from django import template

from planner.tutorials import tutorial

register = template.Library()


@register.inclusion_tag('tutorials/_button.html')
def tutorial_button(key, quiet=False):
    """The tutorial button for video ``key``; renders nothing when that video
    has no ID. ``quiet=True`` draws it as a link, for page headers where it
    sits after the real actions. The page also needs ``{% tutorial_assets %}``
    once."""
    return {'video': tutorial(key), 'quiet': quiet}


@register.inclusion_tag('tutorials/_assets.html')
def tutorial_assets():
    """The player's stylesheet and script. No iframe is in the page until a
    button is pressed, so loading these fetches nothing from YouTube."""
    return {}
