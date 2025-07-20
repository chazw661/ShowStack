from django.db import models

class Device(models.Model):
    name = models.CharField(max_length=100)
    inputs = models.IntegerField()
    outputs = models.IntegerField()

    def __str__(self):
        return self.name

class Console(models.Model):
    name = models.CharField(max_length=100)

class Input(models.Model):
    console = models.ForeignKey(Console, related_name='inputs', on_delete=models.CASCADE)
    device = models.CharField(max_length=100, blank=True)
    output = models.CharField(max_length=100, blank=True)
    dante = models.CharField(max_length=100, blank=True)
    input_ch = models.CharField("Input Ch", max_length=100, blank=True)
    source = models.CharField(max_length=100, blank=True)
    group = models.CharField(max_length=100, blank=True)
    dca = models.CharField(max_length=100, blank=True)
    mute = models.CharField(max_length=20, blank=True, null=True)  # now a text field
    direct_out = models.CharField("Direct Out", max_length=100, blank=True)
    omni_in = models.CharField("Omni In", max_length=100, blank=True)
    omni_out = models.CharField("Omni Out", max_length=100, blank=True)

    def __str__(self):
        return f"Input {self.console.name} - {self.source or 'Unnamed'}"



class Output(models.Model):
    console = models.ForeignKey(Console, related_name='outputs', on_delete=models.CASCADE)
    output = models.CharField(max_length=10)
    label = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
