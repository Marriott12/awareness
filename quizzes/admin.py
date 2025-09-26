from django.contrib import admin
from .models import Quiz, Question, Choice
from .models import QuizAttempt, QuizResponse


class ChoiceInline(admin.TabularInline):
	model = Choice


class QuestionAdmin(admin.ModelAdmin):
	inlines = [ChoiceInline]


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
	list_display = ('title',)


class QuizResponseInline(admin.TabularInline):
	model = QuizResponse


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
	list_display = ('user', 'quiz', 'score', 'taken_at')
	inlines = [QuizResponseInline]


admin.site.register(Question, QuestionAdmin)
