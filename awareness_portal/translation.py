"""Translation configuration for model fields.

Enables multi-language support for training modules, quizzes, policies, and case studies.
"""
from modeltranslation.translator import translator, TranslationOptions
from training.models import TrainingModule
from quizzes.models import Quiz, Question
from policy.models import Policy, Control, Rule
from case_studies.models import CaseStudy


class TrainingModuleTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'content')


class QuizTranslationOptions(TranslationOptions):
    fields = ('title', 'description')


class QuestionTranslationOptions(TranslationOptions):
    fields = ('text', 'explanation')


class PolicyTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


class ControlTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


class RuleTranslationOptions(TranslationOptions):
    fields = ('description',)


class CaseStudyTranslationOptions(TranslationOptions):
    fields = ('title', 'summary', 'content', 'lessons_learned')


# Register translations
translator.register(TrainingModule, TrainingModuleTranslationOptions)
translator.register(Quiz, QuizTranslationOptions)
translator.register(Question, QuestionTranslationOptions)
translator.register(Policy, PolicyTranslationOptions)
translator.register(Control, ControlTranslationOptions)
translator.register(Rule, RuleTranslationOptions)
translator.register(CaseStudy, CaseStudyTranslationOptions)
