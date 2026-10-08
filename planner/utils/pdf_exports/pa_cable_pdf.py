# planner/utils/pdf_exports/pa_cable_pdf.py
"""
PA Cable Schedule PDF Export.

Restyled onto the shared report_kit toolkit so it matches the professional
navy/blue look used across all ShowStack module exports (title header, navy
table headers, zebra striping, "Page X of Y" footer, orphan-safe page breaks).

Data preserved from the original export:
  * the cable run list (array/speaker, destination, count, length, cable
    type, fan-outs, notes, drawing ref)
  * the Quick Order List summary (cable lengths rolled up to stock spools,
    fan-outs, extension cables, and PA couplers -- all with the 20% safety
    margin for temporary installations)
"""

from io import BytesIO
import math

from reportlab.lib.units import inch
from reportlab.platypus import Spacer, Paragraph

from planner.utils.pdf_exports import report_kit as kit


def _project_name(queryset):
    """Derive the project name from the first item's project, if available."""
    first = queryset.first()
    if first is not None and getattr(first, 'project', None):
        return first.project.name or ''
    return ''


def _cable_rows(queryset, S):
    """Build the main cable-run table rows.

    Array/Speaker and Destination come from ``array_speaker_display`` and
    ``destination_display`` -- the two properties that resolve a cable's
    effective values whichever entry mode it is in (issue #73), and the same
    two the PA Cable changelist columns and the System Report use (#99).

    Reading the raw ``label`` and ``destination`` columns instead, as this did,
    printed an empty cell for both on every row entered in "From Soundvision /
    Amps" mode: a linked cable leaves ``label`` NULL and ``destination`` blank
    and carries its array and amp in ``speaker_array`` / ``amp``. The run was
    in the table, with its cable type, count and length -- just with no
    indication of what it ran from or to.
    """
    data = []
    for cable in queryset.prefetch_related('fan_outs'):
        label_text = cable.array_speaker_display or '-'
        destination = cable.destination_display or '-'
        count = str(cable.count) if cable.count else '1'
        length = f"{cable.length}'" if cable.length else '-'
        cable_type = cable.get_cable_display() if cable.cable else '-'
        fan_out = cable.fan_out_summary or '-'
        notes = cable.notes or '-'
        drawing_ref = cable.drawing_ref or '-'

        data.append([
            Paragraph(f"<b>{label_text}</b>", S['body']),
            Paragraph(destination, S['body']),
            count,
            length,
            Paragraph(cable_type, S['body']),
            Paragraph(fan_out, S['body']),
            Paragraph(notes, S['body']),
            Paragraph(drawing_ref, S['body']),
        ])
    return data


def _quick_order_rows(queryset):
    """Roll up all cable, extension, fan-out and coupler quantities into the
    Quick Order List, including the 20% temporary-installation margin.

    The breakdown rule is planner/utils/pa_cable_math.py -- the same module
    the on-screen "Cables needed" summary calls, so the PDF and the screen
    are one calculation rather than two that have to be kept in step.
    """
    from collections import Counter

    from planner.models import PACableSchedule
    from planner.utils import pa_cable_math

    # cable display name -> Counter of {stock length: raw qty}
    totals = {}
    # cable display name -> raw quantity, for the types ordered by count
    jumper_totals = {}
    display_names = dict(PACableSchedule.CABLE_TYPE_CHOICES)

    # Group by each row's own cable value. Iterating CABLE_TYPE_CHOICES and
    # filtering silently dropped any row whose value is not a listed choice --
    # and `cable` defaults to '100_NL4', which is not one.
    for cable in queryset:
        cable_name = display_names.get(cable.cable, cable.cable)
        if not cable_name:
            continue
        if pa_cable_math.is_jumper(cable.cable):
            # Ordered by quantity; whatever length is stored is ignored.
            jumper_totals[cable_name] = (
                jumper_totals.get(cable_name, 0) + (cable.count or 0))
            continue
        totals.setdefault(cable_name, Counter()).update(
            pa_cable_math.run_breakdown(
                cable.length, cable.count, cable.cable))

    # Extension cables (issue #23: extensions live in their own table with a
    # per-extension quantity). They are cables like any other, so they go
    # through the same rule and land in the same stock buckets -- a 150'
    # extension is a 100' plus a 50', not a non-stock "150'" line item that
    # nobody can order off a shelf. Anything stored below 25' (the old
    # 5'/6'/10' options) rounds up to a 25'.
    ext_cable_map = {'NL4': 'NL 4', 'NL8': 'NL 8'}
    for cable in queryset.prefetch_related('fan_outs__extensions'):
        for fan_out in cable.fan_outs.all():
            for ext in fan_out.extensions.all():
                cable_name = ext_cable_map.get(
                    ext.extension_cable, ext.extension_cable)
                totals.setdefault(cable_name, Counter()).update(
                    pa_cable_math.run_breakdown(
                        ext.extension_length, ext.quantity))

    # Emit in CABLE_TYPE_CHOICES order, longest spool first, with the margin
    # applied once to the finished raw total. The old code applied it per
    # cable type and then tried to un-apply it to merge extensions in --
    # `round(safe / 1.2)` does not recover the raw number (raw 17 -> safe 21
    # -> "raw" 18), so merging an extension could add a cable out of nowhere.
    order = [label for _, label in PACableSchedule.CABLE_TYPE_CHOICES]
    ordered_names = sorted(
        set(totals) | set(jumper_totals),
        key=lambda n: (order.index(n) if n in order else len(order), n))

    quick_order_data = []
    for cable_name in ordered_names:
        if cable_name in jumper_totals:
            qty = pa_cable_math.with_safety(jumper_totals[cable_name])
            if qty > 0:
                # No length column value: a jumper is not cut from stock.
                quick_order_data.append([cable_name, '—', str(qty)])
            continue
        counts = totals[cable_name]
        for stock in pa_cable_math.all_stock_lengths():
            qty = pa_cable_math.with_safety(counts.get(stock, 0))
            if qty > 0:
                quick_order_data.append([cable_name, f"{stock}'", str(qty)])

    # Add fan outs to Quick Order List
    fan_out_summary = {}
    for cable in queryset.prefetch_related('fan_outs'):
        for fan_out in cable.fan_outs.all():
            fan_out_name = fan_out.get_fan_out_type_display()
            if fan_out_name not in fan_out_summary:
                fan_out_summary[fan_out_name] = 0
            fan_out_summary[fan_out_name] += fan_out.quantity

    for fan_out_type, total_qty in fan_out_summary.items():
        qty_with_safety = math.ceil(total_qty * 1.2)
        quick_order_data.append([fan_out_type, "Fan Out", str(qty_with_safety)])

    # Issue #23 follow-up: add PA Couplers to the Quick Order list. Each
    # PACoupler row represents a discrete coupler item the engineer needs;
    # roll them up by coupler type with the standard 20% safety margin.
    coupler_summary = {}
    for cable in queryset.prefetch_related('couplers'):
        for c in cable.couplers.all():
            label = c.get_coupler_type_display()
            coupler_summary[label] = coupler_summary.get(label, 0) + c.quantity
    for coupler_label, total_qty in coupler_summary.items():
        qty_with_safety = math.ceil(total_qty * 1.2)
        quick_order_data.append([coupler_label, 'Coupler', str(qty_with_safety)])

    return quick_order_data


def generate_pa_cable_pdf(queryset):
    """Generate PDF (raw bytes) for the PA Cable Schedule."""
    buffer = BytesIO()
    S = kit.styles()
    pagesize = kit.LANDSCAPE_PAGE

    project_name = _project_name(queryset)
    story = kit.title_header("PA Cable Schedule", project_name, pagesize, S)

    # ==================== CABLE LIST ====================
    if queryset.exists():
        headers = ['Array/Speaker', 'Destination', 'Count', 'Length', 'Cable',
                   'Fan Outs', 'Notes', 'Dwg Ref']
        widths = [w * inch for w in (1.1, 1.4, 0.6, 0.7, 1.0, 1.7, 2.2, 0.8)]
        data = _cable_rows(queryset, S)
        # Keep Array/Speaker + Destination even if a page happens to be blank.
        headers, data, widths = kit.prune_empty_columns(headers, data, widths, keep=(0, 1))
        table = kit.data_table(headers, data, widths)
        if table is not None:
            story.append(table)
    else:
        story.append(Paragraph("No PA cables found in this project.", S['empty']))

    # ==================== QUICK ORDER LIST ====================
    quick_order_data = _quick_order_rows(queryset)
    if quick_order_data:
        story.append(Spacer(1, 0.3 * inch))
        qo_headers = ['Item Type', 'Length', 'Order Qty']
        qo_widths = [3.5 * inch, 1.5 * inch, 1.5 * inch]
        heading = [Paragraph("Quick Order List", S['sub'])]
        story += kit.emit_subtable(heading, None, qo_headers, quick_order_data, qo_widths, S)
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(
            "<i>Note: All quantities include a 20% safety margin for "
            "temporary installations.</i>", S['meta']))

    kit.build_pdf(buffer, story, pagesize=pagesize, project_name=project_name,
                  title="PA Cable Schedule")

    pdf = buffer.getvalue()
    buffer.close()
    return pdf
