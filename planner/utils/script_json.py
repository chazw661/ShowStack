"""JSON to write inside a <script> element with ``|safe``.

Plain ``json.dumps`` leaves ``<``, ``>`` and ``&`` as they are, so a device
or track name containing ``</script>`` ends the script element and whatever
follows it runs as markup. Escaping them as ``\\u003C`` etc. keeps the JSON
identical once parsed (Django's ``json_script`` does the same), but nothing in
it can close the element.
"""

import json

from django.core.serializers.json import DjangoJSONEncoder

_ESCAPES = {ord('<'): '\\u003C', ord('>'): '\\u003E', ord('&'): '\\u0026'}


def script_json(value):
    return json.dumps(value, cls=DjangoJSONEncoder).translate(_ESCAPES)
