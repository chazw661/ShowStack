"""Static files storage.

Hashed filenames (style.css -> style.a1b2c3d4.css) are what stop a browser
serving its cached copy of a stylesheet after a deploy. Whitenoise then serves
the hashed names with a long max-age.

The hazard of manifest storage is that a `{% static %}` or `Media` reference to
a file that is not on disk stops being a quiet 404 and becomes an exception --
a 500 on every page that renders it. That is what broke the previous attempt:
templates and ModelAdmin Media classes between them named eleven files that do
not exist, including one on the public marketing pages.

`manifest_strict = False` is only half of the guard against that happening
again. It suppresses Django's own
`ValueError("Missing staticfiles manifest entry for ...")`, but the fallback it
takes instead is `hashed_name()`, which hashes the file off disk and raises
`ValueError("The file ... could not be found with ...")` when it is not there.
For the case we actually care about -- a name no deploy has ever produced -- the
page still 500s. So the fallback is done here instead: the name resolves to its
own unhashed URL, which 404s for that one asset and leaves the rest of the page
standing.

A 404 nobody sees is its own trap, so every name that falls back is logged once
per process. Grep Railway logs for "static asset missing from manifest".
"""

import logging

from whitenoise.storage import CompressedManifestStaticFilesStorage

logger = logging.getLogger(__name__)


class ForgivingManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Hashed, compressed static files that degrade instead of raising."""

    # Suppresses the "Missing staticfiles manifest entry" branch so the
    # hashed_name() fallback below is the one that runs.
    manifest_strict = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Names already reported. A stylesheet named by forty ModelAdmins
        # should log one line per process, not one per page view.
        self._missing_reported = set()

    def stored_name(self, name):
        """Resolve `name` to its hashed form, or to itself if it cannot be.

        Both ValueErrors raised below this point mean the same thing to a
        request -- this asset cannot be resolved -- and neither is worth a 500:

        * "The file ... could not be found with ..." -- absent from the
          manifest and absent from STATIC_ROOT. The ordinary case: a reference
          to a file that was deleted or never existed.
        * "The name ... could not be hashed with ..." -- max_post_process_passes
          exhausted, meaning the intermediate files on disk disagree.
        """
        try:
            return super().stored_name(name)
        except ValueError as exc:
            if name not in self._missing_reported:
                self._missing_reported.add(name)
                logger.warning(
                    "static asset missing from manifest, serving it unhashed "
                    "(it will 404): %s -- %s. Either add the file under a "
                    "STATICFILES_DIRS path or drop the reference that names "
                    "it; `collectstatic` on the next deploy lists it too.",
                    name,
                    exc,
                )
            # The unhashed name: a 404 for this one asset rather than a 500
            # for every page that renders it.
            return name
