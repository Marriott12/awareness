from django.urls import path
from . import views

urlpatterns = [
    path('', views.quizzes_list, name='quizzes_list'),
    path('<int:quiz_id>/take/', views.take_quiz, name='take_quiz'),
]
