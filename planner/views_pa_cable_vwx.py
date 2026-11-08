"""PA Cable Schedule: import from a Vectorworks worksheet CSV.

Upload shows a preview and writes nothing. The preview form carries the file
back, and Confirm plans it again and writes only if that is still the plan
that was previewed (planner.utils.pa_cable_vwx).
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from planner.models import PACableSchedule, Project
from planner.tenancy import current_project_or_none, edit_rights_required_page
from planner.utils import pa_cable_vwx as vwx
from planner.views import _shared_header_context


def _schedule():
    return redirect(reverse('admin:planner_pacableschedule_changelist'))


def _start_over():
    return redirect(reverse('planner:import_pa_cables_vwx'))


@staff_member_required
@edit_rights_required_page
def import_pa_cables_vwx(request):
    project = current_project_or_none(request)
    if project is None:
        messages.error(request, 'No project selected. Please select a project first.')
        return _schedule()

    context = {'title': 'Import from VWX', 'opts': PACableSchedule._meta, **_shared_header_context(request)}
    if request.method != 'POST':
        return TemplateResponse(request, 'admin/planner/pacableschedule/import_vwx.html', context)

    upload = request.FILES.get('csv_file')
    if upload is None:
        messages.error(request, 'Choose a CSV file to import.')
        return _start_over()
    try:
        text = vwx.read_upload(upload)
        plan = vwx.build_plan(vwx.parse(text), project, upload.name)
    except vwx.VwxFileError as exc:
        messages.error(request, str(exc))
        return _start_over()

    context.update({
        'title': 'Import from VWX: preview',
        'plan': plan,
        'csv_text': text,
        'digest': vwx.digest(plan, project),
    })
    return TemplateResponse(request, 'admin/planner/pacableschedule/import_vwx_preview.html', context)


@staff_member_required
@edit_rights_required_page
@require_POST
def import_pa_cables_vwx_confirm(request):
    project = current_project_or_none(request)
    if project is None:
        messages.error(request, 'No project selected. Please select a project first.')
        return _schedule()

    changed = 'The project or the file changed after the preview, so nothing was imported. Upload it again.'
    try:
        parsed = vwx.parse(request.POST.get('csv_text', ''))
    except vwx.VwxFileError:
        messages.error(request, changed)
        return _start_over()

    with transaction.atomic():
        # One import at a time per project: a double-clicked Confirm then
        # sees the first one's rows and fails the digest.
        Project.objects.select_for_update().get(pk=project.pk)
        plan = vwx.build_plan(parsed, project, request.POST.get('filename', ''))
        if vwx.digest(plan, project) != request.POST.get('digest'):
            messages.error(request, changed)
            return _start_over()
        vwx.apply_plan(plan, project)

    summary = '{} created, {} updated, {} skipped'.format(plan.created, plan.updated, plan.skipped)
    if plan.extension_count:
        summary += ', {} extension{} set'.format(plan.extension_count, '' if plan.extension_count == 1 else 's')
    messages.success(request, summary + '.')
    return _schedule()
