from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Avg, Count
from quizzes.models import QuizAttempt, Quiz
from training.models import TrainingModule, TrainingProgress
from django.contrib.auth import get_user_model
import json
import logging

logger = logging.getLogger(__name__)


@login_required
def home(request):
    logger.debug('dashboard.home called; user=%s authenticated=%s is_staff=%s is_superuser=%s', request.user, request.user.is_authenticated, getattr(request.user, 'is_staff', False), getattr(request.user, 'is_superuser', False))
    # For staff/superuser render admin dashboard directly (avoid redirect)
    if request.user.is_staff or request.user.is_superuser:
        return admin_dashboard(request)
    return user_dashboard(request)


@login_required
def user_dashboard(request):
    attempts_qs = QuizAttempt.objects.filter(user=request.user).order_by("-taken_at")[
        :10
    ]
    # Serialize for Chart.js — convert datetimes to ISO strings
    attempts_json = json.dumps([
        {
            "score": float(a.score),
            "taken_at": a.taken_at.isoformat(),
            "quiz__title": a.quiz.title,
        }
        for a in attempts_qs
    ])
    progress = TrainingProgress.objects.filter(user=request.user).select_related(
        "module"
    )[:10]
    return render(
        request,
        "dashboard.html",
        {"attempts": attempts_qs, "progress": progress, "attempts_json": attempts_json},
    )


@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_dashboard(request):
    User = get_user_model()
    attempts_qs = QuizAttempt.objects.select_related("user", "quiz").order_by("-taken_at")[:20]
    recent_attempts = list(attempts_qs)

    avg_score = QuizAttempt.objects.aggregate(avg=Avg("score"))["avg"] or 0
    total_attempts = QuizAttempt.objects.count()
    module_count = TrainingModule.objects.count()
    active_modules = TrainingProgress.objects.values("module").distinct().count()
    user_count = User.objects.count()
    quiz_count = Quiz.objects.count()

    # Top scorers: users with highest average score (min 2 attempts)
    top_scorers = (
        QuizAttempt.objects.values("user__username")
        .annotate(avg=Avg("score"), attempts=Count("id"))
        .filter(attempts__gte=2)
        .order_by("-avg")[:5]
    )

    return render(
        request,
        "admin_dashboard.html",
        {
            "attempts": recent_attempts,
            "module_count": module_count,
            "active_modules": active_modules,
            "user_count": user_count,
            "quiz_count": quiz_count,
            "avg_score": avg_score,
            "total_attempts": total_attempts,
            "top_scorers": top_scorers,
        },
    )
