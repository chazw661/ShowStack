"""One object of every model, inside one project: the objects the write
guard (test_write_endpoint_guard) fills URLs with.

make(Model) fills each required field with a plain value and builds each
foreign key the same way, every chain ending at the fixture's project and
its owner, so whatever a URL names is an object in that project. A model
it cannot build is reported by name, never skipped silently.
"""

import datetime
import itertools
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, models, transaction
from django.utils import timezone

_counter = itertools.count(1)


class Factory:

    def __init__(self, project, owner):
        self.project, self.owner = project, owner
        self.made = {}
        self.failed = {}

    def get(self, model):
        """The fixture's object of ``model`` (built on first use), or None."""
        from planner.models import Project
        if model is Project:
            return self.project
        if issubclass(model, User) or model is User:
            return self.owner
        if model in self.made:
            return self.made[model]
        if model in self.failed:
            return None
        self.failed[model] = 'building'  # breaks FK cycles
        before = set(self.made)
        try:
            with transaction.atomic():
                obj = self._build(model)
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            # Whatever was built inside the rolled-back attempt is gone too.
            for built in set(self.made) - before:
                del self.made[built]
            # A row its parent creates (an amp's channels, a session's mics).
            obj = model.objects.order_by('pk').first()
            if obj is None:
                self.failed[model] = f'{type(exc).__name__}: {exc}'[:200]
                return None
        del self.failed[model]
        self.made[model] = obj
        return obj

    def _value(self, field):
        if field.choices:
            return field.choices[0][0]
        n = next(_counter)
        if isinstance(field, models.EmailField):
            return f'guard{n}@example.invalid'
        if isinstance(field, models.SlugField):
            return f'guard-{n}'
        if isinstance(field, (models.CharField, models.TextField)):
            text = f'Guard {n}'
            return text[:field.max_length] if field.max_length else text
        if isinstance(field, models.BooleanField):
            return False
        if isinstance(field, (models.IntegerField, models.PositiveIntegerField)):
            return 1
        if isinstance(field, models.DecimalField):
            return Decimal('1')
        if isinstance(field, models.FloatField):
            return 1.0
        if isinstance(field, models.DateTimeField):
            return timezone.now()
        if isinstance(field, models.DateField):
            return datetime.date(2026, 1, 1) + datetime.timedelta(days=n)
        if isinstance(field, models.TimeField):
            return datetime.time(9, 0)
        if isinstance(field, models.UUIDField):
            return uuid.uuid4()
        if isinstance(field, models.JSONField):
            return {}
        if isinstance(field, models.GenericIPAddressField):
            return f'10.0.{n // 250 % 250}.{n % 250 + 1}'
        if isinstance(field, models.FileField):
            return ''
        return None

    def _build(self, model):
        kwargs = {}
        for field in model._meta.concrete_fields:
            if field.primary_key and field.auto_created:
                continue
            if isinstance(field, models.ForeignKey):
                # Every FK is set where it can be: an optional project or
                # parent still decides which project the object is in.
                related = field.related_model
                if related is model:
                    continue
                target = self.get(related)
                if target is None and not field.null:
                    raise IntegrityError(f'no {related.__name__} for {field.name}')
                kwargs[field.name] = target
                continue
            if field.has_default() or (field.null and not field.unique):
                continue
            if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
                continue
            if field.blank and isinstance(field, (models.CharField, models.TextField)) \
                    and not field.unique:
                continue
            value = self._value(field)
            if value is not None:
                kwargs[field.name] = value
        obj = model(**kwargs)
        obj.save()
        return obj
