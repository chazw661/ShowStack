"""The browser gate is a glob, so the glob has to be complete.

    SS_BROWSER_TESTS=1 python manage.py test planner.tests \\
        --pattern "*_browser.py" --settings=audiopatch.test_settings

Four Playwright modules were once named without the suffix and a run of
"every *_browser.py" silently left them out. Any module that reads
SS_BROWSER_TESTS must be named ``*_browser.py``.
"""

from pathlib import Path

from django.test import SimpleTestCase

FLAG = 'SS_BROWSER_TESTS'


class BrowserModuleNamingTests(SimpleTestCase):

    def test_every_playwright_module_is_named_browser(self):
        here = Path(__file__).parent
        misnamed = sorted(
            p.name for p in here.glob('*.py')
            if p.name != Path(__file__).name
            and FLAG in p.read_text(encoding='utf-8')
            and not p.name.endswith('_browser.py')
        )
        self.assertEqual(
            [], misnamed,
            'rename to *_browser.py so the browser gate glob picks them up',
        )

    def test_the_glob_finds_something(self):
        here = Path(__file__).parent
        self.assertGreaterEqual(len(list(here.glob('test_*_browser.py'))), 13)
