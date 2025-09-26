from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Quiz, Question, Choice, QuizAttempt


class QuizScoringTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "tester", "t@example.com", "pass"
        )
        self.quiz = Quiz.objects.create(title="Test Quiz")
        q = Question.objects.create(quiz=self.quiz, text="Q1")
        Choice.objects.create(question=q, text="A", is_correct=True)
        Choice.objects.create(question=q, text="B", is_correct=False)

    def test_scoring(self):
        self.client.login(username="tester", password="pass")
        self.client.post(f"/quizzes/{self.quiz.id}/take/", data={"1": "1"})
        # after submission should create a QuizAttempt
        self.assertEqual(
            QuizAttempt.objects.filter(user=self.user, quiz=self.quiz).count(), 1
        )
