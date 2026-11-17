"""Report what the connection matchers find, per project. Read-only.

Runs the same rules the connection graph draws from
(``planner/connections/matchers.py`` -- read its docstring for the rules and
the verdicts), and counts the results, so the rules can be judged against real
shows before anything is stored:

  (a) console / I/O output -> processor input
  (b) processor output -> amp channel input
  (c) free-text PA cable runs: Destination -> speaker array (or amp rack)

Nothing is written: no transaction, no --apply. Safe to run on prod at any
time once deployed.

Usage:
    python manage.py infer_connections
    python manage.py infer_connections --project 3
    python manage.py infer_connections --rule b --rule c
    python manage.py infer_connections -v 2      # every item that did not resolve

    # against prod (see CLAUDE.md, "Running management commands against prod"):
    railway ssh --service ShowStack -- \\
      /opt/venv/bin/python /app/manage.py infer_connections
"""
from collections import Counter

from django.core.management.base import BaseCommand

from planner.connections import matchers as m
from planner.models import Project

RULES = ('a', 'b', 'c')
FIELD_NAMES = {'avb_stream': 'avb', 'aes_input': 'aes', 'analog_input': 'analog'}


def _describe(candidate):
    if isinstance(candidate, str):
        return candidate
    return f'{candidate.node} {candidate.label}'


class Command(BaseCommand):
    help = ("Report the connections ShowStack can infer from stored text, per "
            "project. Read-only -- changes nothing.")

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, default=None,
                            help='Restrict to a single Project id.')
        parser.add_argument('--rule', action='append', choices=RULES,
                            help='Only these rules (repeatable). Default: all.')

    def handle(self, *args, **options):
        rules = options['rule'] or list(RULES)
        detail = options['verbosity'] >= 2
        projects = Project.objects.all().order_by('id')
        if options['project'] is not None:
            projects = projects.filter(id=options['project'])

        reported = 0
        for project in projects:
            index = m.ProjectIndex.load(project)
            matches = m.match_all(index)
            if not (matches.a or matches.b or matches.c or index.amp_channels):
                continue
            reported += 1
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING(
                'Project %d: %s' % (project.id, project.name)))
            if 'a' in rules:
                self._rule_a(index, matches.a, detail)
            if 'b' in rules:
                self._rule_b(index, matches.b, detail)
            if 'c' in rules:
                self._rule_c(matches.c, detail)

        self.stdout.write('')
        self.stdout.write('%d project(s) reported. Nothing was changed.' % reported)

    # -- helpers ---------------------------------------------------------------

    def _counts(self, matches, extra=()):
        c = Counter(x.verdict for x in matches)
        resolved = sum(c[v] for v in m.RESOLVED)
        same = 'same-processor %d' % c[m.SAME_PROCESSOR]
        if c[m.SAME_DEVICE]:
            same += ', same-device %d' % c[m.SAME_DEVICE]
        parts = ['matched %d (%s)' % (resolved, same),
                 'ambiguous %d' % c[m.AMBIGUOUS], 'unmatched %d' % c[m.UNMATCHED]]
        parts += ['%s %d' % (label, c[verdict]) for label, verdict in extra]
        return '  '.join(parts)

    def _detail(self, match, label):
        line = '      %-9s %s %s  %r' % (match.verdict, label, match.source.ref, match.text)
        if match.candidates:
            line += '  candidates: ' + ', '.join(_describe(c) for c in match.candidates)
        self.stdout.write(line)

    # -- rules ------------------------------------------------------------------

    def _rule_a(self, index, matches, detail):
        pairs = sum(1 for x in matches if x.verdict == m.SAME_PROCESSOR
                    and len({t.type for t in x.targets if not isinstance(t, str)}) > 1)
        self.stdout.write(' (a) %s   [same-processor type pairs: %d]'
                          % (self._counts(matches, (('via I/O', m.VIA_IO),)), pairs))
        labels = {m.norm(p.text) for p in index.processor_inputs if m.norm(p.text)}
        by_name = sum(1 for port, _ in index.matrices if m.norm(port.text) in labels)
        self.stdout.write('     matrix NAME equals a processor input label '
                          '(report only, not matched): %d' % by_name)
        if detail:
            for x in matches:
                if x.verdict not in m.RESOLVED:
                    self._detail(x, 'from')

    def _rule_b(self, index, matches, detail):
        io = sum(1 for x in matches if x.verdict in m.RESOLVED and x.via == 'io')
        self.stdout.write(' (b) %s  placeholder %d   [via I/O output: %d]'
                          % (self._counts(matches, (('drift', m.DRIFT),)),
                             len(index.amp_placeholders), io))
        analog = [x for x in matches if x.field == 'analog_input']
        both = sum(1 for x in analog if x.verdict == m.AMBIGUOUS
                   and len({m._is_io(c) for c in x.candidates}) == 2)
        to_io = sum(1 for x in analog if x.verdict in m.RESOLVED and x.via == 'io')
        to_proc = sum(1 for x in analog if x.verdict in m.RESOLVED and x.via != 'io')
        self.stdout.write('     analog input: resolved to I/O output %d · to processor %d · '
                          'ambiguous between both %d' % (to_io, to_proc, both))
        ties = [x for x in matches if x.excluded]
        if ties:
            self.stdout.write('     tie decided by excluding unused outputs (no label, no bus): '
                              '%d match(es), %d output(s) excluded'
                              % (len(ties), sum(x.excluded for x in ties)))

        filled = Counter()
        for ai in index.amp_inputs:
            filled[ai.channel.ref] += 1
        kinds = Counter()
        for ai in index.amp_inputs:
            if filled[ai.channel.ref] == 1:
                kinds[FIELD_NAMES[ai.field]] += 1
        kinds['multiple'] = sum(1 for n in filled.values() if n > 1)
        kinds['none'] = len(index.amp_channels) - len(filled)
        self.stdout.write('     Amp channels (n=%d): avb %d · aes %d · analog %d · '
                          'multiple %d · none %d'
                          % (len(index.amp_channels), kinds['avb'], kinds['aes'],
                             kinds['analog'], kinds['multiple'], kinds['none']))

        v = Counter(x.verdict for x in matches)
        self.stdout.write('       input fields: resolve to one processor %d · to one I/O '
                          'output %d · ambiguous %d · unmatched %d · drift %d · placeholder '
                          '(x, -, n/a) %d'
                          % (sum(v[r] for r in m.RESOLVED) - io, io, v[m.AMBIGUOUS],
                             v[m.UNMATCHED], v[m.DRIFT], len(index.amp_placeholders)))
        cabled = {ai.channel.ref for ai in index.amp_inputs
                  if ai.field in ('aes_input', 'analog_input')}
        self.stdout.write('       AES/analog input with no recorded cable: %d' % len(cabled))
        if detail:
            for x in matches:
                if x.verdict not in m.RESOLVED:
                    self._detail(x, FIELD_NAMES[x.field])

    def _rule_c(self, matches, detail):
        fk = sum(1 for x in matches if x.amp.via == 'fk')
        loc = sum(1 for x in matches if x.row.amp_location_id)
        self.stdout.write(' (c) Free-text PA rows (n=%d): amp FK set %d · not set %d'
                          '   [amp_location set: %d]' % (len(matches), fk, len(matches) - fk, loc))
        dest = Counter(x.speaker.verdict for x in matches)
        texts = {m.norm(x.speaker.text) for x in matches
                 if x.speaker.verdict == m.UNMATCHED and m.norm(x.speaker.text)}
        self.stdout.write('     destination → speaker array: matched %d  ambiguous %d  '
                          'unmatched %d (%d distinct texts)'
                          % (dest[m.MATCHED], dest[m.AMBIGUOUS], dest[m.UNMATCHED], len(texts)))
        rack = [x for x in matches if x.speaker.verdict == m.RACK]
        self.stdout.write('     destination looked like amp rack: %d   [Amp Location %d · '
                          'text only %d]'
                          % (len(rack), sum(1 for x in rack if x.amp.via == 'amp_location'),
                             sum(1 for x in rack if x.amp.via == 'rack_text')))
        if detail:
            for x in matches:
                end = x.speaker
                if end.verdict == m.MATCHED:
                    continue
                text = (x.row.destination or '').strip() if end.verdict == m.RACK else end.text
                line = '      %-9s pa_cable:%d  %r' % (end.verdict, x.row.pk, text)
                if end.candidates:
                    line += '  candidates: ' + ', '.join(end.candidates)
                self.stdout.write(line)
