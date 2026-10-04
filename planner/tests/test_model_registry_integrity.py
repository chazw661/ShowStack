"""Guards against the defect that stopped `manage.py test` building a database.

planner/models.py defined AudioChecklist twice -- a managed=False "dummy for
the admin interface" and, 380 lines later, the real model. Django only logs
"Model 'planner.audiochecklist' was already registered" and lets the second
definition overwrite the first, so nothing failed loudly; what failed quietly
was makemigrations, which recorded the table as unmanaged in 0063. managed=False
means CreateModel emits no DDL, so no backend was ever told to create
planner_audiochecklist, and from 0177 onwards a fresh database could not be
built at all.

Two tests, aimed at the two halves of that:

  * the duplicate class itself, caught by reading the source rather than the
    app registry -- by the time the registry is built the duplicate has already
    been silently overwritten, which is exactly why this went unnoticed for ten
    months;
  * the table being real and usable, which is what the duplicate cost us.
"""
import ast
import pathlib
from collections import Counter

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from planner.models import AudioChecklist, AudioChecklistTask, Project

User = get_user_model()

MODELS_PY = pathlib.Path(__file__).resolve().parent.parent / "models.py"


class DuplicateModelDefinitionTests(TestCase):
    """No model class name may be defined twice in planner/models.py."""

    def test_no_model_class_is_defined_twice(self):
        tree = ast.parse(MODELS_PY.read_text())
        names = [
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        ]
        duplicates = sorted(name for name, n in Counter(names).items() if n > 1)
        self.assertEqual(
            duplicates,
            [],
            "planner/models.py defines these class names more than once: "
            f"{duplicates}. The later definition silently replaces the earlier "
            "one in Django's app registry (it only logs a RuntimeWarning), and "
            "makemigrations then records whichever one it saw -- which is how "
            "planner_audiochecklist ended up never being created. Give the "
            "classes distinct names, or delete the one that is dead.",
        )

    def test_audiochecklist_is_a_managed_model_on_its_real_table(self):
        meta = apps.get_model("planner", "AudioChecklist")._meta
        self.assertTrue(
            meta.managed,
            "AudioChecklist must be managed; managed=False makes CreateModel "
            "emit no DDL, which is the original bug.",
        )
        self.assertEqual(meta.db_table, "planner_audiochecklist")


class AudioChecklistTableTests(TestCase):
    """The table exists and the ORM can use it, both directions of the FK.

    If the migration graph ever stops creating planner_audiochecklist these
    fail -- though in practice the test database would fail to build first,
    which is the louder signal and the one that was missing before.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="checklist-owner",
            email="checklist@example.com",
            password="test-pw-123",
        )
        cls.project = Project.objects.create(name="Checklist Show", owner=cls.owner)

    def test_checklist_and_task_round_trip(self):
        checklist = AudioChecklist.objects.create(
            project=self.project, name="FOH Check List"
        )
        AudioChecklistTask.objects.create(
            checklist=checklist, task="Ring out the PA", task_type="setup"
        )

        fetched = AudioChecklist.objects.get(pk=checklist.pk)
        self.assertEqual(fetched.name, "FOH Check List")
        self.assertEqual(fetched.num_days, 4)       # added by migration 0178
        self.assertEqual(fetched.tasks.count(), 1)

    def test_the_join_that_migration_0177_makes_still_works(self):
        """0177 filters tasks by checklist__name; that join is what used to
        blow up with "no such table: planner_audiochecklist"."""
        checklist = AudioChecklist.objects.create(
            project=self.project, name="Prep Check List"
        )
        AudioChecklistTask.objects.create(
            checklist=checklist, task="Pull the RF rack", task_type="daily"
        )
        self.assertEqual(
            AudioChecklistTask.objects.filter(
                task_type="daily", checklist__name="Prep Check List"
            ).count(),
            1,
        )
