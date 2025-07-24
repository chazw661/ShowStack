from django.contrib import admin
from .models import Device, DeviceInput, DeviceOutput
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

from django.contrib import admin
from .models import Device, DeviceInput,DeviceOutput
from .forms import DeviceForm

class DeviceInputInline(admin.TabularInline):
    model = DeviceInput
    extra = 0
    max_num = 64

class DeviceOutputInline(admin.TabularInline):
    model = DeviceOutput
    extra = 0
    max_num = 64

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    form = DeviceForm
    inlines = [DeviceInputInline, DeviceOutputInline]
    list_display = ['name']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # Only create inputs/outputs if it's a new device
        if not change:
            input_count = form.cleaned_data.get('input_count', 0)
            output_count = form.cleaned_data.get('output_count', 0)

            # Create DeviceInputs
            DeviceInput.objects.bulk_create([
                DeviceInput(device=obj, input_number=i + 1) for i in range(input_count)
            ])

            # Optional: Create DeviceOutputs model if/when you add it
            DeviceOutput.objects.bulk_create([
            DeviceOutput(device=obj, output_number=i + 1) for i in range(output_count)
            ])