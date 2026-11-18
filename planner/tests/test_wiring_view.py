"""Wiring Diagram page: who can open it, what it shows, and that names stay text.

Run with::

    python manage.py test planner.tests.test_wiring_view \\
        --settings=audiopatch.test_settings
"""
import re
import xml.etree.ElementTree as ET

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.models import Project, ProjectMember
from planner.tests.test_wiring_layout import WiringShow

NAME = '<img src=x onerror=alert(1)>'
QUOTED = '"\'><img src=x onerror=alert(1)>'
SVG_NS = '{http://www.w3.org/2000/svg}'


def svg_of(response):
    body = response.content.decode()
    match = re.search(r'<svg xmlns="http://www.w3.org/2000/svg" class="wd-svg".*?</svg>', body, re.S)
    return match.group(0) if match else None


class WiringViewTests(WiringShow, TestCase):
    url = reverse('planner:wiring_diagram')

    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()

    def member(self, name, role):
        user = User.objects.create_user(name, password='pw', is_staff=True)
        ProjectMember.objects.create(user=user, project=self.project, role=role,
                                     invited_by=self.user)
        return user

    def get(self, user, project=None):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = (project or self.project).pk
        session.save()
        return self.client.get(self.url)

    # -- who can open it ---------------------------------------------------------

    def test_every_project_role_can_view_it(self):
        users = {'owner': self.user, 'editor': self.member('ed', 'editor'),
                 'viewer': self.member('vi', 'viewer'),
                 'superuser': User.objects.create_superuser('boss', 'b@example.com', 'pw')}
        for role, user in users.items():
            response = self.get(user)
            self.assertEqual(response.status_code, 200, role)
            self.assertIsNotNone(svg_of(response), role)
            self.assertContains(response, 'Stage Box · outputs')

    def test_a_non_member_sees_nothing_of_the_project(self):
        outsider = User.objects.create_user('out', password='pw', is_staff=True)
        response = self.get(outsider)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Stage Box')
        self.assertNotContains(response, self.project.name)
        self.assertContains(response, 'Choose a project')

    def test_a_non_member_with_a_project_of_their_own_sees_only_theirs(self):
        outsider = User.objects.create_user('out', password='pw', is_staff=True)
        theirs = Project.objects.create(name='Their show', owner=outsider)
        self.device('Their Box', project=theirs)
        response = self.get(outsider, project=self.project)   # a stale session id
        self.assertNotContains(response, 'Stage Box')
        self.assertContains(response, 'Their Box · inputs')

    def test_anonymous_is_sent_to_log_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_it_is_read_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_the_sidebar_lists_it_for_a_viewer_after_pa_cables(self):
        viewer = self.member('vi', 'viewer')
        self.get(viewer)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, f'href="{self.url}"')
        models = [m['object_name'] for app in response.context['available_apps']
                  if app['app_label'] == 'planner' for m in app['models']]
        self.assertIn('WiringDiagram', models)
        if 'PACableSchedule' in models:
            self.assertEqual(models.index('WiringDiagram'), models.index('PACableSchedule') + 1)

    # -- what it shows -------------------------------------------------------------

    def test_the_svg_is_well_formed_with_the_expected_boxes_and_edges(self):
        root = ET.fromstring(svg_of(self.get(self.user)))
        boxes = {g.get('data-box') for g in root.iter(f'{SVG_NS}g') if g.get('data-box')}
        self.assertIn(f'device:{self.box.pk}#in', boxes)
        self.assertIn(f'device:{self.box.pk}#out', boxes)
        self.assertIn('unlinked:text:nowhere', boxes)
        labels = [t.text for t in root.iter(f'{SVG_NS}text') if 'wd-label' in (t.get('class') or '')]
        self.assertIn('Out 2 → AES 1', labels)
        self.assertIn("HL · 2× NL 4 100'", labels)
        self.assertTrue(any(l.startswith('? Delay') for l in labels))

    def test_warnings_list_the_ambiguous_feed_and_its_candidates(self):
        response = self.get(self.user)
        self.assertContains(response, 'Matches more than one')
        warnings = response.context['warnings']
        [row] = [w for w in warnings if w['kind'] == 'ambiguous']
        self.assertEqual(row['text'], 'Delay')
        self.assertEqual(set(row['candidates']), {'SL P1 AES 2', 'SR P1 AES 1'})

    def test_an_empty_project_says_so(self):
        empty = Project.objects.create(name='Empty show', owner=self.user)
        response = self.get(self.user, project=empty)
        self.assertContains(response, 'Nothing to draw yet')
        self.assertIsNone(svg_of(response))


class WiringViewEscapesNamesTests(WiringShow, TestCase):
    """Every user-typed name lands in the SVG and the warnings panel as text."""

    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()
        self.box.name = NAME
        self.box.save()
        self.desk.name = QUOTED
        self.desk.save()
        self.amp_channel(self.sl_amp, 2, analog_input=QUOTED)          # unlinked text
        self.text_cable(self.zone(NAME), destination=QUOTED)             # PA zone + destination
        self.array(self.prediction(file_name='x.pdf'), NAME)
        self.p1_in(self.sr, 'AES', 2, NAME)                               # ambiguous with...
        self.p1_in(self.sl, 'AES', 3, NAME)
        self.device_output(self.box, 5, NAME)                            # ...this output
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def test_no_name_becomes_markup(self):
        response = self.client.get(reverse('planner:wiring_diagram'))
        body = response.content.decode()
        self.assertNotIn('<img src=x', body)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', body)
        self.assertNotIn(QUOTED, body)

    def test_the_svg_parses_and_reads_the_names_back_as_text(self):
        response = self.client.get(reverse('planner:wiring_diagram'))
        root = ET.fromstring(svg_of(response))
        self.assertEqual([e for e in root.iter() if e.tag.endswith('img')], [])
        titles = {t.text for t in root.iter(f'{SVG_NS}title')}
        self.assertIn(f'{NAME} · inputs', titles)
        self.assertIn(QUOTED, titles)
        texts = [t.text or '' for t in root.iter(f'{SVG_NS}text')]
        self.assertIn(f'? {QUOTED}', ' '.join(texts))
        # A quote in a name stays inside its attribute: the box's id reads back whole.
        self.assertIn(f'unlinked:text:{QUOTED}',
                      {g.get('data-box') for g in root.iter(f'{SVG_NS}g')})

    def test_the_warnings_panel_escapes_too(self):
        response = self.client.get(reverse('planner:wiring_diagram'))
        self.assertTrue(any(w['text'] == NAME for w in response.context['warnings']))
        self.assertNotIn('<img src=x', response.content.decode())
