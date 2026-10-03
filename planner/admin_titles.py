"""Plain, user-facing page titles for every admin page.

Django names its own pages after the database operation: "Select Console to
change", "Change I/O Device", "Add Comm Belt Pack". ShowStack's admin *is* the
product, so crew see that wording -- and it reads as somebody else's tool.

`PlainTitlesMixin` rewrites the three titles Django generates:

    changelist   "Select Console to change"  -> "Consoles"
    change form  "Change I/O Device"         -> "Y001 A2 3224"   (the object)
    add form     "Add Comm Belt Pack"        -> "New Belt Pack"

The mixin is applied once, in `ShowStackAdminSite.register`, so it covers every
registered model without touching the ~6000 lines of admin.py. A ModelAdmin can
override the wording for its own model with `plain_title` / `plain_title_plural`
-- that keeps the sidebar (which reads `Meta.verbose_name_plural`) untouched, so
changing a page heading does not need a model change or a migration.
"""
from django.utils.text import capfirst


class PlainTitlesMixin:
    """Replace Django's operation-named admin page titles with plain ones."""

    # No `plain_title = None` class defaults here on purpose: the mixin sits
    # *ahead* of the ModelAdmin in the MRO, so a default defined here would
    # shadow the value the ModelAdmin sets. Read them off the instance instead.

    def _plain_title_plural(self):
        return getattr(self, "plain_title_plural", None) or capfirst(
            self.opts.verbose_name_plural
        )

    def _plain_title(self):
        return getattr(self, "plain_title", None) or capfirst(self.opts.verbose_name)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        # Redirects (and anything that is not a TemplateResponse) have no
        # context to rewrite -- several admins here return one.
        context = getattr(response, "context_data", None)
        if context is None:
            return response
        title = self._plain_title_plural()
        context["title"] = title
        context["subtitle"] = None
        # The ChangeList carries its own copy, used by the pagination summary.
        changelist = context.get("cl")
        if changelist is not None:
            changelist.title = title
        return response

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        # Called after `extra_context` has been merged, so this is the last
        # word on the heading -- including for admins that already set their
        # own title (ConsoleAdmin does, with the same value).
        if add:
            context["title"] = "New %s" % self._plain_title()
        elif obj is not None:
            # The object's own name is what the engineer is looking for here;
            # "Change I/O Device" tells them nothing they didn't know.
            context["title"] = str(obj)
        else:
            context["title"] = self._plain_title()
        # Django puts str(obj) in the subtitle, which would now repeat the
        # heading verbatim.
        context["subtitle"] = None
        return super().render_change_form(request, context, add, change, form_url, obj)


def with_plain_titles(admin_class):
    """Return `admin_class` with `PlainTitlesMixin` mixed in ahead of it.

    Returns the class untouched if it already has the mixin, so re-registering
    a model cannot stack it twice.
    """
    if issubclass(admin_class, PlainTitlesMixin):
        return admin_class
    return type(admin_class)(
        admin_class.__name__,
        (PlainTitlesMixin, admin_class),
        {
            "__module__": admin_class.__module__,
            "__doc__": admin_class.__doc__,
            # ModelAdmin's metaclass regenerates `media` for every new class,
            # and it would find the *inherited* `class Media` and add those
            # assets a second time. An empty Media of our own means the
            # generated property falls through to `admin_class.media` as-is.
            "Media": type("Media", (), {}),
        },
    )
