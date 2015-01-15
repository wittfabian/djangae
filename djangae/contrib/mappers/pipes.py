from mapreduce.mapper_pipeline import MapperPipeline
import cPickle


class MapReduceTask(object):
    """

        Mapreduce base class, inherit this in a statically defined class and
        use .start() to run a mapreduce task

        You must define a staticmethod 'map' which takes in an single arg
        Optionally define a staticmethod 'reduce' for the reduce stage (Not Implemented)

    """
    shard_count = 3
    query_def = None # Needs to be overwritten with a queryDef
    pipeline_class = MapperPipeline # Defaults to MapperPipeline which just runs map stage
    job_name = None
    queue_name = 'default'
    output_writer_spec = None
    base_path = '/_ah/mapreduce'
    output_writer_spec = None
    mapreduce_parameters = {}
    countdown = None
    eta = None
    model = None


    def __init__(self, *args, **kwargs):
        if not self.job_name:
            # No job name then we will just use the class
            self.job_name = self.get_class_path()

    def get_model_app_(self):
        app = self.model._meta.app_label
        name = self.model.__name__
        return '{app}.{name}'.format(
            app=app,
            name=name,
        )

    def get_class_path(self):
        return '{mod}.{cls}'.format(
            mod=self.__class__.__module__,
            cls=self.__class__.__name__,
        )

    def get_map_path(self):
        return '{cls}.{func}'.format(
            cls=self.get_class_path(),
            func=self.map.__name__
        )

    def get_reduce_path(self):
        return '{cls}.{func}'.format(
            cls=self.get_class_path(),
            func=self.reduce.__name__
        )

    @staticmethod
    def map(entity):
        """
        Override this definition with a staticmethod map definition

        """
        raise NotImplementedError('You must supply a map function')

    @staticmethod
    def reduce(key, values):
        pass

    def start(self):
        from mapreduce.control import start_map
        mapper_parameters = {'model': self.get_model_app_()}

        start_map(
            self.job_name,
            self.get_map_path(),
            'djangae.contrib.mappers.readers.DjangoInputReader',
            mapper_parameters,
            shard_count=self.shard_count,
            output_writer_spec=self.output_writer_spec,
            mapreduce_parameters=None,
            base_path=self.base_path,
            queue_name=self.queue_name,
            eta=self.eta,
            countdown=self.countdown,
            # hooks_class_name=None,
            # _app=None,
            # in_xg_transaction=False
        )


        # pipeline = self.pipeline_class(
        #     self.job_name, # job_name: job name as string.
        #     self.get_map_path(), # mapper_spec: specification of mapper to use.
        #     input_reader_spec="djangae.contrib.mappers.readers.DjangoInputReader", # input_reader_spec: specification of input reader to read data from.
        #     params=mapper_parameters, # mapper_params: parameters to use for mapper phase.
        #     shards=self.shards, # shards: number of shards to use as int.
        # )
        # pipeline.start(base_path='/_ah/mapreduce/pipeline')
