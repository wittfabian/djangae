from django.db import models
from djangae.fields import ListField
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models.loading import cache as model_cache
from djangae.contrib.mappers.pipes import MapReduceTask


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

def encode_model(model):
    return "%s,%s" % (model._meta.app_label, model._meta.model_name)

def decode_model(model_str):
    return model_cache.get_model(*model_str.split(','))


class UniqueAction(models.Model):
    action_type = models.CharField(choices=ACTION_TYPES, max_length=100)
    model = models.CharField(max_length=100)
    status = models.CharField(choices=ACTION_STATUSES, default=ACTION_STATUSES[0][0], editable=False, max_length=100)
    #logs = ListField(models.IntegerField(), blank=True, editable=False)


class ActionLog(models.Model):
    instance_key = models.CharField(max_length=255)
    marker_key = models.CharField(max_length=255)
    action = models.ForeignKey(UniqueAction)


@receiver(post_save, sender=UniqueAction)
def start_action(sender, instance, created, raw, **kwargs):
    if created == False:
        # we are saving because status is now "done"?
        import pdb; pdb.set_trace()
        return

    mapper = ActionMapper(model=decode_model(instance.model))
    mapper.start(action_pk=instance.pk)


class ActionMapper(MapReduceTask):
    name = 'action_map'

    @staticmethod
    def map(entity, *args, **kwargs):
        import pdb; pdb.set_trace()
        #if entity.counter % 2:
        #    entity.delete()
        #    yield ('removed', [entity.pk])
        #else:
        yield ('remains', [entity.pk])
