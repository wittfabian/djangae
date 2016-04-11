import cPickle
import pipeline
from mapreduce import context
from mapreduce.mapper_pipeline import MapperPipeline
from mapreduce import pipeline_base

from django.utils.module_loading import import_string
from djangae.contrib.processing.mapreduce.input_readers import DjangoInputReader

from utils import qualname


class DynamicPipeline(pipeline_base.PipelineBase):
    """
        Horrific class which uses pickle to store pipelines for
        yielding via run(). This wouldn't be necessary if the pipeline
        library wasn't built for Java and had a sensible interface that
        didn't require inheritence.
    """
    def __init__(self, pipelines, *args, **kwargs):
        # This gets reinstantiated somewhere with the already-pickled pipelines argument
        # so we prevent double pickling by checking it's not a string
        if not isinstance(pipelines, basestring):
            pipelines = str(cPickle.dumps(pipelines))
        super(DynamicPipeline, self).__init__(pipelines, *args, **kwargs)

    def run(self, pipelines):
        with pipeline.InOrder():
            pipelines = cPickle.loads(str(pipelines))
            for pipe in pipelines:
                yield pipe


class CallbackPipeline(pipeline_base.PipelineBase):
    """
        Simply calls the specified function. Takes a dotted-path to the callback
    """
    def run(self, func):
        func = import_string(func)
        func()


def unpacker(obj):
    params = context.get().mapreduce_spec.mapper.params
    handler = import_string(params["func"])
    yield handler(obj, *params["args"], **params["kwargs"])


def map_queryset(
    queryset, processor_func, finalize_func=None, _shards=None,
    _output_writer=None, _output_writer_kwargs=None, _job_name=None,
    *processor_args, **processor_kwargs
):
    """
        Iterates over a queryset with mapreduce calling process_func for each Django instance.
        Calls finalize_func when the iteration completes.

        output_writer is optional, but should be a mapreduce OutputWriter subclass. Any additional
        args or kwargs are passed down to the handling function.

        Returns the pipeline ID.
    """
    handler_spec = qualname(unpacker)
    handler_params = {
        "func": qualname(processor_func),
        "args": processor_args,
        "kwargs": processor_kwargs
    }

    handler_params.update({
        'input_reader': {
            'model': '{}.{}'.format(queryset.model._meta.app_label, queryset.model.__name__),
            'query': cPickle.dumps(queryset.query)
        }
    })

    pipelines = []
    pipelines.append(MapperPipeline(
        "Map task over {}".format(queryset.model),
        handler_spec=handler_spec,
        input_reader_spec=qualname(DjangoInputReader),
        params=handler_params,
        shards=_shards
    ))

    if finalize_func:
        pipelines.append(CallbackPipeline(qualname(finalize_func)))

    new_pipeline = DynamicPipeline(pipelines)
    new_pipeline.start()


def map_entities(kind_name, processor_func, finalize_func=None, shard_count=None, output_writer=None, output_writer_kwargs=None, job_name=None):
    """
        Iterates over all entities of a particular kind, calling processor_func on each one.
        Calls finalize_func when the iteration completes.

        output_writer is optional, but should be a mapreduce OutputWriter subclass

        Returns the pipeline ID.
    """
    pass


def map_files(bucket_name, process_func, finalize_func=None, shard_count=None, output_writer=None, output_writer_kwargs=None, prefixes=None, job_name=None):
    """
        Iterates over all the files on GoogleCloudStorage

        prefixes should be a list of glob patterns for filename matching

        Returns the pipeline ID.
    """
    pass


def map_reduce_queryset(queryset, map_func, reduce_func, output_writer, finalize_func=None, shard_count=None, output_writer_kwargs=None, job_name=None):
    """
        Does a complete map-shuffle-reduce over the queryset

        output_writer should be a mapreduce OutputWriter subclass

        Returns the pipeline ID.
    """
    pass


def map_reduce_entities(kind_name, map_func, reduce_func, output_writer, finalize_func=None, shard_count=None, output_writer_kwargs=None, job_name=None):
    """
        Does a complete map-shuffle-reduce over the entities

        output_writer should be a mapreduce OutputWriter subclass

        Returns the pipeline ID.
    """
    pass


def pipeline_has_finished(pipeline_id):
    """
        Returns True if the specified pipeline has finished
    """
    pass


def pipeline_in_progress(pipeline_id):
    """
        Returns True if the specified pipeline is in progress
    """
    pass

def get_pipeline_by_id(pipeline_id):
    pass
