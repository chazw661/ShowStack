"""Absolute links meant to be shared: never the *.railway.app host."""

from django.conf import settings


def public_url(path, request=None):
    """``path`` on the host the user is on, unless that is a Railway host.

    Local dev (localhost, a LAN address) keeps its own host so the link works
    there; production and anything reached through *.railway.app get
    settings.SITE_URL (https://showstack.io).
    """
    if request is not None:
        host = request.get_host().split(':')[0].lower()
        if not (host == 'railway.app' or host.endswith('.railway.app')):
            return request.build_absolute_uri(path)
    return settings.SITE_URL + path
