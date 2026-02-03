from django.db import models


class TrainingModule(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title


class TrainingProgress(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    module = models.ForeignKey(TrainingModule, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Training progress"
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.user.username} - {self.module.title}"
