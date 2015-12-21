from mapreduce import input_readers
from django.apps import apps


class DjangoInputReader(input_readers.InputReader):
    """
    """
    def __init__(self, model_path=None, pk__gt=None, pk__lte=None, filters=None, shard_id=None):
        self.model_path = model_path
        app, model = self.model_path.split('.')
        self.model = apps.get_model(app, model)
        self.pk__gt = pk__gt
        self.pk__lte = pk__lte
        self.filters = filters
        self.shard_id = shard_id

    def __iter__(self):
        filters = {}
        if self.pk__gt is not None:
            filters['pk__gt'] = self.pk__gt
        if self.pk__lte is not None:
            filters['pk__lte'] = self.pk__lte
        qs = self.model.objects.filter(**filters)
        for model in qs.order_by('pk'):
            yield model

    @classmethod
    def from_json(cls, input_shard_state):
        """
        """
        return cls(**input_shard_state)

    def to_json(self):
        """
        """
        return {
            'model_path': self.model_path,
            'pk__gt': self.pk__gt,
            'pk__lte': self.pk__lte,
            'filters': self.filters,
            'shard_id': self.shard_id,
        }

    @classmethod
    def split_input(cls, mapper_spec):
        """
        """
        params = input_readers._get_params(mapper_spec)
        app, model = params['model'].split('.')
        model = apps.get_model(app, model)
        filters = params.get('filters', None)

        shard_count = mapper_spec.shard_count
        scatter_query = model.objects.values_list('pk').order_by('__scatter__')
        oversampling_factor = 32
        # FIXME values
        random_keys = [x[0] for x in scatter_query[:shard_count * oversampling_factor]]

        random_keys.sort()
        if len(random_keys) > shard_count:
            random_keys = cls._choose_split_points(random_keys, shard_count) + [None,]
        keyranges = []
        for i, key in enumerate(random_keys):
            if key is None:
                break
            if i == 0:
                keyranges.append(DjangoInputReader(params['model'], pk__lte=key, filters=filters, shard_id=i))
            keyranges.append(DjangoInputReader(params['model'], pk__gt=key, pk__lte=random_keys[i+1], filters=filters, shard_id=i+1))
        return keyranges

    @classmethod
    def _choose_split_points(cls, sorted_keys, shard_count):
        """
        Returns the best split points given a random set of datastore.Keys.
        """
        assert len(sorted_keys) >= shard_count
        index_stride = len(sorted_keys) / float(shard_count)
        return [sorted_keys[int(round(index_stride * i))] for i in range(1, shard_count)]
