from django.contrib import admin
from .models import Device, DeviceInput
from .models import Console, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput
from planner.forms import ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm


class ConsoleInputInline(admin.TabularInline):
    model = ConsoleInput
    form = ConsoleInputForm
    extra = 144
    can_delete = True
    classes = ['collapse']

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class PrepopulatedFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                for form in self.forms:
                    for field in form.fields.values():
                        field.required = False

                for index, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial['input_ch'] = index + 1

        return PrepopulatedFormSet


class ConsoleAuxOutputInline(admin.TabularInline):
    model = ConsoleAuxOutput
    form = ConsoleAuxOutputForm
    extra = 72
    can_delete = True
    classes = ['collapse']

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class PrepopulatedFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                for form in self.forms:
                    for field in form.fields.values():
                        field.required = False

                for index, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial['aux_number'] = index + 1

        return PrepopulatedFormSet


class ConsoleMatrixOutputInline(admin.TabularInline):
    model = ConsoleMatrixOutput
    form = ConsoleMatrixOutputForm
    extra = 36
    can_delete = True
    classes = ['collapse']

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        class PrepopulatedFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                for form in self.forms:
                    for field in form.fields.values():
                        field.required = False

                for index, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial['matrix_number'] = index + 1

        return PrepopulatedFormSet


@admin.register(Console)
class ConsoleAdmin(admin.ModelAdmin):
    list_display = ['name']
    inlines = [
        ConsoleInputInline,
        ConsoleAuxOutputInline,
        ConsoleMatrixOutputInline,
    ]

    class Media:
        js = ['planner/js/mono_stereo_handler.js']
        css = {
            'all': ['css/custom_admin.css']
        }


# ========== Device Admin ==========

from .models import Device, DeviceInput  # ensure this is included at the top


class DeviceInputInline(admin.TabularInline):
    model = DeviceInput
    extra = 16
    max_num = 64


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['name']
    inlines = [DeviceInputInline]