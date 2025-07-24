from django import forms
from django.forms import modelformset_factory
from .models import ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput

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