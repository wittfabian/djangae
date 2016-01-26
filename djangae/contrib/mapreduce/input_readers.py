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
        self.filters = filters
        self.shard_id = shard_id
        self.db = db
        logging.info('DB IS {0}'.format(self.db))

    def __iter__(self):
        filters = {}
        if self.pk__gt is not None:
            filters['pk__gt'] = self.pk__gt
        if self.pk__lte is not None:
            filters['pk__lte'] = self.pk__lte
        qs = self.model.objects.using(self.db).filter(**filters)
        for model in qs.order_by('pk'):
            logging.info(model._state.db)
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
        try:
            app, model = params['model'].split('.')
        except ValueError:
            app, model = params['model'].split(',')
        model = apps.get_model(app, model)
        filters = params.get('filters', None)

        shard_count = mapper_spec.shard_count
        scatter_query = model.objects.using(params['db']).values_list('pk').order_by('__scatter__')
        oversampling_factor = 32
        # FIXME values
        random_keys = [x[0] for x in scatter_query[:shard_count * oversampling_factor]]

        random_keys.sort()
        if len(random_keys) > shard_count:
            random_keys = cls._choose_split_points(random_keys, shard_count) + [None,]
        keyranges = []
        logging.info('DB WILL BE {0}'.format(params['db']))
        if len(random_keys) > 2:
            for i, key in enumerate(random_keys):
                if key is None:
                    break
                if i == 0:
                    keyranges.append(DjangoInputReader(params['model'], pk__lte=key, filters=filters, shard_id=i, db=params['db']))
                keyranges.append(DjangoInputReader(params['model'], pk__gt=key, pk__lte=random_keys[i+1], filters=filters, shard_id=i+1, db=params['db']))
        elif len(random_keys) == 2:
            keyranges.append(DjangoInputReader(params['model'], pk__lte=random_keys[0], filters=filters, shard_id=0, db=params['db']))
            keyranges.append(DjangoInputReader(params['model'], pk__gt=random_keys[0], pk__lte=random_keys[1], filters=filters, shard_id=1, db=params['db']))
            keyranges.append(DjangoInputReader(params['model'], pk__gt=random_keys[1], filters=filters, shard_id=2, db=params['db']))
        elif len(random_keys) == 1:
            keyranges.append(DjangoInputReader(params['model'], pk__lte=random_keys[0], filters=filters, shard_id=0, db=params['db']))
            keyranges.append(DjangoInputReader(params['model'], pk__gt=random_keys[0], filters=filters, shard_id=0, db=params['db']))
        return keyranges

    @classmethod
    def _choose_split_points(cls, sorted_keys, shard_count):
        """
        Returns the best split points given a random set of datastore.Keys.
        """
        assert len(sorted_keys) >= shard_count
        index_stride = len(sorted_keys) / float(shard_count)
        return [sorted_keys[int(round(index_stride * i))] for i in range(1, shard_count)]
