"""Static files and marketing templates: one copy of each, and a quiet deploy.

What went wrong before this file existed:

* `planner/static` was listed in STATICFILES_DIRS and is also the planner
  app's static folder, so collectstatic met each of its files twice and
  logged a hundred "Found another file with the destination path" lines.
* Hidden in that noise, a January copy of `marketing/css/marketing.css` under
  `planner/static` beat the real one in `marketing/static`. Every edit to the
  real one (legal pages, the terms checkbox, the tablet and phone breakpoints)
  was never served.
* `marketing/templates/marketing/` held January copies of the templates in
  `templates/marketing/`, which always won. Dead, and easy to edit by mistake.
* Whitenoise's guess at "which files are hashed" asked the storage for six
  names nothing uses, and each logged "static asset missing from manifest".
"""

import collections
import io
import os
import re
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template import engines
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

# admin_interface ships its own copy of two Django admin scripts and is listed
# before django.contrib.admin so that its copy wins. That is the package's
# design, not ours to fix; collectstatic reports each once per deploy.
PACKAGE_OVERRIDES = {
    'admin/js/cancel.js',
    'admin/js/popup_response.js',
}

# Our own template folders. A name in more than one of them is a dead copy.
OUR_TEMPLATE_ROOTS = (
    'templates',
    os.path.join('planner', 'templates'),
    os.path.join('accounts', 'templates'),
    os.path.join('marketing', 'templates'),
)


def _static_sources():
    """{destination path: {real file on disk, ...}} over every finder."""
    found = collections.defaultdict(set)
    for finder in finders.get_finders():
        for path, storage in finder.list(None):
            found[path].add(os.path.realpath(storage.path(path)))
    return found


class OneCopyOfEachStaticFileTests(SimpleTestCase):
    def test_no_destination_path_is_listed_twice(self):
        """What collectstatic warns about, the same file found twice included."""
        seen = collections.Counter()
        for finder in finders.get_finders():
            for path, _storage in finder.list(None):
                seen[path] += 1
        twice = {path for path, n in seen.items() if n > 1}
        self.assertEqual(sorted(twice - PACKAGE_OVERRIDES), [])

    def test_no_two_files_compete_for_a_path(self):
        competing = {path for path, files in _static_sources().items()
                     if len(files) > 1}
        self.assertEqual(sorted(competing - PACKAGE_OVERRIDES), [])

    def test_marketing_assets_come_from_the_marketing_app(self):
        root = os.path.realpath(os.path.join(settings.BASE_DIR, 'marketing', 'static'))
        for name in ('marketing/css/marketing.css', 'marketing/js/marketing.js',
                     'marketing/images/feature-comm.png'):
            with self.subTest(name=name):
                found = finders.find(name)
                self.assertIsNotNone(found)
                self.assertTrue(os.path.realpath(found).startswith(root + os.sep))

    def test_the_marketing_stylesheet_is_the_current_one(self):
        """The rules the stale copy lacked, each used by a live template."""
        with open(finders.find('marketing/css/marketing.css')) as handle:
            css = handle.read()
        for rule in ('.legal-content', '.terms-agreement',
                     '@media (max-width: 480px)', '@media (max-width: 900px)'):
            with self.subTest(rule=rule):
                self.assertIn(rule, css)


class OneCopyOfEachTemplateTests(SimpleTestCase):
    def test_no_template_name_is_in_two_of_our_folders(self):
        names = collections.defaultdict(list)
        for root in OUR_TEMPLATE_ROOTS:
            base = os.path.join(settings.BASE_DIR, root)
            for folder, _dirs, files in os.walk(base):
                for filename in files:
                    name = os.path.relpath(os.path.join(folder, filename), base)
                    names[name].append(root)
        twice = {name: roots for name, roots in names.items() if len(roots) > 1}
        self.assertEqual(twice, {})

    def test_marketing_pages_load_from_the_project_templates(self):
        root = os.path.realpath(os.path.join(settings.BASE_DIR, 'templates'))
        for page in ('base_marketing', 'home', 'features', 'pricing', 'contact',
                     'about', 'login', 'register', 'pending', 'terms', 'privacy'):
            with self.subTest(page=page):
                template = engines['django'].get_template(f'marketing/{page}.html')
                origin = os.path.realpath(template.origin.name)
                self.assertTrue(origin.startswith(root + os.sep), origin)


class QuietDeployTests(SimpleTestCase):
    """collectstatic, then a Whitenoise start, exactly as a deploy does them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Outside the checkout: a manifest left in staticfiles/ changes how
        # every other test resolves {% static %}.
        cls.root = tempfile.mkdtemp(prefix='showstack-static-')
        cls.addClassCleanup(shutil.rmtree, cls.root, ignore_errors=True)
        cls.enterClassContext(override_settings(STATIC_ROOT=cls.root, DEBUG=False))
        out = io.StringIO()
        call_command('collectstatic', interactive=False, verbosity=1,
                     stdout=out, stderr=out)
        cls.output = out.getvalue()

    def test_collectstatic_reports_only_the_package_overrides(self):
        reported = set(re.findall(
            r"Found another file with the destination path '([^']+)'", self.output))
        self.assertEqual(sorted(reported - PACKAGE_OVERRIDES), [])

    def test_whitenoise_starts_without_a_missing_asset(self):
        from django.contrib.staticfiles.storage import staticfiles_storage
        from whitenoise.middleware import WhiteNoiseMiddleware

        # The storage reports a name once per process; forget what an earlier
        # test's start already reported, or this one passes against nothing.
        staticfiles_storage._missing_reported.clear()
        with self.assertNoLogs('audiopatch.storage', level='WARNING'):
            middleware = WhiteNoiseMiddleware(lambda request: None)
        self.assertTrue(middleware.files)

    def test_hashed_files_are_cached_forever_and_plain_ones_are_not(self):
        from django.contrib.staticfiles.storage import staticfiles_storage
        from whitenoise.middleware import WhiteNoiseMiddleware

        middleware = WhiteNoiseMiddleware(lambda request: None)
        hashed = staticfiles_storage.url('marketing/css/marketing.css')
        self.assertRegex(hashed, r'marketing\.[0-9a-f]{12}\.css$')
        self.assertTrue(middleware.immutable_file_test('', hashed))
        for plain in ('marketing/css/marketing.css', 'admin/js/jquery.init.js',
                      'planner/js/vendor/Sortable.min.js'):
            with self.subTest(plain=plain):
                self.assertFalse(middleware.immutable_file_test(
                    '', settings.STATIC_URL + plain))


class TermsCheckboxTests(TestCase):
    """The clickwrap consent on the register page. Do not remove it."""

    DATA = {
        'first_name': 'New', 'last_name': 'Person', 'email': 'new@example.com',
        'username': 'newperson', 'password1': 'a-very-strong-passw0rd!',
        'password2': 'a-very-strong-passw0rd!',
    }

    def test_the_page_has_a_required_checkbox_linking_both_documents(self):
        html = self.client.get(reverse('marketing:register')).content.decode()
        boxes = re.findall(r'<input[^>]*name="terms"[^>]*>', html)
        self.assertEqual(len(boxes), 1, boxes)
        self.assertIn('type="checkbox"', boxes[0])
        self.assertRegex(boxes[0], r'\brequired\b')
        self.assertNotIn('checked', boxes[0])
        label = html[html.index(boxes[0]):][:600]
        self.assertIn(f'href="{reverse("marketing:terms")}"', label)
        self.assertIn(f'href="{reverse("marketing:privacy")}"', label)

    def test_signing_up_without_it_creates_no_account(self):
        response = self.client.post(reverse('marketing:register'), self.DATA)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You must accept the Terms of Service')
        self.assertFalse(get_user_model().objects.filter(username='newperson').exists())

    def test_signing_up_with_it_does(self):
        response = self.client.post(
            reverse('marketing:register'), {**self.DATA, 'terms': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username='newperson').exists())
