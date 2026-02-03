from django.db import models


class CaseStudy(models.Model):
    title = models.CharField(max_length=250)
    summary = models.TextField()
    published = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Case studies"

    def __str__(self):
        return self.title
