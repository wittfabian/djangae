from django.test import TestCase

from django.contrib.auth.models import User

class EdgeCaseTests(TestCase):
	def setUp(self):
		User.objects.create(username="A", email="test@example.com")
		User.objects.create(username="B", email="test@example.com")
		User.objects.create(username="C", email="test2@example.com")
		User.objects.create(username="D", email="test3@example.com")
		User.objects.create(username="E", email="test3@example.com")

	def test_unusual_queries(self):
		results = User.objects.all()
		self.assertEqual(5, len(results))

		results = User.objects.filter(username__in=["A", "B"])
		self.assertEqual(2, len(results))
		self.assertItemsEqual(["A", "B"], [x.username for x in results])

		results = User.objects.filter(username__in=["A", "B"]).exclude(username="A")
		self.assertEqual(1, len(results))
		self.assertItemsEqual(["A"], [x.username for x in results])

		results = User.objects.filter(username__lt="E")
		self.assertEqual(4, len(results))
		self.assertItemsEqual(["A", "B", "C", "D"], [x.username for x in results])

		results = User.objects.filter(username__lte="E")
		self.assertEqual(5, len(results))

		#Double exclude not supported
		qs = User.objects.exclude(username="E").exclude(username="A")		
		self.assertRaises(RuntimeError, qs)

	def test_counts(self):
		self.assertEqual(5, User.objects.count())
		self.assertEqual(2, User.objects.filter(email="test3@example.com").count())
		self.assertEqual(3, User.objects.exclude(email="test3@example.com").count())
		self.assertEqual(1, User.objects.filter(username="A").exclude(email="test3@example.com").count())

		qs = User.objects.exclude(username="E").exclude(username="A")		
		self.assertRaises(RuntimeError, qs)
		