from django.db import models

class Console(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class ConsoleInput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    dante_number = models.CharField(max_length=3, blank=True, null=True)
    input_ch = models.CharField(max_length=10, blank=True, null=True)
    source = models.CharField(max_length=100, blank=True, null=True)
    group = models.CharField(max_length=100, blank=True, null=True)
    dca = models.CharField(max_length=100, blank=True, null=True)
    mute = models.CharField(max_length=100, blank=True, null=True)
    direct_out = models.CharField(max_length=100, blank=True, null=True)
    omni_in = models.CharField(max_length=100, blank=True, null=True)
    omni_out = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Input {self.dante_number}"


class ConsoleAuxOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    aux_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100, blank=True, null=True)
    mono_stereo = models.CharField(
        max_length=10,
        choices=[("Mono", "Mono"), ("Stereo", "Stereo")],
        blank=True,
        null=True
    )
    bus_type = models.CharField(
        max_length=10,
        choices=[("Fixed", "Fixed"), ("Variable", "Variable")],
        blank=True,
        null=True
    )
    omni_in = models.CharField(max_length=100, blank=True)
    omni_out = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Aux {self.aux_number} - {self.name}"


class ConsoleMatrixOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    matrix_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100, blank=True, null=True)
    mono_stereo = models.CharField(
    max_length=10,
    choices=[("Mono", "Mono"), ("Stereo", "Stereo")],
    blank=True,
    null=True
)
    destination = models.CharField(max_length=100, blank=True, null=True)
    omni_out = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Matrix {self.matrix_number} - {self.name}"
    


    # planner/models.py

from django.db import models

class Device(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class DeviceInput(models.Model):
    device = models.ForeignKey(Device, related_name="inputs", on_delete=models.CASCADE)
    input_label = models.CharField(max_length=20)  # e.g. "IN 1"
    signal_name = models.CharField(max_length=100)  # e.g. "Wless 1 Analogue"

    def __str__(self):
        return f"{self.device.name} - {self.input_label}: {self.signal_name}"