# planner/utils/pdf_exports/comm_pdf.py

from io import BytesIO

from reportlab.platypus import Paragraph

from planner.utils.pdf_exports import report_kit as kit


def get_channel_abbrev(channel):
    """Helper function to extract abbreviation from channel name."""
    if not channel:
        return ''
    # Try to get abbreviation field first
    if hasattr(channel, 'abbreviation') and channel.abbreviation:
        return str(channel.abbreviation)
    # Extract abbreviation from parentheses
    channel_str = str(channel)
    # Find text between parentheses
    if '(' in channel_str and ')' in channel_str:
        start = channel_str.find('(')
        end = channel_str.find(')')
        abbrev = channel_str[start + 1:end].strip()
        return abbrev  # Returns "PROD", "GFX", etc.
    # Fallback to first 4 characters
    return channel_str[:4].upper()


def generate_comm_beltpacks_pdf(project=None):
    """Generate a restyled PDF for Comm Belt Packs, grouped by system type.

    Returns the PDF as raw ``bytes``. Uses the shared ``report_kit`` toolkit
    for the navy palette, title header, styled tables and "Page X of Y" footer.

    ``project`` scopes the belt packs to a single project (multi-tenancy). If
    omitted the report spans every project (legacy behaviour) - callers should
    always pass ``request.current_project``.
    """
    from planner.models import CommBeltPack

    S = kit.styles()
    pagesize = kit.LANDSCAPE_PAGE
    usable = kit.usable_width(pagesize)

    beltpacks = CommBeltPack.objects.all()
    if project is not None:
        beltpacks = beltpacks.filter(project=project)

    if project is not None:
        project_name = project.name
    else:
        # Legacy unscoped call: only name it when a single project is present.
        names = list(beltpacks.values_list('project__name', flat=True).distinct())
        project_name = names[0] if len(names) == 1 and names[0] else ''

    story = kit.title_header("COMM System", project_name, pagesize, S)

    headers = ['BP #', 'Position', 'Name', 'Location', 'Headset',
               'CH 1', 'CH 2', 'CH 3', 'CH 4', 'IP']
    # Proportions of the usable landscape width (sum == 1.0).
    fractions = [0.06, 0.16, 0.16, 0.15, 0.10, 0.075, 0.075, 0.075, 0.075, 0.065]
    col_widths = [f * usable for f in fractions]

    any_rows = False
    for system_type, section_label in [
        ('WIRELESS', 'Wireless System'),
        ('HARDWIRED', 'Hardwired System'),
    ]:
        bps = (beltpacks
               .filter(system_type=system_type)
               .order_by('manufacturer', 'bp_number')
               .select_related('position', 'name', 'unit_location')
               .prefetch_related('channels__channel'))

        data = []
        for bp in bps:
            # Map channel_number -> abbreviation for channels 1..4.
            ch_by_num = {}
            for ch in bp.channels.all():
                if ch.channel_number in (1, 2, 3, 4) and ch.channel:
                    ch_by_num[ch.channel_number] = get_channel_abbrev(ch.channel)

            data.append([
                str(bp.bp_number) if bp.bp_number is not None else '',
                str(bp.position) if bp.position else '',
                str(bp.name) if bp.name else '',
                str(bp.unit_location) if bp.unit_location else '',
                bp.get_headset_display() if bp.headset else '',
                ch_by_num.get(1, ''),
                ch_by_num.get(2, ''),
                ch_by_num.get(3, ''),
                ch_by_num.get(4, ''),
                str(bp.ip_address) if bp.ip_address else '',
            ])

        if not data:
            continue
        any_rows = True

        # Drop channel/IP/etc. columns that are entirely blank; always keep BP #.
        h, d, w = kit.prune_empty_columns(headers, data, col_widths, keep=(0,))

        heading = Paragraph(section_label, S['sub'])
        story += kit.emit_subtable([heading], None, h, d, w, S)

    if not any_rows:
        story.append(Paragraph("No belt packs to display.", S['empty']))

    buffer = BytesIO()
    kit.build_pdf(buffer, story, pagesize=pagesize,
                  project_name=project_name, title="COMM System")
    return buffer.getvalue()
