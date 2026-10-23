"""Which page is the user on, as a key the help registry understands.

The key is Django's own ``view_name`` for the request -- never a guess from
the path. Every page of an admin model (list, add, change, delete, history)
collapses to that model's changelist key, so one topic covers the whole model
and a topic does not need four keys to follow the user into a change form.
"""

from .topics import TOPICS

_STANDARD_ADMIN_SUFFIXES = ('_add', '_change', '_changelist', '_delete', '_history')


def page_key(request):
    match = getattr(request, 'resolver_match', None)
    if match is None or not match.url_name:
        return ''
    # Application namespaces, not instance ones: the admin site is mounted as
    # instance "showstack_admin" of app "admin", and "admin:" is the name the
    # rest of the code reverses with.
    namespace = ':'.join(match.app_names)
    # ModelAdmin.get_urls() wraps its standard views and sets
    # ``wrapper.model_admin``; custom get_urls() views are wrapped by the
    # admin site instead and keep their own names.
    model_admin = getattr(match.func, 'model_admin', None)
    if model_admin is not None and match.url_name.endswith(_STANDARD_ADMIN_SUFFIXES):
        opts = model_admin.model._meta
        return '{}:{}_{}_changelist'.format(namespace, opts.app_label, opts.model_name)
    return '{}:{}'.format(namespace, match.url_name) if namespace else match.url_name


def topics_for(key):
    """Topics tied to ``key``, in registry order."""
    if not key:
        return []
    return [t for t in TOPICS if key in t.pages]
