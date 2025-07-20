from django.shortcuts import render, get_object_or_404
from .models import Console, Input, Output


def console_list(request):
    consoles = Console.objects.all()
    return render(request, "planner/console_detail.html", {
    "console": console,
    "formset": input_formset,
    "output_formset": output_formset,
})


from django.forms import modelformset_factory
from django.shortcuts import render, get_object_or_404, redirect
from .models import Console, Input, Output

def console_detail(request, console_id):
    console = get_object_or_404(Console, id=console_id)
    consoles = Console.objects.all()


    InputFormSet = modelformset_factory(Input, fields='__all__', extra=10, can_delete=True)
    OutputFormSet = modelformset_factory(Output, fields='__all__', extra=10, can_delete=True)

    if request.method == 'POST':
        input_formset = InputFormSet(request.POST, queryset=Input.objects.filter(console=console))
        output_formset = OutputFormSet(request.POST, queryset=Output.objects.filter(console=console))

        if input_formset.is_valid() and output_formset.is_valid():
            inputs = input_formset.save(commit=False)
            outputs = output_formset.save(commit=False)

            for form in inputs:
                form.console = console
                form.save()
            for form in outputs:
                form.console = console
                form.save()

            input_formset.save_m2m()
            output_formset.save_m2m()

            return redirect('console_detail', console_id=console.id)
    else:
        input_formset = InputFormSet(queryset=Input.objects.filter(console=console))
        output_formset = OutputFormSet(queryset=Output.objects.filter(console=console))

    return render(request, "planner/console_detail.html", {
    "console": console,
    "consoles": consoles,  # ✅ Add this
    "formset": input_formset,
    "output_formset": output_formset,
})



