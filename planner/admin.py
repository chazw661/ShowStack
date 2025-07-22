from django.contrib import admin
from .models import Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput
from planner.forms import ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm

class ConsoleInputInline(admin.TabularInline):
    model = ConsoleInput
    form = ConsoleInputForm
    extra = 10
    can_delete = True
    classes = ['collapse']  # ✅ Makes it collapsible


class ConsoleAuxOutputInline(admin.TabularInline):
    model = ConsoleAuxOutput
    form = ConsoleAuxOutputForm
    extra = 10
    can_delete = True
    classes = ['collapse']


class ConsoleMatrixOutputInline(admin.TabularInline):
    model = ConsoleMatrixOutput
    form = ConsoleMatrixOutputForm
    extra = 10
    can_delete = True
    classes = ['collapse']

@admin.register(Console)
class ConsoleAdmin(admin.ModelAdmin):
    list_display = ['name']
    inlines = [
        ConsoleInputInline,
        ConsoleAuxOutputInline,
        ConsoleMatrixOutputInline
    ]