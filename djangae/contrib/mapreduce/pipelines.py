import mapreduce
mapreduce.parameters.config.BASE_PATH = '/_ah/mapreduce'
mapreduce.parameters._DEFAULT_PIPELINE_BASE_PATH = "/_ah/mapreduce/pipeline"


from mapreduce import mapper_pipeline
from mapreduce import pipeline_base
from mapreduce import shuffler
from mapreduce.mapreduce_pipeline import _ReturnPipeline
from mapreduce.mapper_pipeline import MapperPipeline as _MapPipeline
import pipeline

MapperPipeline = mapper_pipeline.MapperPipeline
CleanupPipeline = shuffler._GCSCleanupPipeline


class MapPipeline(pipeline_base.PipelineBase):

    output_names = mapper_pipeline.MapperPipeline.output_names

    def run(self, job_name, mapper_spec, input_reader_spec, mapper_params=None, shards=None):
        map_pipeline = yield _MapPipeline(job_name, mapper_spec, input_reader_spec, params=mapper_params, shards=shards)
        with pipeline.After(map_pipeline):
            all_temp_files = yield pipeline.common.Extend(map_pipeline)
            yield CleanupPipeline(all_temp_files)
        yield _ReturnPipeline(map_pipeline.result_status,
                              map_pipeline.result_status,
                              map_pipeline.counters,
                              map_pipeline.job_id,
                              map_pipeline)
