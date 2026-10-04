"""The one definition of how a PA cable run becomes physical stock cables.

This used to live in three places that agreed by coincidence rather than by
construction:

  * ``PACableAdmin.changelist_view`` -- the on-screen "Cables needed" /
    "Order qty" summary,
  * ``pa_cable_pdf._quick_order_rows`` -- the PDF Quick Order List,
  * and, for fan-out extensions, a *fourth* rule inside the admin summary
    that rounded the other way.

They now all call this module. The rule is stated once, here, and the tests
in ``planner/tests/test_pa_cable_math.py`` pin it.

The rule
--------
A run is built from **physical cables**. A row of ``4 x 50'`` is four 50'
cables -- never two 100' ones, because those four runs go to four different
places and cannot be spliced into each other.

Stock is 100', 50' and 25'. Nothing shorter is carried, so a short run takes
a 25' and the slack is coiled.

For a single run of length L:

  1. Take whole 100' cables while more than 100' remains.
  2. Whatever is left is **one** more cable: the smallest stock length that
     covers it. 25' or less takes a 25'; 50' or less takes a 50'; anything
     longer takes a 100'.

Then the row's ``count`` multiplies the whole breakdown.

Worked examples (these are the cases that come up on a real plot):

===========  ====================  ==================================
Run length   Stock cables          Why
===========  ====================  ==================================
10'          1 x 25'               nothing shorter is carried
25'          1 x 25'               exact
50'          1 x 50'               exact
60'          1 x 100'              50' will not reach
75'          1 x 100'              rounds up
100'         1 x 100'              exact
110'         1 x 100' + 1 x 25'    leftover 10' takes a 25'
150'         1 x 100' + 1 x 50'    leftover 50' is exact
175'         1 x 100' + 1 x 100'   leftover 75' rounds up to 100'
200'         2 x 100'              exact
300'         3 x 100'              exact
===========  ====================  ==================================

Jumpers
-------
A jumper ("NL4 Jumper", see ``JUMPER_TYPES``) is a short box-to-box link.
You order N of them; you do not cut them to length. So a jumper is counted
by quantity only: it never goes through the breakdown above, its stored
length is ignored wherever one exists, and it contributes nothing to any
total-length figure. Any run that needs a length belongs to a cable type,
not to Jumper.

Per cable type
--------------
Every type carries the same three lengths today. ``STOCK_LENGTHS_BY_TYPE``
exists so one type can differ without a second copy of the rule appearing
somewhere: put the ``PACableSchedule.CABLE_TYPE_CHOICES`` key in it with its
own descending list, and the breakdown, the summary columns and the PDF all
follow.

Ordering overage
----------------
"Order qty" is the raw count plus a 20% temporary-installation margin,
``ceil(raw * 1.2)``. It is applied **once**, to the finished total -- never to
a subtotal that something else is then added to, because ``ceil`` is not
reversible and ``round(safe / 1.2)`` does not recover the raw number (raw 17
-> safe 21 -> "raw" 18).
"""

import math
from collections import Counter

#: What every cable type is stocked in, longest first.
DEFAULT_STOCK_LENGTHS = (100, 50, 25)

#: Per-type overrides, keyed by PACableSchedule.CABLE_TYPE_CHOICES value.
#: Empty today -- see "Per cable type" above.
STOCK_LENGTHS_BY_TYPE = {}

#: Temporary-installation ordering margin.
SAFETY_FACTOR = 1.2

#: Cable types that are counted by quantity only, by display label.
#:
#: A jumper is a short box-to-box link: you order N of them, you do not cut
#: them to length. So a jumper never goes through the breakdown, its length
#: is ignored wherever it is stored, and it contributes nothing to any
#: total-length figure. Anything that needs a length is a cable type, not a
#: jumper.
#:
#: Add a type here (e.g. "NL8 Jumper") and the stored CABLE_TYPE_CHOICES
#: value is picked up with it -- see ``jumper_type_values()``.
JUMPER_TYPES = {"NL4 Jumper"}

#: Said in plain words under the summary table, so the screen explains itself.
RULE_TEXT = (
    "Stock is 100', 50' and 25'. Each run is built from physical cables: "
    "whole 100' cables while more than 100' remains, then one more cable for "
    "the leftover — the smallest stock length that covers it (25' or "
    "less takes a 25', 50' or less takes a 50', anything longer takes a "
    "100'). A row's Count multiplies the whole breakdown — 4 × 50' "
    "is four 50' cables, not two 100' ones. Order qty adds a 20% margin, "
    "rounded up. "
    "Jumpers are counted by quantity only. Use a cable type, not Jumper, "
    "for any run that needs a length."
)

#: Memo for jumper_type_values(), keyed by the JUMPER_TYPES it was built
#: from so a test that patches the set is not served a stale answer.
_jumper_values_cache = {}


def jumper_type_values():
    """The stored ``cable`` values whose display label is in JUMPER_TYPES.

    The summary groups rows by display label while the breakdown is handed
    the row's stored value, so both spellings have to resolve. Deriving one
    from the other keeps JUMPER_TYPES the single place a jumper is named.

    The model import is deferred: this module is imported from admin.py and
    the PDF exporter, and a module-level ``from planner.models import ...``
    would make that a cycle.
    """
    key = frozenset(JUMPER_TYPES)
    if key not in _jumper_values_cache:
        from planner.models import PACableSchedule
        _jumper_values_cache[key] = frozenset(
            value for value, label in PACableSchedule.CABLE_TYPE_CHOICES
            if label in JUMPER_TYPES
        )
    return _jumper_values_cache[key]


def is_jumper(cable_type):
    """True for a jumper, given either its stored value or its display label."""
    if not cable_type:
        return False
    return cable_type in JUMPER_TYPES or cable_type in jumper_type_values()


def stock_lengths_for(cable_type=None):
    """The stock lengths carried for ``cable_type``, longest first."""
    return STOCK_LENGTHS_BY_TYPE.get(cable_type, DEFAULT_STOCK_LENGTHS)


def all_stock_lengths():
    """Every length any type is stocked in, longest first.

    What the summary columns and the Quick Order List iterate, so a per-type
    override shows up on screen without anything else being edited.
    """
    lengths = set(DEFAULT_STOCK_LENGTHS)
    for override in STOCK_LENGTHS_BY_TYPE.values():
        lengths.update(override)
    return tuple(sorted(lengths, reverse=True))


#: Convenience for callers that just want the columns.
STOCK_LENGTHS = all_stock_lengths()


def round_up_to_stock(leftover, cable_type=None):
    """The single cable that covers ``leftover`` feet.

    The smallest stock length that reaches. ``None`` for a leftover of zero
    or less -- no cable is needed.
    """
    if leftover is None or leftover <= 0:
        return None
    stock = stock_lengths_for(cable_type)
    for length in sorted(stock):
        if leftover <= length:
            return length
    # Longer than the longest spool. The caller takes whole longest-spool
    # cables off first, so this is only reachable if a type's list changes
    # under us; covering it with the longest keeps us from under-ordering.
    return max(stock)


def stock_breakdown(length, cable_type=None):
    """Stock cables for ONE run of ``length`` feet, as ``{stock: qty}``.

    A jumper returns nothing at all: it is ordered by quantity, so whatever
    length is stored against it -- blank, 3', 100' -- is ignored rather than
    cut from stock.

    A zero, negative or missing length needs no cable and returns an empty
    Counter rather than raising -- a half-entered row should not take the
    whole summary down.
    """
    cables = Counter()
    if is_jumper(cable_type):
        return cables
    if not length or length <= 0:
        return cables

    longest = max(stock_lengths_for(cable_type))
    remaining = length
    while remaining > longest:
        cables[longest] += 1
        remaining -= longest

    covering = round_up_to_stock(remaining, cable_type)
    if covering is not None:
        cables[covering] += 1
    return cables


def run_breakdown(length, count, cable_type=None):
    """``stock_breakdown(length)`` multiplied by the row's ``count``.

    Empty for a jumper. The count is not lost -- the caller tallies a
    jumper's quantity directly (see ``PACableAdmin.changelist_view``).
    """
    cables = Counter()
    if not count or count <= 0:
        return cables
    for stock, qty in stock_breakdown(length, cable_type).items():
        cables[stock] += qty * count
    return cables


def with_safety(raw):
    """Raw count -> order quantity, with the 20% margin. 0 stays 0."""
    if not raw or raw <= 0:
        return 0
    return math.ceil(raw * SAFETY_FACTOR)


def explain_run(length, count=1, cable_type=None):
    """``"4 x 150' -> 4 x 100' + 4 x 50'"`` -- for tests and for showing work."""
    cables = run_breakdown(length, count, cable_type)
    if not cables:
        return "%s × %s' → (nothing)" % (count, length)
    parts = ' + '.join(
        "%d × %d'" % (cables[stock], stock)
        for stock in all_stock_lengths() if cables.get(stock)
    )
    return "%s × %s' → %s" % (count, length, parts)
