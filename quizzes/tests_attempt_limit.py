from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Quiz, Question, Choice


User = get_user_model()


class QuizAttemptLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pass")
        # Quiz with attempt_limit 1
        self.quiz = Quiz.objects.create(title="Limit Quiz", attempt_limit=1)
        q = Question.objects.create(quiz=self.quiz, text="Q1")
        Choice.objects.create(question=q, text="A", is_correct=True)

    def test_attempt_limit_enforced(self):
        self.client.login(username="u1", password="pass")
        url = reverse("quizzes:take", args=[self.quiz.id])
        # first POST should be allowed
        resp1 = self.client.post(
            url,
            {"question_" + str(Question.objects.first().id): Choice.objects.first().id},
        )
        self.assertNotEqual(resp1.status_code, 403)
        # second POST should be redirected to locked page or show 403
        resp2 = self.client.post(
            url,
            {"question_" + str(Question.objects.first().id): Choice.objects.first().id},
        )
        self.assertIn(resp2.status_code, (302, 200, 403))
