"""Cabinet catalogue: the seed's figures, its redeploy behaviour, and who may edit.

Run with::

    python manage.py test planner.tests.test_cabinet_catalogue \\
        --settings=audiopatch.test_settings
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from planner.management.commands.load_cabinets import CABINETS
from planner.models import CabinetModel, CabinetSection, Project, UserProfile


def load(*args):
    call_command('load_cabinets', *args, stdout=StringIO())


def sections(model):
    return [(s.name, s.nominal_impedance_ohms)
            for s in CabinetSection.objects.filter(cabinet__model=model)]


class SeedFiguresTests(TestCase):

    def setUp(self):
        load()

    def test_every_cabinet_is_seeded_once_with_a_cited_source(self):
        self.assertEqual(len(CABINETS), CabinetModel.objects.count())
        for cab in CabinetModel.objects.all():
            self.assertIn('Preset Guide', cab.source)
            self.assertRegex(cab.source, r'p\.\d+.*p\.118')
            self.assertTrue(cab.sections.exists(), cab.model)

    def test_active_multiway_sections(self):
        self.assertEqual([('LF', 8), ('HF', 8)], sections('Kara II'))
        self.assertEqual([('LF', 8), ('HF', 8)], sections('K3'))
        # Preset Guide p.118: K2's HF section is the 16 ohm exception.
        self.assertEqual([('LF', 8), ('MF', 8), ('HF', 16)], sections('K2'))

    def test_a_series_is_passive(self):
        # [A10] / [A15] route PA to every output (pp.68, 70): one section.
        for model in ('A10 Wide/Focus', 'A15 Wide/Focus'):
            self.assertEqual([('Full range', 8)], sections(model))
            self.assertFalse(CabinetModel.objects.get(model=model).is_multiway)

    def test_impedance_exceptions(self):
        self.assertEqual([('Full range', 16)], sections('Kiva II'))
        for model in ('KS28', 'SB28', 'K1-SB', 'SB6i'):
            self.assertEqual(Decimal(4), sections(model)[0][1], model)

    def test_only_l2_is_marked_unverified(self):
        unverified = set(CabinetSection.objects.filter(verified=False)
                         .values_list('cabinet__model', flat=True))
        self.assertEqual({'L2 / L2D'}, unverified)

    def test_section_label(self):
        kara_lf = CabinetSection.objects.get(cabinet__model='Kara II', name='LF')
        self.assertEqual('Kara II · LF', str(kara_lf))
        self.assertEqual('KS28', str(CabinetSection.objects.get(cabinet__model='KS28')))


class RedeployTests(TestCase):

    def test_redeploy_keeps_a_superusers_edit(self):
        load()
        hf = CabinetSection.objects.get(cabinet__model='Kara II', name='HF')
        hf.nominal_impedance_ohms = Decimal('12')
        hf.save()
        load()
        hf.refresh_from_db()
        self.assertEqual(Decimal('12'), hf.nominal_impedance_ohms)
        self.assertEqual(len(CABINETS), CabinetModel.objects.count())

    def test_force_resets_to_the_seed(self):
        load()
        CabinetSection.objects.filter(cabinet__model='Kara II', name='HF').update(
            nominal_impedance_ohms=Decimal('12'))
        load('--force')
        self.assertEqual([('LF', 8), ('HF', 8)], sections('Kara II'))

    def test_a_missing_section_is_restored_without_force(self):
        load()
        CabinetSection.objects.filter(cabinet__model='K2', name='MF').delete()
        load()
        self.assertEqual([('LF', 8), ('MF', 8), ('HF', 16)], sections('K2'))


class CataloguePermissionTests(TestCase):

    def setUp(self):
        load()
        self.owner = User.objects.create_user('cab_owner', 'o@example.com', 'pw',
                                              is_staff=True)
        UserProfile.objects.update_or_create(user=self.owner,
                                             defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.superuser = User.objects.create_superuser('cab_su', 's@example.com', 'pw')
        self.kara = CabinetModel.objects.get(model='Kara II')

    def _login(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['current_project_id'] = self.project.id
        s.save()

    def test_owner_can_read_but_not_change(self):
        self._login(self.owner)
        url = reverse('admin:planner_cabinetmodel_change', args=[self.kara.id])
        self.assertEqual(200, self.client.get(
            reverse('admin:planner_cabinetmodel_changelist')).status_code)
        self.assertEqual(200, self.client.get(url).status_code)
        self.client.post(url, {'manufacturer': 'L-Acoustics', 'model': 'PWNED'})
        self.kara.refresh_from_db()
        self.assertEqual('Kara II', self.kara.model)
        self.assertEqual(403, self.client.get(
            reverse('admin:planner_cabinetmodel_add')).status_code)

    def test_superuser_can_open_the_editor(self):
        self._login(self.superuser)
        resp = self.client.get(reverse('admin:planner_cabinetmodel_changelist'))
        self.assertContains(resp, 'Kara II')
        self.assertContains(resp, 'LF 8 Ω')
