from django.db import models

class Console(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class ConsoleInput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    dante_number = models.CharField(max_length=3)
    input_ch = models.CharField(max_length=10)
    source = models.CharField(max_length=100)
    group = models.CharField(max_length=100, blank=True)
    dca = models.CharField(max_length=100, blank=True)
    mute = models.CharField(max_length=100, blank=True)
    direct_out = models.CharField(max_length=100, blank=True)
    omni_in = models.CharField(max_length=100, blank=True)
    omni_out = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Input {self.dante_number}"


class ConsoleAuxOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    aux_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    mono_stereo = models.CharField("Mono/Stereo", max_length=10, choices=[("Mono", "Mono"), ("Stereo", "Stereo")])
    bus_type = models.CharField("Fixed/Variable", max_length=10, choices=[("Fixed", "Fixed"), ("Variable", "Variable")])
    omni_in = models.CharField(max_length=100, blank=True)
    omni_out = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Aux {self.aux_number} - {self.name}"


class ConsoleMatrixOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    matrix_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    mono_stereo = models.CharField(
        max_length=10, choices=[("Mono", "Mono"), ("Stereo", "Stereo")]
    )
    destination = models.CharField(max_length=100, blank=True)
    omni_out = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Matrix {self.matrix_number} - {self.name}"