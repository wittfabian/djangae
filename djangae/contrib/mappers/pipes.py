from mapreduce.mapreduce_pipeline import MapreducePipeline, MapPipeline
from mapreduce.mapper_pipeline import MapperPipeline
from queryset import QueryDef
import cPickle


def start_django_orm_mapper(query_def, func, job_name, shards=3):
    """ Wrapper function for launching a map job """

    params = {'querydef': str(cPickle.dumps(query_def))}

    pipeline = MapperPipeline(
        job_name, # job_name: job name as string.
        func, # mapper_spec: specification of mapper to use.
        input_reader_spec="djangae.contrib.mappers.readers.DjangoInputReader", # input_reader_spec: specification of input reader to read data from.
        params=params, # mapper_params: parameters to use for mapper phase.
        shards=3 # shards: number of shards to use as int.
    )
    pipeline.start()
