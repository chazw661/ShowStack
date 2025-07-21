# planner/forms.py
from django import forms
from django.forms import modelformset_factory
from .models import Input

class ConsoleInputForm(forms.ModelForm):
    class Meta:
        model = ConsoleInput  # or whatever your model is called
        fields = [
            'dante_number',
            'channel',
            'source',
            'group',
            'dca',
            'mute',
            'direct_out',
            'omni_in',
            'omni_out',
        ]


InputFormSet = modelformset_factory(
    Input, form=InputForm, extra=144, can_delete=True
)
