"""Mic Planner: the sidebar entry (named and placed just above Mic Tracker),
the dashboard card's states per show day (no import, imported, plan, sent,
changed since), the channel count, Mic Tracker's "Planned in Mic Planner",
the old /mic-plan/ URLs and help slugs, and a viewer's read-only card.
Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_planner_dashboard --settings=audiopatch.test_settings
"""

import re
from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import push
from planner.mic_plan.status import channel_count
from planner.models import MicPlanPush, MicPlanSettings, ShowDay
from planner.tests.test_mic_plan_edits import EditBase
from planner.tests.test_mic_plan_import import MicPlanBase


def plan_of(used, channels=None, spares=0, over=0):
    packs = ([{'rf': n, 'pool': 'body', 'spare': False} for n in range(1, used + 1)]
             + [{'rf': 100 + n, 'pool': 'HH', 'spare': True} for n in range(spares)])
    for p in packs[used - over:used]:
        p['over'] = True
    return SimpleNamespace(packs=packs, settings={'wireless_channels': channels, 'handheld_channels': 2,
                                                  'spare_handhelds': spares})


class ChannelCountTests(SimpleTestCase):

    def test_used_of_the_usable_channels_and_the_spares(self):
        self.assertEqual('9 of 13 ch · 1 spare', channel_count(plan_of(9, 14, 1))['text'])
        self.assertEqual('13 of 13 ch · 1 spare', channel_count(plan_of(13, 14, 1))['text'])
        self.assertEqual('9 of 14 ch', channel_count(plan_of(9, 14))['text'])           # no spares: omitted
        c = channel_count(plan_of(13, 14, 1))
        self.assertEqual((13, 13, 1, False), (c['used'], c['of'], c['spare'], c['over']))

    def test_over_the_rig(self):
        c = channel_count(plan_of(15, 14, 1, over=2))
        self.assertEqual('15 of 13 ch — over the rig', c['text'])
        self.assertTrue(c['over'])

    def test_no_rig(self):
        c = channel_count(plan_of(9))
        self.assertEqual(('9 ch', None, False), (c['text'], c['of'], c['over']))


class SidebarTests(MicPlanBase):

    def models(self, user):
        self.use(user)
        resp = self.client.get(reverse('admin:planner_console_changelist'))
        app = next(a for a in resp.context['available_apps'] if a['app_label'] == 'planner')
        return app['models']

    def test_mic_planner_sits_just_above_mic_tracker(self):
        for user in (self.owner, self.viewer):
            with self.subTest(user=user.username):
                names = [(m['object_name'], str(m['name'])) for m in self.models(user)]
                k = names.index(('ShowflowImport', 'Mic Planner'))
                self.assertEqual(('ShowDay', 'Mic Tracker'), names[k + 1])


class DashboardBase(EditBase):

    def stats(self):
        resp = self.client.get(reverse('planner:dashboard_stats'))
        self.assertEqual(200, resp.status_code)
        return resp.json()

    def mine(self, data=None):
        data = data or self.stats()
        return next(d for d in data['mic_planner'] if d['day'] == self.day.pk)

    def tracker_row(self, data):
        return next(d for d in data['show_days'] if d['date'] == str(self.day.date))

    def send(self):
        p = push.preview(self.day)
        resp = self.client.post(reverse('planner:mic_plan_push', args=[self.day.pk]),
                                {'version': p.plan.version, 'digest': p.digest})
        self.assertEqual(302, resp.status_code)


class DashboardCardTests(DashboardBase):

    def test_no_import_then_imported_then_a_plan(self):
        bare = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        row = next(d for d in self.stats()['mic_planner'] if d['day'] == bare.pk)
        self.assertEqual('none', row['state'])
        self.plan().delete()
        self.assertEqual({'day': self.day.pk, 'state': 'imported'},
                         {k: v for k, v in self.mine().items() if k in ('day', 'state')})
        self.generate()
        row = self.mine()
        self.assertEqual('plan', row['state'])
        self.assertEqual(self.plan().version, row['version'])
        self.assertIsNone(row['sent'])
        self.assertFalse(row['changed_since_sent'])

    def test_channels_and_the_review_count_match_the_page(self):
        s = MicPlanSettings.objects.get(project=self.project)
        s.wireless_channels, s.handheld_channels, s.spare_handhelds = 14, 3, 1
        s.save()
        self.generate()
        row = self.mine()
        used = sum(1 for p in self.plan().packs if not p.get('spare'))
        self.assertEqual('{} of 13 ch · 1 spare'.format(used), row['channels']['text'])
        page = self.client.get(reverse('planner:mic_plan') + '?day={}'.format(self.day.pk))
        self.assertEqual(len(page.context['cards']), row['review'])

    def test_sent_then_changed_since(self):
        self.send()
        data = self.stats()
        row = self.mine(data)
        self.assertEqual(self.plan().version, row['sent']['version'])
        self.assertFalse(row['changed_since_sent'])
        self.assertTrue(self.tracker_row(data)['planned'])
        self.generate()                                         # a new version
        row = self.mine()
        self.assertTrue(row['changed_since_sent'])
        self.assertEqual(self.plan().version - 1, row['sent']['version'])

    def test_a_reverted_push_is_not_sent(self):
        self.send()
        last = MicPlanPush.objects.get(day=self.day)
        last.summary = {**last.summary, 'reverted': True}
        last.save()
        data = self.stats()
        self.assertIsNone(self.mine(data)['sent'])
        self.assertFalse(self.tracker_row(data)['planned'])

    def test_mic_tracker_note_only_for_a_pushed_day(self):
        data = self.stats()
        self.assertFalse(self.tracker_row(data)['planned'])

    def test_only_the_current_projects_days(self):
        self.assertFalse([d for d in self.stats()['mic_planner'] if d['day'] == self.other_day.pk])

    def test_the_card_sits_before_mic_tracker(self):
        html = self.client.get(reverse('admin:index')).content.decode()
        self.assertLess(html.index('ss-card micplan'), html.index('ss-card mic"'))
        self.assertIn('Import a showflow to plan mics', html)


class ViewerTests(DashboardBase):

    def test_a_viewer_sees_the_card_read_only(self):
        self.send()
        self.use(self.viewer)
        row = self.mine()
        self.assertEqual('plan', row['state'])
        self.assertTrue(row['sent'])
        html = self.client.get(reverse('admin:index')).content.decode()
        card = re.search(r'<a class="ss-card micplan".*?</a>', html, re.S).group(0)
        self.assertIn('href="{}"'.format(reverse('planner:mic_plan')), card)
        self.assertNotRegex(card, r'<form|<button|method=')


class OldLinksTests(MicPlanBase):

    def test_mic_plan_urls_keep_their_paths(self):
        self.assertEqual('/audiopatch/mic-plan/', reverse('planner:mic_plan'))
        self.assertEqual('/audiopatch/mic-plan/day/{}/a2/'.format(self.day.pk),
                         reverse('planner:mic_plan_a2', args=[self.day.pk]))
        self.use(self.owner)
        resp = self.client.get('/audiopatch/mic-plan/')
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, '<h1>Mic Planner')
        self.assertNotRegex(resp.content.decode(), r'Mic Plan\b(?!ner)')

    def test_help_slugs_and_their_aliases(self):
        self.use(self.owner)
        for slug in ('import', 'edits', 'a2-schedule', 'push'):
            with self.subTest(slug=slug):
                self.assertEqual(200, self.client.get('/help/mic-plan-{}/'.format(slug)).status_code)
                resp = self.client.get('/help/mic-planner-{}/'.format(slug))
                self.assertRedirects(resp, '/help/mic-plan-{}/'.format(slug), status_code=301)
        self.assertContains(self.client.get('/help/mic-plan-import/'), 'Import a showflow into Mic Planner')
