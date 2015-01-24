from mapreduce.mapper_pipeline import MapperPipeline
from mapreduce import parameters
from mapreduce import control
from mapreduce import context
from pipeline.util import for_name


DJANGAE_MAPREDUCE_BASE_PATH = '/_ah/mapreduce'


class DjangaeMapperPipeline(MapperPipeline):

    def run(self, job_name, handler_spec, input_reader_spec, output_writer_spec=None, params=None, shards=None):
        """
            Overwritting this method allows us to pass the base_path properly, I know it's stupid but I think
            this is the cleanest way that still gives us a working Pipeline that we can chain
        """
        if shards is None:
          shards = parameters.config.SHARD_COUNT

        mapreduce_id = control.start_map(
            job_name,
            handler_spec,
            input_reader_spec,
            params or {},
            mapreduce_parameters={
                "done_callback": self.get_callback_url(),
                "done_callback_method": "GET",
                "pipeline_id": self.pipeline_id,
                "base_path": DJANGAE_MAPREDUCE_BASE_PATH
            },
            shard_count=shards,
            output_writer_spec=output_writer_spec,
            queue_name=self.queue_name,
            )
        self.fill(self.outputs.job_id, mapreduce_id)
        self.set_status(console_url="%s/detail?mapreduce_id=%s" % (
            (parameters.config.BASE_PATH, mapreduce_id)))

    def callback(self, **kwargs):
        """
            Callback finish exists on the pipeline class, so we just use it as a nice
            wrapper for the static method attached to the MapReduceTask
        """
        ctx = context.get()
        params = ctx.mapreduce_spec.mapper.params
        finish_func = params.get('_finish', None)
        finish_func = for_name(finish_func)
        return finish_func(**kwargs)


class MapReduceTask(object):
    """
        MapReduceTask base class, inherit this in a statically defined class and
        use .start() to run a mapreduce task

        You must define a staticmethod 'map' which takes in an arg of the entity being mapped over.
        Optionally define a staticmethod 'reduce' for the reduce stage (Not Implemented).

        You can pass any additional args and/or kwargs to .start(), which will then be passed into
        each call of .map() for you.

        Overwrite 'finish' with a static definition for a finish callback
    """
    shard_count = 3
    pipeline_class = MapperPipeline # Defaults to MapperPipeline which just runs map stage
    job_name = None
    queue_name = 'default'
    output_writer_spec = None
    pipeline_base_path = '/_ah/mapreduce/pipeline'
    output_writer_spec = None
    mapreduce_parameters = {}
    countdown = None
    eta = None
    model = None
    map_args = []
    map_kwargs = {}


    def __init__(self, model=None):
        if model:
            self.model = model
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

    def get_finish_path(self):
        return '{cls}.{func}'.format(
            cls=self.get_class_path(),
            func=self.finish.__name__
        )

    @staticmethod
    def map(entity, *args, **kwargs):
        """
            Override this definition with a staticmethod map definition
        """
        raise NotImplementedError('You must supply a map function')

    @staticmethod
    def reduce(key, values):
        """
            Override this with a static method for the reduce phase
        """
        raise NotImplementedError('You must supply a reduce function')

    @staticmethod
    def finish(**kwargs):
        """
            Override this with a static method for the finish callback
        """
        raise NotImplementedError('You must supply a finish function')

    def start(self, *args, **kwargs):
        mapper_parameters = {
            'model': self.get_model_app_(),
            '_map': self.get_map_path(),
            '_finish': self.get_finish_path(),
            'kwargs': kwargs,
            'args': args,
        }

        pipe = DjangaeMapperPipeline(
            self.job_name,
            'djangae.contrib.mappers.pipes.thunk_map',
            'djangae.contrib.mappers.readers.DjangoInputReader',
            params=mapper_parameters,
            shards=self.shard_count
        )
        pipe.start(base_path=self.pipeline_base_path)



def thunk_map(x):
    """
        This is the default map function that wraps the static map function.

        It allows you to pass args and kwargs to your map function for defining
        more dynamic mappers
    """
    from mapreduce import context
    ctx = context.get()
    params = ctx.mapreduce_spec.mapper.params
    map_func = params.get('_map', None)
    args = params.get('args', [])
    kwargs = params.get('kwargs', {})
    map_func = for_name(map_func)
    return map_func(x, *args, **kwargs)
