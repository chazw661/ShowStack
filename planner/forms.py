# planner/forms.py
from django import forms
from django.forms import modelformset_factory
from .models import Input

class InputForm(forms.ModelForm):
    class Meta:
        model = Input
        fields = [
            'channel', 'label', 'device', 'output',
            'dante', 'input_ch', 'source', 'group',
            'dca', 'mute', 'direct_out', 'omni_in', 'omni_out'
        ]

InputFormSet = modelformset_factory(
    Input, form=InputForm, extra=144, can_delete=False
)
