from mapreduce import input_readers
from django.apps import apps
import logging

class DjangoInputReader(input_readers.InputReader):
    """
    """
    def __init__(self, model_path=None, pk__gt=None, pk__lte=None, filters=None, shard_id=None, db='default'):
        self.model_path = model_path
        try:
            app, model = self.model_path.split('.')
        except ValueError:
            app, model = self.model_path.split(',')
        self.model = apps.get_model(app, model)
        self.pk__gt = pk__gt
        self.pk__lte = pk__lte
        self.filters = filters or {}
        self.shard_id = shard_id
        self.db = db

    def __iter__(self):
        if self.pk__gt is not None:
            self.filters['pk__gt'] = self.pk__gt
        if self.pk__lte is not None:
            self.filters['pk__lte'] = self.pk__lte
        if self.db:
            qs = self.model.objects.using(self.db).filter(**self.filters)
        else:
            qs = self.model.objects.filter(**self.filters)
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
            'db': self.db
        }

    @classmethod
    def split_input(cls, mapper_spec):
        """
        """
        params = input_readers._get_params(mapper_spec)
        db = params.get('db', None)
        try:
            app, model = params['model'].split('.')
        except ValueError:
            app, model = params['model'].split(',')
        model = apps.get_model(app, model)
        filters = params.get('filters', None)

        shard_count = mapper_spec.shard_count
        if db:
            scatter_query = model.objects.using(db)
        else:
            scatter_query = model.objects
        scatter_query = scatter_query.values_list('pk').order_by('__scatter__')
        oversampling_factor = 32
        # FIXME values
        random_keys = [x[0] for x in scatter_query[:shard_count * oversampling_factor]]

        random_keys.sort()
        if len(random_keys) > shard_count:
            random_keys = cls._choose_split_points(random_keys, shard_count)
        keyranges = []
        if len(random_keys) > 1:
            keyranges.append(DjangoInputReader(params['model'], pk__lte=random_keys[0], filters=filters, shard_id=0, db=db))
            for x in xrange((len(random_keys) - 1)):
                keyranges.append(DjangoInputReader(params['model'], pk__gt=random_keys[x], pk__lte=random_keys[x+1], filters=filters, shard_id=x+1, db=db))
            keyranges.append(DjangoInputReader(params['model'], pk__gt=random_keys[x+1], filters=filters, shard_id=x+2, db=db))
        elif len(random_keys) == 1:
            keyranges.append(DjangoInputReader(params['model'], pk__lte=random_keys[0], filters=filters, shard_id=0, db=db))
            keyranges.append(DjangoInputReader(params['model'], pk__gt=random_keys[0], filters=filters, shard_id=1, db=db))
        else:
            keyranges.append(DjangoInputReader(params['model'], filters=filters, shard_id=0, db=db))
        return keyranges

    @classmethod
    def _choose_split_points(cls, sorted_keys, shard_count):
        """
        Returns the best split points given a random set of datastore.Keys.
        """
        assert len(sorted_keys) >= shard_count
        index_stride = len(sorted_keys) / float(shard_count)
        return [sorted_keys[int(round(index_stride * i))] for i in range(1, shard_count)]
