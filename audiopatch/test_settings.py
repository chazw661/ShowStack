"""Test-only settings overrides.

Why this file exists
--------------------
Legacy migration ``planner/migrations/0112_fix_showday_date_constraint.py``
contains Postgres-only raw SQL (``ALTER TABLE ... ADD CONSTRAINT``) that
SQLite cannot parse, so the test database — built from the migration chain
during ``manage.py test`` setup — fails with::

    django.db.utils.OperationalError: near "CONSTRAINT": syntax error

Production runs on Postgres so the legacy migration is fine there. To run
the test suite locally on SQLite, we disable migrations and let Django
create tables directly from the current model definitions::

    python manage.py test planner.tests.test_reaper_export \\
        --settings=audiopatch.test_settings

This was first documented in Plan 01-01 SUMMARY (Phase 1, Wave 1) under
"Decisions Made" as a known pre-existing issue. This file is the
test-time workaround so we can run actual ``django.test.TestCase``
fixtures end-to-end without touching the legacy migration.

The override is a no-op against Postgres because Postgres applies the
legacy raw SQL just fine; this settings file is only used by the local
test runner on SQLite.
"""

from .settings import *  # noqa: F401,F403


class _DisableMigrations:
    """Sentinel mapping that tells Django to skip migrations for every app
    and instead create tables directly from current model state.

    See https://docs.djangoproject.com/en/5.2/topics/testing/overview/#the-test-database
    """

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
