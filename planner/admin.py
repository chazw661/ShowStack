from django.contrib import admin
from .models import Console, ConsoleInput, ConsoleOutput

from planner.forms import ConsoleInputForm #ConsoleOutputForm 

class ConsoleInputInline(admin.TabularInline):
    model = ConsoleInput
    form = ConsoleInputForm
    extra = 10  # Number of blank entries shown by default

class ConsoleOutputInline(admin.TabularInline):
    model = ConsoleOutput
    #form = ConsoleOutputForm
    extra = 10

@admin.register(Console)
class ConsoleAdmin(admin.ModelAdmin):
    list_display = ['name']
    inlines = [ConsoleInputInline, ConsoleOutputInline]