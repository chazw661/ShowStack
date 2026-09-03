# planner/utils/pdf_exports/ip_address_report_pdf.py

from io import BytesIO

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer

from planner.utils.pdf_exports import report_kit as kit


def generate_ip_address_report_pdf(project=None):
    """
    Generate comprehensive IP Address Report PDF for all modules.
    Lists all IP addresses organized by module type with summary.

    Returns:
        BytesIO buffer containing the PDF
    """
    from django.apps import apps

    Console = apps.get_model('planner', 'Console')
    Device = apps.get_model('planner', 'Device')
    Amp = apps.get_model('planner', 'Amp')
    SystemProcessor = apps.get_model('planner', 'SystemProcessor')
    CommBeltPack = apps.get_model('planner', 'CommBeltPack')
    CommConfig = apps.get_model('planner', 'CommConfig')

    PAGE = kit.PORTRAIT_PAGE
    S = kit.styles()
    uw = kit.usable_width(PAGE)

    project_name = getattr(project, 'name', '') or ''

    story = []
    story += kit.title_header("IP Address Management", project_name, pagesize=PAGE, S=S)

    def empty(msg):
        return Paragraph(f"<i>{msg}</i>", S['empty'])

    # ------------------------------------------------------------------
    # 1. Mixing Consoles
    # ------------------------------------------------------------------
    consoles = (Console.objects.filter(project=project).order_by('name')
                if project else Console.objects.none())
    story.append(kit.section_banner("Mixing Consoles", number=1, pagesize=PAGE, S=S))
    story.append(Spacer(1, 8))
    if consoles.exists():
        headers = ['Console Name', 'Primary IP Address', 'Secondary IP Address']
        data = [[c.name or '—',
                 c.primary_ip_address or '—',
                 c.secondary_ip_address or '—'] for c in consoles]
        widths = [3.0 * inch, 2.25 * inch, 2.25 * inch]
        headers, data, widths = kit.prune_empty_columns(headers, data, widths, keep=(0,))
        story.append(kit.data_table(headers, data, widths))
    else:
        story.append(empty("No consoles defined"))
    story.append(Spacer(1, 0.2 * inch))

    # ------------------------------------------------------------------
    # 2. I/O Devices
    # ------------------------------------------------------------------
    devices = (Device.objects.filter(project=project).order_by('name')
               if project else Device.objects.none())
    story.append(kit.section_banner("I/O Devices", number=2, pagesize=PAGE, S=S))
    story.append(Spacer(1, 8))
    if devices.exists():
        headers = ['Device Name', 'Primary IP Address', 'Secondary IP Address']
        data = [[d.name or '—',
                 d.primary_ip_address or '—',
                 d.secondary_ip_address or '—'] for d in devices]
        widths = [3.0 * inch, 2.25 * inch, 2.25 * inch]
        headers, data, widths = kit.prune_empty_columns(headers, data, widths, keep=(0,))
        story.append(kit.data_table(headers, data, widths))
    else:
        story.append(empty("No I/O devices defined"))
    story.append(Spacer(1, 0.2 * inch))

    # ------------------------------------------------------------------
    # 3. Amplifiers
    # ------------------------------------------------------------------
    amps = (Amp.objects.filter(project=project).order_by('location__name', 'name')
            if project else Amp.objects.none())
    story.append(kit.section_banner("Amplifiers", number=3, pagesize=PAGE, S=S))
    story.append(Spacer(1, 8))
    if amps.exists():
        headers = ['Amplifier Name', 'Location', 'IP Address (AVB Network)']
        data = []
        for amp in amps:
            ip = getattr(amp, 'ip_address', '') or '—'
            location = amp.location.name if amp.location else 'No Location'
            data.append([amp.name or '—', location, ip])
        widths = [2.75 * inch, 2.25 * inch, 2.5 * inch]
        headers, data, widths = kit.prune_empty_columns(headers, data, widths, keep=(0,))
        story.append(kit.data_table(headers, data, widths))
    else:
        story.append(empty("No amplifiers defined"))
    story.append(Spacer(1, 0.2 * inch))

    # ------------------------------------------------------------------
    # 4. System Processors
    # ------------------------------------------------------------------
    processors = (SystemProcessor.objects.filter(project=project).order_by('device_type', 'name')
                  if project else SystemProcessor.objects.none())
    story.append(kit.section_banner("System Processors", number=4, pagesize=PAGE, S=S))
    story.append(Spacer(1, 8))
    if processors.exists():
        headers = ['Processor Name', 'Type', 'IP Address (AVB Network)']
        data = []
        for p in processors:
            ip = getattr(p, 'ip_address', '') or '—'
            device_type = (p.get_device_type_display()
                           if hasattr(p, 'get_device_type_display') else p.device_type)
            data.append([p.name or '—', device_type, ip])
        widths = [2.75 * inch, 2.25 * inch, 2.5 * inch]
        headers, data, widths = kit.prune_empty_columns(headers, data, widths, keep=(0,))
        story.append(kit.data_table(headers, data, widths))
    else:
        story.append(empty("No system processors defined"))
    story.append(Spacer(1, 0.2 * inch))

    # ------------------------------------------------------------------
    # 5. COMM Config (wireless roles) — grouped per config, no orphan headings
    # ------------------------------------------------------------------
    comm_configs = (CommConfig.objects.filter(project=project, is_template=False).order_by('name')
                    if project else CommConfig.objects.none())
    story.append(kit.section_banner("COMM Config", number=5, pagesize=PAGE, S=S))
    story.append(Spacer(1, 8))
    role_device_types = ['FSII-BP', 'E-BP', 'HBP-2X', 'HMS-4X', 'HRM-4X', 'V12', 'V24', 'V32']
    any_roles = False
    for config in comm_configs:
        roles = config.roles.filter(device_type__in=role_device_types).order_by('role_number')
        if not roles.exists():
            continue
        any_roles = True
        headers = ['Role Name', 'Device Type', 'IP Address']
        data = [[role.label or '—',
                 role.get_device_type_display(),
                 str(role.ip_address) if role.ip_address else '—'] for role in roles]
        widths = [2.5 * inch, 2.5 * inch, 2.5 * inch]
        headers, data, widths = kit.prune_empty_columns(headers, data, widths, keep=(0,))
        story += kit.emit_subtable([], config.name, headers, data, widths, S=S)
    if not any_roles:
        story.append(empty("No COMM Config roles defined"))
    story.append(Spacer(1, 0.2 * inch))

    # ------------------------------------------------------------------
    # 6. COMM Belt Packs (Hardwired)
    # ------------------------------------------------------------------
    belt_packs = (CommBeltPack.objects.filter(project=project, system_type='HARDWIRED')
                  .order_by('bp_number') if project else CommBeltPack.objects.none())
    story.append(kit.section_banner("COMM Belt Packs (Hardwired)", number=6, pagesize=PAGE, S=S))
    story.append(Spacer(1, 8))
    if belt_packs.exists():
        headers = ['BP #', 'Position', 'Name', 'IP Address']
        data = []
        for bp in belt_packs:
            ip = getattr(bp, 'ip_address', '') or '—'
            data.append([f"BP{bp.bp_number}", bp.position or '—', bp.name or '—', ip])
        widths = [1.0 * inch, 2.25 * inch, 2.25 * inch, 2.0 * inch]
        headers, data, widths = kit.prune_empty_columns(headers, data, widths, keep=(0, 2))
        story.append(kit.data_table(headers, data, widths))
    else:
        story.append(empty("No hardwired belt packs defined"))
    story.append(Spacer(1, 0.3 * inch))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    console_ips = sum(1 for c in consoles if c.primary_ip_address) + \
        sum(1 for c in consoles if c.secondary_ip_address)
    device_ips = sum(1 for d in devices if d.primary_ip_address) + \
        sum(1 for d in devices if d.secondary_ip_address)
    amp_ips = sum(1 for a in amps if getattr(a, 'ip_address', ''))
    processor_ips = sum(1 for p in processors if getattr(p, 'ip_address', ''))
    bp_ips = sum(1 for bp in belt_packs if getattr(bp, 'ip_address', ''))
    total_ips = console_ips + device_ips + amp_ips + processor_ips + bp_ips

    story.append(kit.section_banner("Summary", pagesize=PAGE, S=S))
    story.append(Spacer(1, 8))
    summary_headers = ['Module', 'IP Addresses Assigned']
    summary_data = [
        ['Mixing Consoles', str(console_ips)],
        ['I/O Devices', str(device_ips)],
        ['Amplifiers', str(amp_ips)],
        ['System Processors', str(processor_ips)],
        ['COMM Belt Packs (Hardwired)', str(bp_ips)],
        ['TOTAL', str(total_ips)],
    ]
    story.append(kit.data_table(summary_headers, summary_data, [4.5 * inch, 3.0 * inch]))

    buf = BytesIO()
    kit.build_pdf(buf, story, pagesize=PAGE, project_name=project_name,
                  title="IP Address Management")
    buf.seek(0)
    return buf
