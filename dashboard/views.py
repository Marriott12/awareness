from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from quizzes.models import QuizAttempt
from training.models import TrainingProgress


@login_required
def home(request):
	# route to admin dashboard if staff/superuser
	if request.user.is_staff or request.user.is_superuser:
		return admin_dashboard(request)
	return user_dashboard(request)


@login_required
def user_dashboard(request):
	attempts_qs = QuizAttempt.objects.filter(user=request.user).order_by('-taken_at')[:10]
	attempts = list(attempts_qs.values('score', 'taken_at', 'quiz__title'))
	progress = TrainingProgress.objects.filter(user=request.user).select_related('module')[:10]
	return render(request, 'dashboard.html', {'attempts': attempts_qs, 'progress': progress, 'attempts_json': attempts})


@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_dashboard(request):
	# simple admin summary: recent attempts site-wide + user/module counts
	attempts_qs = QuizAttempt.objects.all().order_by('-taken_at')[:20]
	recent_attempts = list(attempts_qs.select_related('user', 'quiz')[:20])
	module_count = TrainingProgress.objects.values('module').distinct().count()
	user_count = request._request.__class__ and None  # placeholder to keep template flexible
	return render(request, 'admin_dashboard.html', {'attempts': recent_attempts, 'module_count': module_count})
