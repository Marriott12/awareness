from django.db import models


class CaseStudy(models.Model):
    title = models.CharField(max_length=250)
    summary = models.TextField()
    published = models.BooleanField(default=True)

    def __str__(self):
        return self.title
