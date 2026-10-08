"""An Amp saved without an Amplifier Model.

``Amp.amp_model`` is declared ``null=True, blank=True``. ``blank=True`` is what
a ModelForm reads to decide whether a field is required, so the admin renders
the Amplifier Model dropdown with its ``---------`` empty choice and no
``required`` attribute: leaving it alone is a supported submission as far as
every layer above the model is concerned.

``Amp.save()`` disagreed. It calls ``setup_channels()``, which read
``self.amp_model.channel_count`` with no guard, so two things an engineer can
do in the admin ended in a 500:

  * **Add** an amp with the Amplifier Model dropdown left empty.
  * **Deep edit** an existing amp and clear its model back to ``---------``
    (``save()`` takes that branch via ``old_model and old_model != None``).

A third path, ``Project.duplicate()``, copies ``amp_model`` across verbatim and
so propagated the crash -- dormant only because nothing could persist a NULL in
the first place.

Making the model-less amp *saveable* then exposes everywhere else that read the
FK bare, which is why this file also covers the change form rendering, the
channel inline and the dashboard. Those were latent before: unreachable only
because the row they needed could not exist.

Run with::

    python manage.py test planner.tests.test_amp_without_model \\
        --settings=audiopatch.test_settings
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from planner.admin import AmpAdminForm, AmpChannelInlineForm
from planner.models import Amp, AmpChannel, AmpLocation, AmpModel, Project


class _AmpMixin:
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='amp_nomodel', email='a@example.com', password='x')
        self.project = Project.objects.create(name='no model', owner=self.user)
        self.location = AmpLocation.objects.create(project=self.project,
                                                   name='SL LA Racks')
        self.model = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA12X', channel_count=4,
            nl4_connector_count=2, nl8_connector_count=1, cacom_output_count=1)
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def add_amp(self, **kw):
        kw.setdefault('name', 'SL LA12X #1')
        kw.setdefault('location', self.location)
        return Amp.objects.create(project=self.project, **kw)

    def add_form_post(self, amp_model=''):
        """The POST body the admin Add form submits."""
        return {
            'location': self.location.pk,
            'amp_model': amp_model,
            'name': 'Posted Amp',
            'ip_address': '',
            'preset': '',
            'color': '#FFFFFF',
            'sort_order': 0,
            'channels-TOTAL_FORMS': '0',
            'channels-INITIAL_FORMS': '0',
            'channels-MIN_NUM_FORMS': '0',
            'channels-MAX_NUM_FORMS': '1000',
            '_save': 'Save',
        }


class TheFieldIsOptionalTests(_AmpMixin, TestCase):
    """Why this is a bug and not a misuse: every layer says it is allowed."""

    def test_the_model_field_is_nullable_and_blankable(self):
        field = Amp._meta.get_field('amp_model')
        self.assertTrue(field.null)
        self.assertTrue(field.blank)

    def test_the_admin_form_does_not_require_it(self):
        self.assertFalse(AmpAdminForm().fields['amp_model'].required)

    def test_the_admin_form_validates_without_it(self):
        data = self.add_form_post()
        # The admin excludes `project` and fills it in save_model; a form
        # built directly still asks for it.
        data['project'] = self.project.pk
        form = AmpAdminForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.errors.get('amp_model'))


class SaveWithoutAModelTests(_AmpMixin, TestCase):
    """``setup_channels()`` is the crash site; all four shapes of it."""

    def test_creating_one_does_not_raise(self):
        amp = self.add_amp()
        self.assertIsNone(amp.amp_model)
        self.assertEqual(amp.channels.count(), 0)

    def test_saving_it_again_does_not_raise(self):
        amp = self.add_amp()
        amp.name = 'renamed'
        amp.save()
        amp.refresh_from_db()
        self.assertEqual(amp.name, 'renamed')

    def test_clearing_the_model_does_not_raise(self):
        amp = self.add_amp(amp_model=self.model)
        self.assertEqual(amp.channels.count(), 4)
        amp.amp_model = None
        amp.save()                      # old_model set, new None -> branch B
        amp.refresh_from_db()
        self.assertIsNone(amp.amp_model)

    def test_clearing_the_model_keeps_the_channels(self):
        """Non-destructive on purpose: those rows are the engineer's patch."""
        amp = self.add_amp(amp_model=self.model)
        amp.channels.update(channel_name='Main L LF')
        amp.amp_model = None
        amp.save()
        self.assertEqual(amp.channels.count(), 4)
        self.assertEqual(
            sorted(set(amp.channels.values_list('channel_name', flat=True))),
            ['Main L LF'])

    def test_picking_a_model_afterwards_reconciles_the_count(self):
        amp = self.add_amp()
        self.assertEqual(amp.channels.count(), 0)
        amp.amp_model = self.model
        amp.save()
        self.assertEqual(amp.channels.count(), 4)

    def test_a_model_with_fewer_channels_still_shrinks(self):
        """The guard must not have disabled the existing reconciliation."""
        amp = self.add_amp(amp_model=self.model)
        self.assertEqual(amp.channels.count(), 4)
        small = AmpModel.objects.create(manufacturer="L'Acoustics",
                                        model_name='LA4X', channel_count=2)
        amp.amp_model = small
        amp.save()
        self.assertEqual(amp.channels.count(), 2)

    def test_str_does_not_read_none(self):
        self.assertEqual(str(self.add_amp()), 'SL LA12X #1 (no model)')
        self.assertIn('LA12X', str(self.add_amp(name='x',
                                                amp_model=self.model)))


class AdminAddFormTests(_AmpMixin, TestCase):
    """Path 1: POST the Add form with the dropdown left empty. Was a 500."""

    URL = '/admin/planner/amp/add/'

    def test_the_add_page_renders(self):
        self.assertEqual(self.client.get(self.URL).status_code, 200)

    def test_posting_without_a_model_succeeds(self):
        response = self.client.post(self.URL, self.add_form_post())
        self.assertEqual(response.status_code, 302)     # saved, redirected
        amp = Amp.objects.get(name='Posted Amp')
        self.assertIsNone(amp.amp_model)
        self.assertEqual(amp.channels.count(), 0)

    def test_posting_with_a_model_still_builds_channels(self):
        response = self.client.post(self.URL,
                                    self.add_form_post(amp_model=self.model.pk))
        self.assertEqual(response.status_code, 302)
        amp = Amp.objects.get(name='Posted Amp')
        self.assertEqual(amp.amp_model, self.model)
        self.assertEqual(amp.channels.count(), 4)


class AdminChangeFormTests(_AmpMixin, TestCase):
    """Path 2: "Deep edit" an amp and clear its model. Was a 500 twice over --
    once on the POST that cleared it, and then on every GET of the page."""

    def url(self, amp):
        return '/admin/planner/amp/%s/change/' % amp.pk

    def post_body(self, amp, amp_model=''):
        body = self.add_form_post(amp_model=amp_model)
        body['name'] = amp.name
        return body

    def test_clearing_the_model_through_the_form_succeeds(self):
        amp = self.add_amp(amp_model=self.model)
        response = self.client.post(self.url(amp), self.post_body(amp))
        self.assertEqual(response.status_code, 302)
        amp.refresh_from_db()
        self.assertIsNone(amp.amp_model)

    def test_the_change_page_renders_for_a_model_less_amp(self):
        """``get_fieldsets`` read ``obj.amp_model.nl4_connector_count`` bare."""
        amp = self.add_amp()
        response = self.client.get(self.url(amp))
        self.assertEqual(response.status_code, 200)

    def test_the_change_page_still_shows_connector_fieldsets_with_a_model(self):
        amp = self.add_amp(amp_model=self.model)
        response = self.client.get(self.url(amp))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('NL4 Connectors', html)
        self.assertIn('CaCom Outputs', html)
        self.assertIn('NL8 Connectors', html)

    def test_no_connector_fieldsets_without_a_model(self):
        amp = self.add_amp()
        html = self.client.get(self.url(amp)).content.decode('utf-8')
        self.assertNotIn('NL4 Connectors', html)
        self.assertNotIn('CaCom Outputs', html)
        self.assertNotIn('NL8 Connectors', html)

    def test_the_rack_changelist_renders(self):
        self.add_amp()
        self.add_amp(name='with model', amp_model=self.model)
        response = self.client.get('/admin/planner/amp/')
        self.assertEqual(response.status_code, 200)


class ChannelInlineFormTests(_AmpMixin, TestCase):
    """``AmpChannelInlineForm.__init__`` read ``amp.amp_model.has_avb_inputs``."""

    def test_it_builds_for_a_channel_on_a_model_less_amp(self):
        amp = self.add_amp()
        channel = AmpChannel.objects.create(amp=amp, channel_number=1)
        form = AmpChannelInlineForm(instance=channel)
        # No capabilities to read, so nothing is hidden.
        from django import forms as dj_forms
        for name in ('avb_stream', 'aes_input', 'analog_input'):
            self.assertNotIsInstance(form.fields[name].widget,
                                     dj_forms.HiddenInput)

    def test_it_still_hides_fields_the_model_lacks(self):
        no_avb = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA4X', channel_count=2,
            has_avb_inputs=False, has_aes_inputs=True, has_analog_inputs=True)
        amp = self.add_amp(amp_model=no_avb)
        form = AmpChannelInlineForm(instance=amp.channels.first())
        from django import forms as dj_forms
        self.assertIsInstance(form.fields['avb_stream'].widget,
                              dj_forms.HiddenInput)
        self.assertNotIsInstance(form.fields['aes_input'].widget,
                                 dj_forms.HiddenInput)


class DashboardTests(_AmpMixin, TestCase):
    """``total_amp_channels`` summed ``a.amp_model.channel_count`` bare.

    The widest blast radius of the latent set: the sum is not scoped to a
    project, so one model-less amp anywhere would have taken down the
    dashboard for every logged-in user.
    """

    URL = '/audiopatch/dashboard/'

    def test_it_renders_with_a_model_less_amp_present(self):
        self.add_amp()
        self.assertEqual(self.client.get(self.URL).status_code, 200)

    def test_the_channel_count_skips_it_and_totals_the_rest(self):
        self.add_amp()                                   # contributes 0
        self.add_amp(name='with model', amp_model=self.model)   # contributes 4
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_amp_channels'], 4)
        self.assertEqual(response.context['total_amps'], 2)


class ProjectDuplicationTests(_AmpMixin, TestCase):
    """``Project.duplicate()`` copies ``amp_model`` verbatim, NULL included."""

    def test_duplicating_a_project_with_a_model_less_amp(self):
        self.add_amp()
        copy = self.project.duplicate(new_name='dup')
        amps = Amp.objects.filter(project=copy)
        self.assertEqual(amps.count(), 1)
        self.assertIsNone(amps.first().amp_model)

    def test_duplicating_carries_a_real_model_over(self):
        self.add_amp(amp_model=self.model)
        copy = self.project.duplicate(new_name='dup2')
        self.assertEqual(Amp.objects.get(project=copy).amp_model, self.model)

    def test_duplicating_a_mixed_project(self):
        self.add_amp()
        self.add_amp(name='with model', amp_model=self.model)
        copy = self.project.duplicate(new_name='dup3')
        got = sorted(
            (a.name, a.amp_model_id)
            for a in Amp.objects.filter(project=copy)
        )
        self.assertEqual(got, [('SL LA12X #1', None),
                               ('with model', self.model.pk)])
