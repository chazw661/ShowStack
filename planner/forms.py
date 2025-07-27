
# planner/forms.py

from django import forms
from django.forms import modelformset_factory
from .models import Device, ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput



class DeviceForm(forms.ModelForm):
    """Full form used when editing an existing Device."""
    class Meta:
        model = Device
        fields = ["name", "input_count", "output_count"]

class NameOnlyForm(forms.ModelForm):
    """
    A stripped‐down ModelForm used only on the very first “Add”:
    only name, input_count and output_count.
    """
    class Meta:
        model = Device
        fields = ["name", "input_count", "output_count"]

# … then your ConsoleInputForm, ConsoleAuxOutputForm, etc. below …


# ─── Console Input Form ────────────────────────────────────────────────────────

class ConsoleInputForm(forms.ModelForm):
    class Meta:
        model = ConsoleInput
        fields = [
            'dante_number',
            'input_ch',
            'source',
            'group',
            'dca',
            'mute',
            'direct_out',
            'omni_in',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['dante_number'].widget.attrs.update({
            'class': 'block w-6 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['input_ch'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['source'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['group'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['dca'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mute'].widget.attrs.update({
            'class': 'w-24 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['direct_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_in'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

InputFormSet = modelformset_factory(
    ConsoleInput,
    form=ConsoleInputForm,
    extra=10,
    can_delete=True
)

# ─── Console Output Form ───────────────────────────────────────────────────────

class ConsoleAuxOutputForm(forms.ModelForm):
    class Meta:
        model = ConsoleAuxOutput
        fields = [
            'aux_number',
            'name',
            'mono_stereo',
            'bus_type',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['aux_number'].widget.attrs.update({
            'class': 'w-16 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mono_stereo'].widget.attrs.update({
             'class': 'mono-stereo-select'
        })
        self.fields['bus_type'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

OutputFormSet = modelformset_factory(
    ConsoleAuxOutput,
    form=ConsoleAuxOutputForm,
    extra=10,
    can_delete=True
)

# ─── Console Matrix Output Form ────────────────────────────────────────────────

class ConsoleMatrixOutputForm(forms.ModelForm):
    class Meta:
        model = ConsoleMatrixOutput
        fields = [
            'matrix_number',
            'name',
            'mono_stereo',
            'destination',
            'omni_out',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['matrix_number'].widget.attrs.update({
            'class': 'w-16 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-36 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['mono_stereo'].widget.attrs.update({
            'class': 'mono-stereo-select'
        })
        self.fields['destination'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })
        self.fields['omni_out'].widget.attrs.update({
            'class': 'w-28 text-center align-middle bg-white text-black rounded-sm',
        })

MatrixOutputFormSet = modelformset_factory(
    ConsoleMatrixOutput,
    form=ConsoleMatrixOutputForm,
    extra=10,
    can_delete=True
)


#----------Device dropdowns--------
from django import forms
from .models import (
    DeviceInput,
    DeviceOutput,
    ConsoleInput,
    ConsoleAuxOutput,
    ConsoleMatrixOutput,
    Console,
)


class DeviceInputInlineForm(forms.ModelForm):
    console_input = forms.ChoiceField(
        label="Console Input",
        required=False,
        widget=forms.Select,
        choices=[],
    )

    class Meta:
        model = DeviceInput
        fields = ("input_number", "console_input")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        grouped = []
        # grab every Console and do Python‐side filtering
        for console in Console.objects.prefetch_related("consoleinput_set"):
            opts = [
                (ci.pk, f"{ci.input_ch}: {ci.source}")
                for ci in console.consoleinput_set.all()
                if ci.source  # only non‐empty, non‐None sources
            ]
            if opts:
                grouped.append((console.name, opts))

        # always start with the blank header
        self.fields["console_input"].choices = [("", "---------")] + grouped

        # if we’re editing an existing DeviceInput, preserve its current value
        if getattr(self, "instance", None) and self.instance.pk:
            self.fields["console_input"].initial = self.instance.console_input_id


class DeviceOutputInlineForm(forms.ModelForm):
    console_output = forms.ChoiceField(
        label="Console Output",
        required=False,
        widget=forms.Select,
        choices=[],
    )

    class Meta:
        model = DeviceOutput
        fields = ("output_number", "console_output")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        grouped = []
        # grab every Console and do Python‐side filtering on both Aux & Matrix outputs
        for console in Console.objects.prefetch_related(
            "consoleauxoutput_set", "consolematrixoutput_set"
        ):
            opts = []
            # Aux outputs
            opts += [
                (ao.pk, f"Aux {ao.aux_number}: {ao.name}")
                for ao in console.consoleauxoutput_set.all()
                if ao.name  # only non‐empty, non‐None names
            ]
            # Matrix outputs
            opts += [
                (mo.pk, f"Mat {mo.matrix_number}: {mo.name}")
                for mo in console.consolematrixoutput_set.all()
                if mo.name
            ]

            if opts:
                grouped.append((console.name, opts))

        self.fields["console_output"].choices = [("", "---------")] + grouped

        # if we’re editing an existing DeviceOutput, preserve its current value
        if getattr(self, "instance", None) and self.instance.pk:
            self.fields["console_output"].initial = self.instance.console_output_id