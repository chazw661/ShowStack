"""Channel order on a console -- one rule for the Console page and its PDF.

The channel number is text (input_ch, aux_number, matrix_number), so a plain
ORDER BY gives 1, 10, 100, 101, ... 11. Numbered channels sort as numbers;
anything else ("ST 7", "ST6") follows them in text order, then blanks; the
row id breaks ties so the order never shuffles between page loads.

The cast only sees values that are all digits: casting "ST 7" to an integer
is a DataError on Postgres (SQLite would quietly call it 0).
"""

from django.db.models import Case, F, IntegerField, Value, When
from django.db.models.functions import Cast

NON_NUMERIC = 99999


def by_channel_number(qs, field):
    """``qs`` ordered by its text channel-number ``field``, numbers first."""
    return qs.annotate(
        _channel_int=Case(
            When(**{f'{field}__regex': r'^\d+$'}, then=Cast(field, IntegerField())),
            default=Value(NON_NUMERIC),
            output_field=IntegerField(),
        )
    ).order_by('_channel_int', F(field).asc(nulls_last=True), 'pk')
