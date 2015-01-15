from mapreduce.mapreduce_pipeline import MapreducePipeline, MapPipeline
from mapreduce.mapper_pipeline import MapperPipeline
from queryset import QueryDef
import cPickle


class MapReduceTask(object):
    """

        Mapreduce base class, inherit this in a statically defined class and
        use .start() to run a mapreduce task

        You must define a staticmethod 'map' which takes in an single arg
        Optionally define a staticmethod 'reduce' for the reduce stage (Not Implemented)

    """
    shards = 3
    query_def = None # Needs to be overwritten with a queryDef
    pipeline_class = MapperPipeline # Defaults to MapperPipeline which just runs map stage
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
        """
        Override this definition with a staticmethod map definition

        """
        raise NotImplementedError('You must supply a map function')

    @staticmethod
    def reduce(key, values):
        pass

    def start(self):
        params = {'querydef': str(cPickle.dumps(self.query_def))}

        pipeline = self.pipeline_class(
            self.job_name, # job_name: job name as string.
            self.get_map_path(), # mapper_spec: specification of mapper to use.
            input_reader_spec="djangae.contrib.mappers.readers.DjangoInputReader", # input_reader_spec: specification of input reader to read data from.
            params=params, # mapper_params: parameters to use for mapper phase.
            shards=3 # shards: number of shards to use as int.
        )
        pipeline.start()
