"""Static files storage.

Hashed filenames (style.css -> style.a1b2c3d4.css) are what stop a browser
serving its cached copy of a stylesheet after a deploy. Whitenoise then serves
the hashed names with a long max-age.

The hazard of manifest storage is that a `{% static %}` or `Media` reference to
a file that is not on disk stops being a quiet 404 and becomes an exception --
a 500 on every page that renders it. That is what broke the previous attempt:
templates and ModelAdmin Media classes between them named eleven files that do
not exist, including one on the public marketing pages.

Those references are fixed, but `manifest_strict = False` keeps a future
mistake proportionate: an unknown name falls back to its unhashed URL, which
404s for that one asset instead of taking the page down. Missing files still
show up in the deploy log, where collectstatic reports them.
"""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Hashed, compressed static files that degrade instead of raising."""

    # A name absent from the manifest resolves to itself rather than raising
    # ValueError("Missing staticfiles manifest entry for ...").
    manifest_strict = False
