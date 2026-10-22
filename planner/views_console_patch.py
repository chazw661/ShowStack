"""Console page Patch cell: the picker's one endpoint.

GET  -> the picker for one channel (devices, ports, current patch, ``state``)
POST -> patch or unpatch a port, JSON body
        {"action": "patch"|"unpatch", "port": <pk>, "state": "...",
         "mode": "replace"|"add", "name": "<typed in the row, unsaved>"}

Both answer with the channel's fresh cell and the free-ports block so the page
can swap exactly those two in place -- the console form is never submitted, so
unsaved edits elsewhere on the page survive. A refused write (409 stale/taken,
400 choose, ...) carries the same fresh state, and nothing was written.

Owner / editor of the CURRENT project only (``_edit_rights_required``, #121's
gate for JSON endpoints); a viewer gets 403 before anything is read. The
channel and the port are looked up inside the current project, so another
show's ids are 404. Rules: planner/utils/console_patch_edit.py.
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from planner.tenancy import current_project_or_none
from planner.utils import console_patch_edit as edit
from planner.views import _edit_rights_required


@require_http_methods(['GET', 'POST'])
@_edit_rights_required
def console_patch(request, kind, pk):
    project = current_project_or_none(request)
    if project is None or kind not in edit.KINDS:
        return JsonResponse({'error': 'not_found'}, status=404)

    if request.method == 'GET':
        channel = edit.load_channel(kind, pk, project)
        if channel is None:
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse(edit.response_payload(kind, pk, project, channel))

    try:
        body = json.loads(request.body or b'{}')
        port_pk = int(body.get('port'))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'bad_request', 'message': 'Bad request.'}, status=400)
    try:
        edit.apply(kind, pk, project,
                   action=body.get('action'), port_pk=port_pk,
                   state=str(body.get('state') or ''), mode=body.get('mode') or '',
                   name=str(body.get('name') or ''))
    except edit.PatchError as err:
        payload = {'error': err.code, 'message': err.message}
        if err.status in (409, 400):
            payload.update(edit.response_payload(kind, pk, project))
        return JsonResponse(payload, status=err.status)
    payload = edit.response_payload(kind, pk, project)
    payload['ok'] = True
    return JsonResponse(payload)
