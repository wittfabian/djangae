import cPickle
import pipeline
from mapreduce import context
from mapreduce.mapper_pipeline import MapperPipeline
from mapreduce.mapreduce_pipeline import MapreducePipeline
from mapreduce import pipeline_base
from mapreduce.model import MapreduceState
from mapreduce.input_readers import RawDatastoreInputReader, GoogleCloudStorageInputReader

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
        Simply calls the specified function.
        Takes a dotted-path to the callback
    """
    def run(self, func):
        func = import_string(func)
        func()


def unpacker(obj):
    params = context.get().mapreduce_spec.mapper.params
    handler = import_string(params["func"])
    yield handler(obj, *params["args"], **params["kwargs"])


def _do_map(input_reader, processor_func, finalize_func, params, _shards, _output_writer, _output_writer_kwargs, _job_name, *processor_args, **processor_kwargs):
    handler_spec = qualname(unpacker)
    handler_params = {
        "func": qualname(processor_func),
        "args": processor_args,
        "kwargs": processor_kwargs
    }

    handler_params.update(params)

    pipelines = []
    pipelines.append(MapperPipeline(
        _job_name,
        handler_spec=handler_spec,
        input_reader_spec=qualname(input_reader),
        output_writer_spec=qualname(_output_writer) if _output_writer else None,
        params=handler_params,
        shards=_shards
    ))

    if finalize_func:
        pipelines.append(CallbackPipeline(qualname(finalize_func)))

    new_pipeline = DynamicPipeline(pipelines)
    new_pipeline.start()
    return new_pipeline


def map_queryset(
    queryset, processor_func, finalize_func=None, _shards=None,
    _output_writer=None, _output_writer_kwargs=None, _job_name=None,
    *processor_args, **processor_kwargs
):
    """
        Iterates over a queryset with mapreduce calling process_func for
        each Django instance. Calls finalize_func when the iteration completes.

        output_writer is optional, but should be a mapreduce OutputWriter
        subclass. Any additional args or kwargs are passed down to the
        handling function.

        Returns the pipeline
    """
    params = {
        'input_reader': DjangoInputReader.params_from_queryset(queryset),
        'output_writer': _output_writer_kwargs or {}
    }

    return _do_map(
        DjangoInputReader,
        processor_func, finalize_func, params, _shards, _output_writer,
        _output_writer_kwargs,
        _job_name or "Map task over {}".format(queryset.model),
        *processor_args, **processor_kwargs
    )


def map_files(
    processor_func, bucketname, filenames=None, finalize_func=None, _shards=None,
    _output_writer=None, _output_writer_kwargs=None, _job_name=None,
    *processor_args, **processor_kwargs
):
    """
        Iterates over files in cloudstorage matching patterns in filenames list.

        output_writer is optional, but should be a mapreduce OutputWriter
        subclass. Any additional args or kwargs are passed down to the
        handling function.

        Returns the pipeline
    """
    if filenames is None:
        filenames = ['*']

    params = {
        'input_reader': {
            GoogleCloudStorageInputReader.OBJECT_NAMES_PARAM: filenames,
            GoogleCloudStorageInputReader.BUCKET_NAME_PARAM: bucketname,
        },
        'output_writer': _output_writer_kwargs or {}
    }

    return _do_map(
        GoogleCloudStorageInputReader,
        processor_func, finalize_func, params, _shards, _output_writer,
        _output_writer_kwargs,
        _job_name or "Map task over files {} in {}".format(filenames, bucketname),
        *processor_args, **processor_kwargs
    )


def map_entities(kind_name, processor_func, finalize_func=None, _shards=None, _output_writer=None, _output_writer_kwargs=None, _job_name=None, *processor_args, **processor_kwargs):
    """
        Iterates over all entities of a particular kind, calling processor_func
        on each one.
        Calls finalize_func when the iteration completes.

        output_writer is optional, but should be a mapreduce
        OutputWriter subclass

        Returns the pipeline
    """
    params = {
        'input_reader': {RawDatastoreInputReader.ENTITY_KIND_PARAM: kind_name},
        'output_writer': _output_writer_kwargs or {}
    }

    return _do_map(
        RawDatastoreInputReader,
        processor_func, finalize_func, params, _shards, _output_writer,
        _output_writer_kwargs,
        _job_name or "Map task over {}".format(kind_name),
        *processor_args, **processor_kwargs
    )


def map_reduce_queryset(queryset, map_func, reduce_func, output_writer, finalize_func=None, shard_count=None, output_writer_kwargs=None, job_name=None):
    """
        Does a complete map-shuffle-reduce over the queryset

        output_writer should be a mapreduce OutputWriter subclass

        Returns the pipeline
    """
    map_func = qualname(map_func)
    reduce_func = qualname(reduce_func)
    output_writer = qualname(output_writer)
    pipeline = MapreducePipeline(
        job_name or "Map task over {}".format(queryset.model),
        map_func,
        reduce_func,
        qualname(DjangoInputReader),
        output_writer,
        mapper_params={
            "input_reader": DjangoInputReader.params_from_queryset(queryset),
        },
        reducer_params={
            "output_writer": output_writer_kwargs
        },
        shards=shard_count)
    pipeline.start()
    return pipeline


def map_reduce_entities(kind_name, map_func, reduce_func, output_writer, finalize_func=None, shard_count=None, output_writer_kwargs=None, job_name=None):
    """
        Does a complete map-shuffle-reduce over the entities

        output_writer should be a mapreduce OutputWriter subclass

        Returns the pipeline
    """
    map_func = qualname(map_func)
    reduce_func = qualname(reduce_func)
    output_writer = qualname(output_writer)
    pipeline = MapreducePipeline(
        job_name or "Map task over {}".format(kind_name),
        map_func,
        reduce_func,
        qualname(RawDatastoreInputReader),
        output_writer,
        mapper_params={
            'input_reader': {
                RawDatastoreInputReader.ENTITY_KIND_PARAM: kind_name
            },
        },
        reducer_params={
            "output_writer": output_writer_kwargs or {}
        },
        shards=shard_count
    )
    pipeline.start()
    return pipeline


def pipeline_has_finished(pipeline_id):
    """
        Returns True if the specified pipeline has finished
    """
    pipe = get_pipeline_by_id(pipeline_id)
    return pipe.has_finalized


def pipeline_in_progress(pipeline_id):
    """
        Returns True if the specified pipeline is in progress
    """
    return not pipeline_has_finished(pipeline_id)


def get_pipeline_by_id(pipeline_id):
    return pipeline.Pipeline.from_id(pipeline_id)


def get_mapreduce_state(pipeline):
    mapreduce_id = pipeline.outputs.job_id.value
    mapreduce_state = MapreduceState.get_by_job_id(mapreduce_id)
    return mapreduce_state
