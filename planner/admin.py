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
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import Device, DeviceInput, DeviceOutput
from .forms import DeviceForm, NameOnlyForm

# ———— your inlines here ——————————————————————————————————

class DeviceInputInline(admin.TabularInline):
    model = DeviceInput
    extra = 0  # we'll override in get_formset()

    def get_formset(self, request, obj=None, **kwargs):
        # show exactly obj.input_count extra blank rows
        kwargs['extra'] = obj.input_count if obj else 0
        FormSet = super().get_formset(request, obj, **kwargs)

        class InitializingFormSet(FormSet):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                # auto-populate input_number for new rows
                for idx, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial.setdefault('input_number', idx + 1)

        return InitializingFormSet


class DeviceOutputInline(admin.TabularInline):
    model = DeviceOutput
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        kwargs['extra'] = obj.output_count if obj else 0
        FormSet = super().get_formset(request, obj, **kwargs)

        class InitializingFormSet(FormSet):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                # auto-populate output_number for new rows
                for idx, form in enumerate(self.forms):
                    if not form.instance.pk:
                        form.initial.setdefault('output_number', idx + 1)

        return InitializingFormSet



@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    inlines = [DeviceInputInline, DeviceOutputInline]
    list_display = ('name',)

    def get_fields(self, request, obj=None):
        """
        On the add form (obj is None) show name + counts.
        On the change form, everything is in the title/inlines,
        so show no fields above the inlines.
        """
        if obj is None:
            return ['name', 'input_count', 'output_count']
        return []

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = NameOnlyForm
        else:
            kwargs['form'] = DeviceForm
        return super().get_form(request, obj, **kwargs)

    def response_add(self, request, obj, post_url_continue=None):
        # redirect into the change page so the inlines appear.
        change_url = reverse('admin:planner_device_change', args=(obj.pk,))
        return HttpResponseRedirect(change_url)