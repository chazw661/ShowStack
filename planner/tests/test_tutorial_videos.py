"""Tutorial videos, the label order link, and the branding page's messages.

- A "Watch how" button renders wherever its video has an ID and vanishes
  when the ID is blank -- pages and Help alike.
- No page carries a YouTube iframe on load: the button holds the embed URL
  and the player script builds the iframe only when it is pressed.
- The label stock carries its own order link, shown on Print labels, in
  Help and on the alignment PDF.
- A saved-branding message shows once (the admin's message bar), not twice.

Run with::

    python manage.py test planner.tests.test_tutorial_videos \\
        --settings=audiopatch.test_settings
"""

import re
from io import BytesIO
from unittest import mock

from django.contrib.auth.models import User
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from planner import tutorials
from planner.help.topics import TOPICS_BY_SLUG
from planner.models import ProjectMember, UserProfile
from planner.tests.test_amp_output_cabinets import Fixture as AmpFixture
from planner.tests.test_help import WORD_LIMIT, visible_words
from planner.tests.test_power_plan_single_entry import SingleEntryBase
from planner.utils.labels.render import Options, render_alignment_pdf
from planner.utils.labels.stock import STOCKS

LABELS_ID = tutorials.TUTORIAL_VIDEOS['labels']
POWER_ID = tutorials.TUTORIAL_VIDEOS['power']
ORDER_URL = 'https://www.onlinelabels.com/products/ol3016lp'

BUTTON = re.compile(r'<button[^>]*class="ss-tutorial-btn[^"]*"[^>]*>')
IFRAME = re.compile(r'<iframe[^>]*>', re.I)


def blank(key):
    return mock.patch.dict(tutorials.TUTORIAL_VIDEOS, {key: ''})


class VideoAssertions:

    def assert_button(self, html, video_id):
        buttons = [b for b in BUTTON.findall(html) if video_id in b]
        self.assertTrue(buttons, 'no Watch how button for {}'.format(video_id))
        for b in buttons:
            self.assertIn('data-tutorial-src="https://www.youtube-nocookie.com/embed/{}"'
                          .format(video_id), b)
            self.assertIn('aria-haspopup="dialog"', b)
        self.assertIn('planner/js/tutorial_video.js', html)

    def assert_no_button(self, html):
        self.assertFalse(BUTTON.findall(html))
        self.assertNotIn('Watch how', html)

    def assert_nothing_loads_from_youtube(self, html):
        # The only mention of YouTube is the button's data attribute.
        for frame in IFRAME.findall(html):
            self.assertNotIn('youtube', frame.lower())
        stripped = re.sub(r'data-tutorial-src="[^"]*"', '', html)
        self.assertNotIn('youtube', stripped.lower())


# ---------------------------------------------------------------- config + tag

class TutorialConfigTests(VideoAssertions, TestCase):

    def render(self, key):
        return Template("{% load tutorial_tags %}{% tutorial_button key %}").render(
            Context({'key': key}))

    def test_button_text_carries_the_length(self):
        self.assertIn('▶ Watch how (2 min)', self.render('labels'))
        self.assertIn('▶ Watch how (1½ min)', self.render('power'))

    def test_blank_or_unknown_id_renders_nothing(self):
        with blank('labels'):
            self.assertIsNone(tutorials.tutorial('labels'))
            self.assertEqual(self.render('labels').strip(), '')
        self.assertEqual(self.render('nonsense').strip(), '')

    def test_assets_hold_no_iframe(self):
        html = Template("{% load tutorial_tags %}{% tutorial_assets %}").render(Context())
        self.assertNotIn('<iframe', html)
        self.assertNotIn('youtube', html)

    def test_player_script_builds_the_iframe_only_on_open_and_removes_it(self):
        from django.contrib.staticfiles import finders
        with open(finders.find('planner/js/tutorial_video.js'), encoding='utf-8') as f:
            js = f.read()
        self.assertIn("createElement('iframe')", js)
        self.assertIn('frameBox.replaceChildren();', js)          # close removes it
        self.assertIn("'cancel'", js)                              # Esc
        self.assertIn('e.target === dialog', js)                   # backdrop
        self.assertIn('opener.focus()', js)                        # focus returned
        self.assertIn("'strict-origin-when-cross-origin'", js)     # YouTube needs a Referer


# ---------------------------------------------------------------- label pages

class LabelPageTests(VideoAssertions, TestCase):

    @classmethod
    def setUpTestData(cls):
        from planner.models import Project
        cls.owner = User.objects.create_user('tv_owner', 'o@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=cls.owner, defaults={'account_type': 'paid'})
        cls.project = Project.objects.create(name='Main Show', owner=cls.owner)
        cls.viewer = User.objects.create_user('tv_viewer', 'v@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=cls.viewer, defaults={'account_type': 'paid'})
        ProjectMember.objects.create(user=cls.viewer, project=cls.project, role='viewer',
                                     invited_by=cls.owner)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def page(self, name):
        r = self.client.get(reverse(name))
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    def test_print_and_branding_pages_show_the_labels_video(self):
        for user in (self.owner, self.viewer):
            self.login(user)
            for name in ('planner:mic_tracker_print', 'planner:project_branding'):
                with self.subTest(user=user.username, page=name):
                    html = self.page(name)
                    self.assert_button(html, LABELS_ID)
                    self.assertNotIn(POWER_ID, html)
                    self.assert_nothing_loads_from_youtube(html)

    def test_blank_id_hides_the_button(self):
        self.login(self.owner)
        with blank('labels'):
            for name in ('planner:mic_tracker_print', 'planner:project_branding'):
                with self.subTest(page=name):
                    self.assert_no_button(self.page(name))

    def test_order_link_beside_the_stock_description(self):
        self.login(self.viewer)
        html = self.page('planner:mic_tracker_print')
        link = re.search(r'<a[^>]*id="mtp-order"[^>]*>([^<]*)</a>', html)
        self.assertIsNotNone(link)
        self.assertIn('href="{}"'.format(ORDER_URL), link.group(0))
        self.assertIn('target="_blank"', link.group(0))
        self.assertIn('rel="noopener"', link.group(0))
        self.assertEqual(link.group(1), 'Order labels ↗')
        # It sits in the same line as the stock description.
        sub = re.search(r'<div class="mtp-sub">(.*?)</div>', html, re.S).group(1)
        self.assertIn(STOCKS['OL3016LP'].description.replace('"', '&quot;'), sub)
        self.assertIn('mtp-order', sub)

    def test_order_link_hidden_for_a_stock_without_one(self):
        from dataclasses import replace
        stock = replace(STOCKS['OL3016LP'], order_url='')
        self.login(self.owner)
        with mock.patch.dict(STOCKS, {'OL3016LP': stock}):
            html = self.page('planner:mic_tracker_print')
        self.assertNotIn('id="mtp-order"', html)
        self.assertNotIn(ORDER_URL, html)

    def test_saved_branding_message_shows_once(self):
        self.login(self.owner)
        r = self.client.post(reverse('planner:branding_save'),
                             {'bg_color': '', 'accent_style': 'none'}, follow=True)
        self.assertEqual(r.status_code, 200)
        texts = [str(m) for m in r.context['messages']]
        self.assertEqual(len(texts), 1, texts)
        html = r.content.decode()
        self.assertEqual(html.count(texts[0]), 1, texts[0])
        self.assertIn('class="messagelist"', html)
        self.assertNotIn('pb-messages', html)

    def test_label_pages_leave_messages_to_the_admin_bar(self):
        # admin/base.html prints every message; a page printing them again
        # shows each one twice.
        from django.template.loader import get_template
        for name in ('planner/mic_tracker_print.html', 'planner/project_branding.html'):
            source = get_template(name).template.source
            self.assertNotRegex(source, r'for \w+ in messages', name)

    def test_alignment_pdf_names_where_to_buy(self):
        from pypdf import PdfReader
        pdf = render_alignment_pdf(STOCKS['OL3016LP'], Options())
        reader = PdfReader(BytesIO(pdf))
        page = reader.pages[0]
        text = page.extract_text()
        self.assertIn('Labels: OnlineLabels OL3016LP — onlinelabels.com/products/ol3016lp', text)
        uris = [a.get_object()['/A']['/URI'] for a in page.get('/Annots', [])]
        self.assertIn(ORDER_URL, uris)

    def test_alignment_pdf_without_order_url_has_no_line(self):
        from dataclasses import replace
        from pypdf import PdfReader
        stock = replace(STOCKS['OL3016LP'], order_url='')
        text = PdfReader(BytesIO(render_alignment_pdf(stock, Options()))).pages[0].extract_text()
        self.assertNotIn('Labels: OnlineLabels', text)


# ---------------------------------------------------------------- power pages

class PowerCalculatorTests(VideoAssertions, SingleEntryBase):

    def test_calculator_header_shows_the_power_video(self):
        self.generate_a()
        for user in (self.user_a, self.viewer):
            self.use(user)
            r = self.client.get(reverse('planner:power_distribution_calculator'))
            self.assertEqual(r.status_code, 200)
            html = r.content.decode()
            with self.subTest(user=user.username):
                self.assert_button(html, POWER_ID)
                self.assertNotIn(LABELS_ID, html)
                self.assert_nothing_loads_from_youtube(html)

    def test_blank_id_hides_it(self):
        self.generate_a()
        self.use(self.user_a)
        with blank('power'):
            html = self.client.get(reverse('planner:power_distribution_calculator')).content.decode()
        self.assert_no_button(html)


class AmpRackTests(VideoAssertions, AmpFixture):

    def test_cabinets_row_shows_the_power_video_beside_the_help_link(self):
        viewer = User.objects.create_user('tv_amp_viewer', password='pw', is_staff=True)
        self.join(viewer, self.project, 'viewer')
        for user in (self.owner, viewer):
            self.use(user)
            html = self.client.get(reverse('admin:planner_amp_changelist')).content.decode()
            with self.subTest(user=user.username):
                head = re.search(r'<div class="amp-cabinets-head">(.*?)<div class="amp-plan-controls">',
                                 html, re.S)
                self.assertIsNotNone(head)
                self.assertIn('How power is worked out', head.group(1))
                self.assert_button(head.group(1) + html, POWER_ID)
                self.assertIn(POWER_ID, head.group(1))
                self.assert_nothing_loads_from_youtube(html)

    def test_blank_id_hides_it(self):
        self.use(self.owner)
        with blank('power'):
            html = self.client.get(reverse('admin:planner_amp_changelist')).content.decode()
        self.assertIn('How power is worked out', html)
        self.assert_no_button(html)


# ---------------------------------------------------------------- help

class HelpVideoTests(VideoAssertions, TestCase):

    TOPICS = {'mic-labels': LABELS_ID, 'label-branding': LABELS_ID, 'power-plan': POWER_ID}

    def setUp(self):
        user = User.objects.create_user('tv_help', 'h@example.com', 'pw', is_staff=True)
        self.client.force_login(user)

    def test_topics_link_their_video(self):
        for slug, video_id in self.TOPICS.items():
            with self.subTest(slug=slug):
                html = self.client.get(reverse('help:topic', args=[slug])).content.decode()
                self.assert_button(html, video_id)
                self.assert_nothing_loads_from_youtube(html)
        index = self.client.get(reverse('help:index')).content.decode()
        self.assert_button(index, LABELS_ID)
        self.assert_button(index, POWER_ID)
        self.assert_nothing_loads_from_youtube(index)

    def test_blank_id_hides_the_help_line(self):
        with blank('labels'), blank('power'):
            for slug in self.TOPICS:
                html = self.client.get(reverse('help:topic', args=[slug])).content.decode()
                self.assertNotIn('help-video', html, slug)
                self.assert_no_button(html)

    def test_topics_with_their_video_line_fit_the_word_budget(self):
        for slug in self.TOPICS:
            topic = TOPICS_BY_SLUG[slug]
            line = render_to_string('tutorials/_button.html',
                                    {'video': tutorials.tutorial(topic.video)})
            n = len(visible_words(render_to_string(topic.template) + line))
            self.assertLessEqual(n, WORD_LIMIT, '{} ({} words)'.format(slug, n))

    def test_labels_topic_links_the_stock_order_page(self):
        html = render_to_string(TOPICS_BY_SLUG['mic-labels'].template)
        link = re.search(r'<a[^>]*>Order labels ↗</a>', html)
        self.assertIsNotNone(link)
        # Help fragments carry no template logic, so the URL is written out:
        # this keeps it in step with the stock registry.
        self.assertIn('href="{}"'.format(STOCKS['OL3016LP'].order_url), link.group(0))
        self.assertIn('target="_blank"', link.group(0))
        self.assertIn('rel="noopener"', link.group(0))
