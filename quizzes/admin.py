from django.contrib import admin
from .models import Quiz, Question, Choice
from .models import QuizAttempt, QuizResponse


class ChoiceInline(admin.TabularInline):
    model = Choice


class QuestionAdmin(admin.ModelAdmin):
    inlines = [ChoiceInline]


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "attempt_limit")


class QuizResponseInline(admin.TabularInline):
    model = QuizResponse
    extra = 0
    readonly_fields = ('question', 'selected')


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "quiz", "score", "taken_at")
    readonly_fields = ('user', 'quiz', 'score', 'taken_at')
    inlines = [QuizResponseInline]


@admin.register(QuizResponse)
class QuizResponseAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected")
    readonly_fields = ('attempt', 'question', 'selected')


admin.site.register(Question, QuestionAdmin)
