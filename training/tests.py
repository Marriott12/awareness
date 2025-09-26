from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import TrainingModule, TrainingProgress


class TrainingProgressTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user('tp', 'tp@example.com', 'pass')
		self.module = TrainingModule.objects.create(title='M1', slug='m1', content='c')

	def test_mark_complete(self):
		self.client.login(username='tp', password='pass')
		resp = self.client.post(f'/training/{self.module.slug}/', follow=True)
		self.assertTrue(TrainingProgress.objects.filter(user=self.user, module=self.module).exists())
