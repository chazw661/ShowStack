from django.db import models

class Console(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class ConsoleInput(models.Model):
    console = models.ForeignKey(Console, related_name='inputs', on_delete=models.CASCADE)
    dante_number = models.PositiveIntegerField(null=True, blank=True)
    channel = models.CharField(max_length=10, blank=True)
    source = models.CharField(max_length=100, blank=True)
    group = models.CharField(max_length=50, blank=True)
    dca = models.CharField(max_length=50, blank=True)
    mute = models.BooleanField(default=False)
    direct_out = models.CharField(max_length=100, blank=True)
    omni_in = models.CharField(max_length=100, blank=True)
    omni_out = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Ch {self.channel} on {self.console.name}"


class ConsoleOutput(models.Model):
    console = models.ForeignKey(Console, related_name='outputs', on_delete=models.CASCADE)
    output_label = models.CharField(max_length=100)
    destination = models.CharField(max_length=100, blank=True)
    routing = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.output_label} on {self.console.name}"