from django.shortcuts import render, get_object_or_404
from django.forms import modelformset_factory
from .models import Console, ConsoleInput

def console_detail(request, console_id):
    console = get_object_or_404(Console, pk=console_id)

    InputFormSet = modelformset_factory(
        Input,
        fields=[
            "output", "dante_number", "input_ch", "source", "group",
            "dca", "mute", "direct_out", "omni_in", "omni_out"
        ],
        extra=10,
        can_delete=True
    )

    if request.method == "POST":
        formset = InputFormSet(request.POST, queryset=Input.objects.filter(console=console))
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.console = console
                instance.save()
            for obj in formset.deleted_objects:
                obj.delete()
    else:
        formset = InputFormSet(queryset=Input.objects.filter(console=console))

    consoles = Console.objects.all()

    return render(request, "planner/console_detail.html", {
        "formset": formset,
        "console": console,
        "consoles": consoles
    })
