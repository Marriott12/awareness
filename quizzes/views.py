from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Quiz, Question, Choice, QuizAttempt, QuizResponse


def quizzes_list(request):
	quizzes = Quiz.objects.all()
	return render(request, 'quizzes_list.html', {'quizzes': quizzes})


@login_required
def take_quiz(request, quiz_id):
	quiz = get_object_or_404(Quiz, pk=quiz_id)
	questions = quiz.questions.all()

	# enforce per-user attempt limit
	if quiz.attempt_limit:
		existing = QuizAttempt.objects.filter(quiz=quiz, user=request.user).count()
		if existing >= quiz.attempt_limit:
			return render(request, 'quizzes_locked.html', {'quiz': quiz, 'limit': quiz.attempt_limit})

	if request.method == 'POST':
		total = questions.count()
		correct = 0
		attempt = QuizAttempt.objects.create(user=request.user, quiz=quiz, score=0)
		details = []
		for q in questions:
			selected_id = request.POST.get(str(q.id))
			selected = None
			if selected_id:
				try:
					selected = Choice.objects.get(pk=int(selected_id), question=q)
				except Choice.DoesNotExist:
					selected = None
			is_correct = selected.is_correct if selected else False
			if is_correct:
				correct += 1
			# record response
			if selected:
				QuizResponse.objects.create(attempt=attempt, question=q, selected=selected)
			details.append({'question': q, 'selected': selected, 'is_correct': is_correct})
		score = (correct / total) * 100 if total else 0
		attempt.score = score
		attempt.save()
		return render(request, 'quizzes_result.html', {'quiz': quiz, 'score': score, 'correct': correct, 'total': total, 'details': details})

	return render(request, 'quizzes_take.html', {'quiz': quiz, 'questions': questions})
