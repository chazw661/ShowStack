"""Label branding: the project's colours and logos for the beltpack labels.

Everything is the current project's (session-scoped, no ids in URLs). Any
member may see the page, the preview and the logos; only someone who may
edit the project may change them, refused before the body is read.

The rules themselves -- contrast, B&W greys, which logo fits -- live in
planner.utils.labels.brand and layout; this module only reads and writes.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from planner.models import ProjectLogo
from planner.tenancy import can_edit_current_project, edit_rights_required_page
from planner.tenancy import current_project_or_none as _scoped_project
from planner.utils.labels import brand as B
from planner.utils.labels import layout as L
from planner.utils.labels.stock import DEFAULT_STOCK, STOCKS


def _back():
    return redirect('planner:project_branding')


def logo_notes(brand, stock):
    """{kind: [(level, message)]} for the logos on the page: what prints
    where, and why a logo will not print or will look soft."""
    notes = {kind: [] for kind in B.LOGO_KINDS}
    full = brand.full_logo_kind
    widest, widest_part = L.max_logo_aspect(stock), L.max_logo_aspect(stock, part=True)
    mark = brand.logo('mark')
    for logo in brand.logos:
        out = notes[logo.kind]
        dpi = logo.dpi_at(L.LOGO_HEIGHT)
        if dpi < B.MIN_PRINT_DPI:
            out.append(('warn', 'Prints at {:.0f} dpi at 8 mm high, below {}: it may look soft. '
                                'Upload a larger image.'.format(dpi, B.MIN_PRINT_DPI)))
        if logo.kind == 'mark':
            if mark_contrast_low(brand, logo):
                out.append(('warn', 'Low contrast against the background (under {:.0f}:1): '
                                    'the mark may barely show.'.format(B.MARK_MIN_CONTRAST)))
            if logo.aspect > widest:
                out.append(('warn', 'Too wide for the header at 8 mm high (at most {:.2f}:1), '
                                    'so no logo prints.'.format(widest)))
            continue
        if logo.kind != full:
            out.append(('info', 'Not used: the background is {}, so the logo for {} backgrounds '
                                'prints.'.format('dark' if brand.text_white else 'light',
                                                 'dark' if brand.text_white else 'light')))
            continue
        instead = 'the mark prints instead' if mark else 'no logo prints (upload a mark)'
        if logo.aspect > widest:
            out.append(('warn', 'Too wide for the header at 8 mm high: {:.2f}:1 against at most '
                                '{:.2f}:1, so {}.'.format(logo.aspect, widest, instead)))
        elif logo.aspect > widest_part:
            out.append(('info', 'On a pack\'s continuation labels ("1/2") there is room for '
                                '{:.2f}:1, so {} there.'.format(widest_part, instead)))
        else:
            out.append(('ok', 'Prints top-right on every label.'))
    return notes


def mark_contrast_low(brand, logo):
    from planner.utils.labels.palette import mean_luminance

    if not logo.content:
        return False
    lum = mean_luminance(logo.content)
    return lum is not None and B.contrast(lum, brand.bg_luminance) < B.MARK_MIN_CONTRAST


@staff_member_required
def project_branding(request):
    project = _scoped_project(request)
    if project is None:
        return redirect('planner:mic_tracker')
    stock = STOCKS[DEFAULT_STOCK]
    brand = B.brand_for(project)
    rows = {row.kind: row for row in ProjectLogo.objects.filter(project=project)
            .only('kind', 'sha256', 'width', 'height')}
    notes = logo_notes(brand, stock)
    logos = [{
        'kind': kind, 'title': title, 'row': rows.get(kind), 'notes': notes[kind],
    } for kind, title in B.LOGO_KIND_CHOICES]
    _, separated = brand.bw_accents()
    accents = list(brand.accents) + [''] * (B.MAX_ACCENTS - len(brand.accents))
    from planner.views import _shared_header_context
    return render(request, 'planner/project_branding.html', {
        **_shared_header_context(request),
        'project': project,
        'brand': brand,
        'accents': accents,
        'styles': B.ACCENT_STYLE_CHOICES,
        'logos': logos,
        'can_edit': can_edit_current_project(request),
        'bw_separated': separated,
        'max_aspect': L.max_logo_aspect(stock),
        'default_bg_k': B.DEFAULT_BG_K,
    })


@staff_member_required
@require_POST
@edit_rights_required_page
def branding_save(request):
    project = _scoped_project(request)
    if project is None:
        raise Http404('No project.')
    try:
        bg = request.POST.get('bg_color', '').strip()
        bg = B.parse_hex(bg) if bg else ''
        accents = B.parse_accents(request.POST.getlist('accent'))
        style = B.parse_style(request.POST.get('accent_style', 'none'))
    except B.BrandError as error:
        messages.error(request, str(error))
        return _back()
    project.brand_bg_color = bg
    project.brand_accent_colors = accents
    project.brand_accent_style = style
    project.save(update_fields=['brand_bg_color', 'brand_accent_colors',
                                'brand_accent_style', 'updated_at'])
    messages.success(request, 'Label branding saved.')
    return _back()


@staff_member_required
@require_POST
@edit_rights_required_page
def branding_logo_upload(request):
    from planner.utils.image_upload import ImageRejected, read_upload_capped

    project = _scoped_project(request)
    if project is None:
        raise Http404('No project.')
    kind = request.POST.get('kind')
    upload = request.FILES.get('logo')
    if kind not in B.LOGO_KINDS or upload is None:
        messages.error(request, 'Choose a PNG or JPEG file to upload.')
        return _back()
    try:
        ProjectLogo.store(project, kind, read_upload_capped(upload), request.user)
    except ImageRejected as error:
        messages.error(request, '{}: {}.'.format(dict(B.LOGO_KIND_CHOICES)[kind], error))
        return _back()
    messages.success(request, '{} uploaded.'.format(dict(B.LOGO_KIND_CHOICES)[kind]))
    return _back()


@staff_member_required
@require_POST
@edit_rights_required_page
def branding_logo_delete(request):
    project = _scoped_project(request)
    if project is None:
        raise Http404('No project.')
    kind = request.POST.get('kind')
    if kind in B.LOGO_KINDS:
        ProjectLogo.objects.filter(project=project, kind=kind).delete()
        messages.success(request, '{} removed.'.format(dict(B.LOGO_KIND_CHOICES)[kind]))
    return _back()


@staff_member_required
@require_GET
def branding_logo(request):
    """A logo image, ?kind=on_dark|on_light|mark. Versioned by ?v=<sha>,
    so it may be cached for good."""
    project = _scoped_project(request)
    kind = request.GET.get('kind')
    if project is None or kind not in B.LOGO_KINDS:
        raise Http404('No logo.')
    row = ProjectLogo.objects.filter(project=project, kind=kind).first()
    if row is None:
        raise Http404('No logo.')
    response = HttpResponse(bytes(row.content), content_type=row.content_type)
    response['Cache-Control'] = 'private, max-age=31536000, immutable'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _preview_brand(request, saved):
    """The saved brand with any of bg / accent / accent_style from the query
    string laid over it, so the preview follows unsaved edits. A value that
    does not parse is ignored, not an error."""
    import dataclasses

    changes = {}
    if 'bg' in request.GET:
        try:
            bg = request.GET['bg'].strip()
            changes['bg'] = B.parse_hex(bg) if bg else ''
        except B.BrandError:
            pass
    if 'accent' in request.GET or 'accents' in request.GET:
        try:
            changes['accents'] = tuple(B.parse_accents(request.GET.getlist('accent')))
        except B.BrandError:
            pass
    if 'accent_style' in request.GET:
        try:
            changes['accent_style'] = B.parse_style(request.GET['accent_style'])
        except B.BrandError:
            pass
    return dataclasses.replace(saved, **changes)


@staff_member_required
@require_GET
@xframe_options_sameorigin
def branding_preview_pdf(request):
    from planner.utils.labels.render import render_preview_pdf

    project = _scoped_project(request)
    if project is None:
        raise Http404('No project.')
    brand = _preview_brand(request, B.brand_for(project))
    response = HttpResponse(render_preview_pdf(brand, STOCKS[DEFAULT_STOCK]),
                            content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="ShowStack-label-branding-preview.pdf"'
    response['Cache-Control'] = 'no-store'
    return response


@staff_member_required
@require_GET
def branding_suggest_accents(request):
    """{"accents": [...], "source": kind} from the stored logo with the most
    colour in it: the on-light logo, else the mark, else the on-dark one."""
    from planner.utils.labels.palette import suggest_accents

    project = _scoped_project(request)
    if project is None:
        raise Http404('No project.')
    try:
        bg = B.parse_hex(request.GET.get('bg', '')) if request.GET.get('bg') else None
    except B.BrandError:
        bg = None
    rows = {row.kind: row for row in ProjectLogo.objects.filter(project=project)}
    for kind in ('on_light', 'mark', 'on_dark'):
        if kind in rows:
            return JsonResponse({'accents': suggest_accents(bytes(rows[kind].content), bg),
                                 'source': kind})
    return JsonResponse({'accents': [], 'source': None,
                         'error': 'Upload a logo first: the colours come from it.'})
