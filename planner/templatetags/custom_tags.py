from django import template

register = template.Library()

@register.filter
def in_list(value, arg_list):
    return value in arg_list
