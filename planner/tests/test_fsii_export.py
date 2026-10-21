"""FreeSpeak II .cca export: partylines stay within CH 1-12, nothing dropped.

The export relabels partylines inside the factory `connections` file
(planner/data/comm_config/fsii_factory), which holds CH 1-12 only. A 13th
partyline used to vanish from the file without a word, with any key or port
routed to it pointing at a channel the base station does not have.

Run with::

    python manage.py test planner.tests.test_fsii_export \\
        --settings=audiopatch.test_settings
"""

import gzip
import io
import json
import tarfile

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.models import CommConfig, CommConfigPartyline, Project, UserProfile
from planner.views import _seed_freespeak_defaults


def unpack(cca_bytes):
    """{'db/devices': [json, ...], 'db/connections': [...], ...} of a .cca."""
    tar = tarfile.open(fileobj=io.BytesIO(gzip.decompress(cca_bytes)))
    files = {}
    for member in tar.getmembers():
        if member.isfile():
            text = tar.extractfile(member).read().decode()
            if member.name.startswith('db/'):
                files[member.name] = [json.loads(l) for l in text.splitlines() if l.strip()]
            else:
                files[member.name] = text
    return files


class FsiiExportBase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('a1', 'a1@example.com', 'pw')
        UserProfile.objects.update_or_create(user=self.user,
                                             defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='Show', owner=self.user)
        self.config = CommConfig.objects.create(project=self.project, name='FS2',
                                                device_type='freespeak')
        _seed_freespeak_defaults(self.config)
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def pl(self, ch):
        return self.config.partylines.get(channel_number=ch)

    def export(self):
        return self.client.get(reverse('planner:comm_config_export_freespeak',
                                       args=[self.config.pk]))

    def add_partyline(self):
        return self.client.post(reverse('planner:comm_config_add_partyline'),
                                json.dumps({'config_id': self.config.pk}),
                                content_type='application/json')


class FsiiPartylineLimitTests(FsiiExportBase):

    def test_a_thirteenth_partyline_is_refused(self):
        response = self.add_partyline()
        self.assertEqual(response.status_code, 400)
        self.assertIn('12 partylines', response.json()['error'])
        self.assertEqual(self.config.partylines.count(), 12)

    def test_a_freed_channel_is_reused_instead_of_going_past_12(self):
        self.pl(5).delete()
        response = self.add_partyline()
        self.assertEqual(response.json()['channel_number'], 5)
        self.assertEqual(set(self.config.partylines.values_list('channel_number', flat=True)),
                         set(range(1, 13)))

    def test_arcadia_keeps_counting_up(self):
        arcadia = CommConfig.objects.create(project=self.project, name='Arc')
        CommConfigPartyline.objects.create(config=arcadia, channel_number=12, label='x')
        response = self.client.post(reverse('planner:comm_config_add_partyline'),
                                    json.dumps({'config_id': arcadia.pk}),
                                    content_type='application/json')
        self.assertEqual(response.json()['channel_number'], 13)

    def test_every_partyline_in_range_is_named_in_the_export(self):
        for ch in range(1, 13):
            CommConfigPartyline.objects.filter(pk=self.pl(ch).pk).update(label=f'Show {ch}')
        response = self.export()
        self.assertEqual(response.status_code, 200)
        labels = {c['val']['id']: c['val']['label']
                  for c in unpack(response.content)['db/connections']
                  if c['val']['type'] == 'partyline'}
        self.assertEqual(labels, {ch: f'Show {ch}' for ch in range(1, 13)})

    def test_an_existing_partyline_past_12_blocks_the_export_and_says_which(self):
        # Made before the cap: by the old max+1 rule, or copied in from a
        # template.
        CommConfigPartyline.objects.create(config=self.config, channel_number=13,
                                           label='Video <b>')
        response = self.export()
        self.assertEqual(response.status_code, 409)
        self.assertNotEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('CH 13 "Video &lt;b&gt;"', response.content.decode())

        page = self.client.get(reverse('planner:comm_config_editor', args=[self.config.pk]))
        self.assertContains(page, 'Export blocked.')
        self.assertContains(page, 'CH 13 &ldquo;Video &lt;b&gt;&rdquo;')
        self.assertContains(page, 'disabled title="FreeSpeak II has partylines CH 1-12 only')

    def test_the_export_works_again_once_it_is_gone(self):
        extra = CommConfigPartyline.objects.create(config=self.config,
                                                   channel_number=13, label='Video')
        self.assertEqual(self.export().status_code, 409)
        extra.delete()
        self.assertEqual(self.export().status_code, 200)
        page = self.client.get(reverse('planner:comm_config_editor', args=[self.config.pk]))
        self.assertNotContains(page, 'Export blocked.')
