from mapreduce.mapreduce_pipeline import MapreducePipeline, MapPipeline
from mapreduce.mapper_pipeline import MapperPipeline
from queryset import QueryDef
import cPickle


class MapReduceTask(object):
    """

        Mapreduce base class

        You must define a staticmethod 'map' which takes in an single arg

        Optionally define a staticmethod 'reduce' for the reduce stage
    """
    shards = 3
    query_def = None
    pipeline = None
    pipeline_class = MapperPipeline
    job_name = None

    def __init__(self, *args, **kwargs):
        if not self.job_name:
            # No job name then we will just use the class
            self.job_name = self.get_class_path()

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
        raise NotImplementedError('You must supply a map function')

    @staticmethod
    def reduce(key, values):
        raise NotImplementedError('No reduce function defined, just running map stage')

    def start(self):
        params = {'querydef': str(cPickle.dumps(self.query_def))}

        self.pipeline = self.pipeline_class(
            self.job_name, # job_name: job name as string.
            self.get_map_path(), # mapper_spec: specification of mapper to use.
            input_reader_spec="djangae.contrib.mappers.readers.DjangoInputReader", # input_reader_spec: specification of input reader to read data from.
            params=params, # mapper_params: parameters to use for mapper phase.
            shards=3 # shards: number of shards to use as int.
        )
        self.pipeline.start()
