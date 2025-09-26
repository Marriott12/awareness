from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed demo content: training modules, quizzes, and case studies."

    def handle(self, *args, **options):
        from training.models import TrainingModule
        from quizzes.models import Quiz, Question, Choice
        from case_studies.models import CaseStudy

        # Create training modules
        modules = [
            ("Social Media OPSEC Basics", "Basics about safe posting and privacy."),
            (
                "Handling Requests for Information",
                "How to handle requests and verify identity.",
            ),
            (
                "Cybersecurity Act Overview",
                "Key points from the Cybersecurity Act relevant to personnel.",
            ),
        ]
        for i, (title, content) in enumerate(modules, start=1):
            m, created = TrainingModule.objects.get_or_create(
                slug=title.lower().replace(" ", "-"),
                defaults={"title": title, "content": content, "order": i},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created module: {title}"))

        # Create quizzes
        q, created = Quiz.objects.get_or_create(title="Social Media OPSEC Basics")
        if created:
            ques = Question.objects.create(
                quiz=q, text="Which of the following is safe to post?"
            )
            Choice.objects.create(
                question=ques, text="Your current exact location", is_correct=False
            )
            Choice.objects.create(
                question=ques,
                text="A generic photo without identifiable metadata",
                is_correct=True,
            )
            self.stdout.write(
                self.style.SUCCESS("Created demo quiz: Social Media OPSEC Basics")
            )
        else:
            self.stdout.write("Demo quiz already exists")

        # Case studies
        cs_data = [
            (
                "Operational Leak via Social Media",
                "A unit location was exposed via a photo with geotags.",
            ),
            (
                "Location Exposure and Recon",
                "An individual posted patterns that allowed adversaries to profile movements.",
            ),
        ]
        for title, summary in cs_data:
            cs, created = CaseStudy.objects.get_or_create(
                title=title, defaults={"summary": summary, "published": True}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created case study: {title}"))

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
