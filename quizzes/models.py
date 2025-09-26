from django.db import models


class Quiz(models.Model):
    title = models.CharField(max_length=200)
    attempt_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Optional per-user attempt limit"
    )

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, related_name="questions", on_delete=models.CASCADE)
    text = models.TextField()

    def __str__(self):
        return self.text[:50]


class Choice(models.Model):
    question = models.ForeignKey(
        Question, related_name="choices", on_delete=models.CASCADE
    )
    text = models.CharField(max_length=400)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.FloatField()
    taken_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} - {self.score}"


class QuizResponse(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt, related_name="responses", on_delete=models.CASCADE
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected = models.ForeignKey(Choice, on_delete=models.CASCADE)

    def __str__(self):
        return (
            f"{self.attempt.user.username} - {self.question.id} -> {self.selected.id}"
        )
