from django.contrib import admin
from .models import TrainingModule, TrainingProgress


@admin.register(TrainingModule)
class TrainingModuleAdmin(admin.ModelAdmin):
	list_display = ('title', 'slug', 'order')
	prepopulated_fields = {"slug": ("title",)}


@admin.register(TrainingProgress)
class TrainingProgressAdmin(admin.ModelAdmin):
	list_display = ('user', 'module', 'completed_at')
