from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import TrainingModule, TrainingProgress


def module_list(request):
    modules = TrainingModule.objects.all()
    completed = []
    if request.user.is_authenticated:
        completed = TrainingProgress.objects.filter(user=request.user).values_list(
            "module_id", flat=True
        )
    return render(
        request, "training_list.html", {"modules": modules, "completed": completed}
    )


@login_required
def module_detail(request, slug):
    module = get_object_or_404(TrainingModule, slug=slug)
    if request.method == "POST":
        # mark complete
        TrainingProgress.objects.get_or_create(user=request.user, module=module)
        return redirect("training_list")
    return render(request, "training_detail.html", {"module": module})
