"""Small builders for the connection matcher / graph / report tests.

Generic names only (the repo is public). Every builder takes the project, so a
test can build a second project to check nothing leaks across.
"""
from django.contrib.auth import get_user_model

from planner.models import (
    Amp, AmpLocation, AmpModel, Console, ConsoleInput, ConsoleMatrixOutput,
    Device, DeviceInput, DeviceOutput, GalaxyOutput, GalaxyProcessor, Location,
    P1Input, P1Output, P1Processor, PACableSchedule, PAZone, Project,
    SoundvisionPrediction, SpeakerArray, SystemProcessor,
)


class ConnectionFixtures:
    """Mixin for TestCase: ``self.project`` plus builders."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username='wiring', password='x')
        self.project = self.make_project('wiring show')

    def make_project(self, name):
        return Project.objects.create(name=name, owner=self.user)

    def location(self, project, name='FOH'):
        return Location.objects.create(project=project, name=name)

    # -- processors ------------------------------------------------------------

    def p1(self, name, project=None):
        project = project or self.project
        proc = SystemProcessor.objects.create(project=project, name=name, device_type='P1',
                                              location=self.location(project, f'{name} loc'))
        P1Processor.objects.create(system_processor=proc)   # scaffolds 16 in / 16 out
        return proc

    def galaxy(self, name, project=None):
        project = project or self.project
        proc = SystemProcessor.objects.create(project=project, name=name,
                                              device_type='GALAXY',
                                              location=self.location(project, f'{name} loc'))
        GalaxyProcessor.objects.create(system_processor=proc)
        return proc

    def p1_in(self, proc, port_type, number, label):
        port = P1Input.objects.get(p1_processor__system_processor=proc,
                                   input_type=port_type, channel_number=number)
        port.label = label
        port.save()
        return port

    def p1_out(self, proc, port_type, number, label):
        port = P1Output.objects.get(p1_processor__system_processor=proc,
                                    output_type=port_type, channel_number=number)
        port.label = label
        port.save()
        return port

    def galaxy_out(self, proc, port_type, number, label):
        return GalaxyOutput.objects.create(galaxy_processor=proc.galaxy_config,
                                           output_type=port_type, channel_number=number,
                                           label=label)

    # -- consoles and I/O ----------------------------------------------------

    def console(self, name='FOH Desk', project=None, **kw):
        return Console.objects.create(project=project or self.project, name=name, **kw)

    def channel(self, console, number, source=''):
        return ConsoleInput.objects.create(console=console, input_ch=str(number), source=source)

    def matrix(self, console, number, name='', destination=''):
        return ConsoleMatrixOutput.objects.create(console=console, matrix_number=str(number),
                                                  name=name, destination=destination)

    def device(self, name='Stage Box', project=None):
        return Device.objects.create(project=project or self.project, name=name)

    def device_input(self, device, number, channel=None, name=''):
        return DeviceInput.objects.create(device=device, input_number=number,
                                          console_input=channel,
                                          signal_name=name or (channel.source if channel else ''))

    def device_output(self, device, number, name='', bus=None):
        out = DeviceOutput(device=device, output_number=number, signal_name=name)
        if bus is not None:
            out.console_output = bus
        out.save()
        return out

    # -- amps, arrays, PA cables ---------------------------------------------

    def amp(self, name, project=None, rack='SL Racks', channels=4):
        project = project or self.project
        rack_obj, _ = AmpLocation.objects.get_or_create(project=project, name=rack)
        model, _ = AmpModel.objects.get_or_create(
            manufacturer="L'Acoustics", model_name=f'TEST{channels}',
            defaults={'channel_count': channels})
        return Amp.objects.create(project=project, name=name, location=rack_obj,
                                  amp_model=model)

    def amp_channel(self, amp, number, **inputs):
        ch = amp.channels.get(channel_number=number)
        for field, value in inputs.items():
            setattr(ch, field, value)
        ch.save()
        return ch

    def prediction(self, project=None, file_name='show.pdf'):
        return SoundvisionPrediction.objects.create(project=project or self.project,
                                                    file_name=file_name)

    def array(self, prediction, name, source_name=None):
        return SpeakerArray.objects.create(
            prediction=prediction, source_name=source_name or name, array_base_name=name,
            configuration='vertical_flown', bumper_type='K2-BUMP')

    def zone(self, name, project=None):
        return PAZone.objects.get_or_create(project=project or self.project, name=name)[0]

    def text_cable(self, label=None, destination='', project=None, **kw):
        return PACableSchedule.objects.create(
            project=project or self.project, entry_mode='text', label=label,
            destination=destination, cable=kw.pop('cable', 'NL_4'),
            count=kw.pop('count', 2), length=kw.pop('length', 100), **kw)

    def linked_cable(self, amp, array, project=None, **kw):
        return PACableSchedule.objects.create(
            project=project or self.project, entry_mode='linked', amp=amp,
            speaker_array=array, cable=kw.pop('cable', 'NL_4'), count=kw.pop('count', 1),
            length=kw.pop('length', 150), **kw)
