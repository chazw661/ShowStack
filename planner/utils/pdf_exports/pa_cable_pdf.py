# planner/utils/pdf_exports/pa_cable_pdf.py
"""
PA Cable Schedule PDF Export.

Restyled onto the shared report_kit toolkit so it matches the professional
navy/blue look used across all ShowStack module exports (title header, navy
table headers, zebra striping, "Page X of Y" footer, orphan-safe page breaks).

Data preserved from the original export:
  * the cable run list (label, destination, count, length, cable type,
    fan-outs, notes, drawing ref)
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
    """Build the main cable-run table rows."""
    data = []
    for cable in queryset.prefetch_related('fan_outs'):
        label_text = str(cable.label) if cable.label else '-'
        destination = cable.destination or '-'
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
    Quick Order List (same logic as the original export, incl. 20% safety)."""
    from planner.models import PACableSchedule

    quick_order_data = []

    for cable_type in PACableSchedule.CABLE_TYPE_CHOICES:
        cables = queryset.filter(cable=cable_type[0])
        if cables.exists():
            hundreds = 0
            fifties = 0
            twenty_fives = 0
            tens = 0
            fives = 0

            for cable in cables:
                cable_length = cable.length or 0
                cable_count = cable.count or 0

                for _ in range(cable_count):
                    remaining = cable_length
                    while remaining > 0:
                        if remaining > 50:
                            hundreds += 1
                            remaining -= 100
                        elif remaining > 25:
                            fifties += 1
                            remaining -= 50
                        elif remaining > 10:
                            twenty_fives += 1
                            remaining -= 25
                        elif remaining > 5:
                            tens += 1
                            remaining -= 10
                        elif remaining > 0:
                            fives += 1
                            remaining -= 5

            hundreds_safe = math.ceil(hundreds * 1.2) if hundreds > 0 else 0
            fifties_safe = math.ceil(fifties * 1.2) if fifties > 0 else 0
            twenty_fives_safe = math.ceil(twenty_fives * 1.2) if twenty_fives > 0 else 0
            tens_safe = math.ceil(tens * 1.2) if tens > 0 else 0
            fives_safe = math.ceil(fives * 1.2) if fives > 0 else 0

            cable_name = cable_type[1]

            if hundreds_safe > 0:
                quick_order_data.append([cable_name, "100'", str(hundreds_safe)])
            if fifties_safe > 0:
                quick_order_data.append([cable_name, "50'", str(fifties_safe)])
            if twenty_fives_safe > 0:
                quick_order_data.append([cable_name, "25'", str(twenty_fives_safe)])
            if tens_safe > 0:
                quick_order_data.append([cable_name, "10'", str(tens_safe)])
            if fives_safe > 0:
                quick_order_data.append([cable_name, "5'", str(fives_safe)])

    # Add extension cables to quick order totals (issue #23: extensions now
    # live in their own table with per-extension quantity).
    ext_cable_map = {'NL4': 'NL 4', 'NL8': 'NL 8'}
    for cable in queryset.prefetch_related('fan_outs__extensions'):
        for fan_out in cable.fan_outs.all():
            for ext in fan_out.extensions.all():
                cable_name = ext_cable_map.get(ext.extension_cable, ext.extension_cable)
                ext_length = ext.extension_length
                ext_qty = ext.quantity

                length_label = f"{ext_length}'"
                # Check if this cable+length already exists in quick_order_data
                found = False
                for row in quick_order_data:
                    if row[0] == cable_name and row[1] == length_label:
                        # Recalculate: add raw ext_qty to pre-safety total, reapply safety
                        current_safe = int(row[2])
                        # Reverse the 20% to get raw, add extension, reapply
                        raw_estimate = round(current_safe / 1.2)
                        new_total = raw_estimate + ext_qty
                        row[2] = str(math.ceil(new_total * 1.2))
                        found = True
                        break
                if not found:
                    quick_order_data.append([cable_name, length_label, str(math.ceil(ext_qty * 1.2))])

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
        headers = ['Label', 'Destination', 'Count', 'Length', 'Cable',
                   'Fan Outs', 'Notes', 'Dwg Ref']
        widths = [w * inch for w in (1.1, 1.4, 0.6, 0.7, 1.0, 1.7, 2.2, 0.8)]
        data = _cable_rows(queryset, S)
        # Keep Label + Destination even if a page happens to be blank.
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
