from django.test import TestCase
from django.db import models

class User(models.Model):
	username = models.CharField(max_length=32)
	email = models.EmailField()

	def __unicode__(self):
		return self.username

class MultiTableParent(models.Model):
	parent_field = models.CharField(max_length=32)

class MultiTableChildOne(MultiTableParent):
	child_one_field = models.CharField(max_length=32)

class MultiTableChildTwo(MultiTableParent):
	child_two_field = models.CharField(max_length=32)

class EdgeCaseTests(TestCase):
	def setUp(self):
		User.objects.create(username="A", email="test@example.com")
		User.objects.create(username="B", email="test@example.com")
		User.objects.create(username="C", email="test2@example.com")
		User.objects.create(username="D", email="test3@example.com")
		User.objects.create(username="E", email="test3@example.com")

	def test_multi_table_inheritance(self):
		parent = MultiTableParent.objects.create(parent_field="parent1")
		child1 = MultiTableChildOne.objects.create(parent_field="child1", child_one_field="child1")
		child2 = MultiTableChildTwo.objects.create(parent_field="child2", child_two_field="child2")

		self.assertEqual(3, MultiTableParent.objects.count())
		self.assertItemsEqual([parent.pk, child1.pk, child2.pk], list(MultiTableParent.objects.values_list('pk', flat=True)))
		self.assertEqual(1, MultiTableChildOne.objects.count())
		self.assertEqual(child1, MultiTableChildOne.objects.get())

		self.assertEqual(1, MultiTableChildTwo.objects.count())
		self.assertEqual(child2, MultiTableChildTwo.objects.get())

	def test_unusual_queries(self):
		results = User.objects.all()
		self.assertEqual(5, len(results))

		results = User.objects.filter(username__in=["A", "B"])
		self.assertEqual(2, len(results))
		self.assertItemsEqual(["A", "B"], [x.username for x in results])

		results = User.objects.filter(username__in=["A", "B"]).exclude(username="A")
		self.assertEqual(1, len(results), results)
		self.assertItemsEqual(["B"], [x.username for x in results])

		results = User.objects.filter(username__lt="E")
		self.assertEqual(4, len(results))
		self.assertItemsEqual(["A", "B", "C", "D"], [x.username for x in results])

		results = User.objects.filter(username__lte="E")
		self.assertEqual(5, len(results))

		#Double exclude not supported
		with self.assertRaises(RuntimeError):
			list(User.objects.exclude(username="E").exclude(username="A"))

		results = User.objects.filter(username="A", email="test@example.com")
		self.assertEqual(1, len(results))

	def test_counts(self):
		self.assertEqual(5, User.objects.count())
		self.assertEqual(2, User.objects.filter(email="test3@example.com").count())
		self.assertEqual(3, User.objects.exclude(email="test3@example.com").count())
		self.assertEqual(1, User.objects.filter(username="A").exclude(email="test3@example.com").count())

		with self.assertRaises(RuntimeError):
			list(User.objects.exclude(username="E").exclude(username="A"))
		
