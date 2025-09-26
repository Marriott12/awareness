from django.urls import path
from . import views

app_name = "quizzes"

urlpatterns = [
    path("", views.quizzes_list, name="list"),
    path("<int:quiz_id>/take/", views.take_quiz, name="take"),
]
