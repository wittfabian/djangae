
default_app_config = 'djangae.contrib.processing.mapreduce.apps.MapreduceConfig'


def map_queryset(queryset, processor_func, finalize_func=None, shard_count=None, output_writer=None, output_writer_kwargs=None, job_name=None):
    """
        Iterates over a queryset with mapreduce calling process_func for each Django instance.
        Calls finalize_func when the iteration completes.

        output_writer is optional, but should be a mapreduce OutputWriter subclass

        Returns the pipeline ID.
    """
    pass


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
