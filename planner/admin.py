from django.contrib import admin
from .models import Device, Console, Input, Output

admin.site.register(Device)
admin.site.register(Console)
admin.site.register(Input)
admin.site.register(Output)
