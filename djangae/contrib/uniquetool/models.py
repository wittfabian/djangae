from django.db import models
from djangae.fields import ListField

ACTION_TYPES = [
    # Verify all models unique contraint markers exist and are assigned to it.
    ('check', 'Check'),
    # Recreate any missing markers
    ('repair', 'Repair'),
    # Remove any marker that isn't properly linked to an instance.
    ('clean', 'Clean'),
]

ACTION_STATUSES = [
    ('running', 'Running'),
    ('done', 'Done'),
]


def get_models():
    return [
        ('model', 'model'),
    ]


class UniqueAction(models.Model):
    action_type = models.CharField(choices=ACTION_TYPES, max_length=100)
    model = models.CharField(max_length=100)
    status = models.CharField(choices=ACTION_STATUSES, default=ACTION_STATUSES[0][0], editable=False, max_length=100)
    #logs = ListField(models.IntegerField(), blank=True, editable=False)



class ActionLog(models.Model):
    instance_key = models.CharField(max_length=255)
    marker_key = models.CharField(max_length=255)
    action = models.ForeignKey(UniqueAction)
