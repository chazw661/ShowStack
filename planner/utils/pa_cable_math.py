"""The one definition of how a PA cable run becomes physical stock cables.

This used to live in three places that agreed by coincidence rather than by
construction:

  * ``CablePACableScheduleAdmin.changelist_view`` -- the on-screen "Cables
    needed" / "Order qty" summary,
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

For a single run of length L:

  1. Take whole 100' cables while more than 100' remains.
  2. Whatever is left is **one** more cable, rounded **up** to the next stock
     length: 25', 50' or 100'.
  3. 10' and 5' are used only when the leftover is exactly 10 or exactly 5.
     A 7' leftover takes a 25', not a 10' -- a 10' cable will not reach.

Then the row's ``count`` multiplies the whole breakdown.

Worked examples (these are the cases that come up on a real plot):

===========  ====================  ==================================
Run length   Stock cables          Why
===========  ====================  ==================================
50'          1 x 50'               exact
60'          1 x 100'              50' will not reach
75'          1 x 100'              rounds up
100'         1 x 100'              exact
150'         1 x 100' + 1 x 50'    leftover 50' is exact
175'         1 x 100' + 1 x 100'   leftover 75' rounds up to 100'
200'         2 x 100'              exact
300'         3 x 100'              exact
===========  ====================  ==================================

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

#: Stock spool lengths carried, longest first.
STOCK_LENGTHS = (100, 50, 25, 10, 5)

#: Lengths that are only ever used on an exact fit. A 10' cable does not
#: reach 12', so a 12' leftover takes a 25'.
EXACT_FIT_ONLY = (10, 5)

#: Lengths a leftover may round up into.
ROUND_UP_LENGTHS = tuple(
    length for length in sorted(STOCK_LENGTHS) if length not in EXACT_FIT_ONLY
)

#: Temporary-installation ordering margin.
SAFETY_FACTOR = 1.2

#: Said in plain words under the summary table, so the screen explains itself.
RULE_TEXT = (
    "Each run is built from physical cables: whole 100' cables while more "
    "than 100' remains, then one more cable for the leftover, rounded up to "
    "the next stock length (25', 50' or 100'). 10' and 5' are used only when "
    "the leftover is exactly that long. A row's Count multiplies the whole "
    "breakdown — 4 × 50' is four 50' cables, not two 100' ones. "
    "Order qty adds a 20% margin, rounded up."
)


def round_up_to_stock(leftover):
    """The single cable that covers ``leftover`` feet.

    ``None`` for a leftover of zero or less. 10' and 5' only on an exact fit.
    """
    if leftover is None or leftover <= 0:
        return None
    if leftover in EXACT_FIT_ONLY:
        return leftover
    for length in ROUND_UP_LENGTHS:
        if leftover <= length:
            return length
    # Longer than the longest spool: the caller is expected to have taken
    # whole 100' cables off first, so this is only reachable if STOCK_LENGTHS
    # ever changes. Covering it with the longest spool keeps us from
    # under-ordering.
    return max(ROUND_UP_LENGTHS)


def stock_breakdown(length):
    """Stock cables for ONE run of ``length`` feet, as ``{stock: qty}``.

    A zero, negative or missing length needs no cable and returns an empty
    Counter rather than raising -- a half-entered row should not take the
    whole summary down.
    """
    cables = Counter()
    if not length or length <= 0:
        return cables

    remaining = length
    while remaining > 100:
        cables[100] += 1
        remaining -= 100

    covering = round_up_to_stock(remaining)
    if covering is not None:
        cables[covering] += 1
    return cables


def run_breakdown(length, count):
    """``stock_breakdown(length)`` multiplied by the row's ``count``."""
    cables = Counter()
    if not count or count <= 0:
        return cables
    for stock, qty in stock_breakdown(length).items():
        cables[stock] += qty * count
    return cables


def with_safety(raw):
    """Raw count -> order quantity, with the 20% margin. 0 stays 0."""
    if not raw or raw <= 0:
        return 0
    return math.ceil(raw * SAFETY_FACTOR)


def explain_run(length, count=1):
    """``"4 x 150' -> 4 x 100' + 4 x 50'"`` -- for tests and for showing work."""
    cables = run_breakdown(length, count)
    if not cables:
        return "%s × %s' → (nothing)" % (count, length)
    parts = ' + '.join(
        "%d × %d'" % (cables[stock], stock)
        for stock in STOCK_LENGTHS if cables.get(stock)
    )
    return "%s × %s' → %s" % (count, length, parts)
