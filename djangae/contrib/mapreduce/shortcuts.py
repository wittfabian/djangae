from mapreduce.mapreduce_pipeline import MapreducePipeline
import csv
from mapreduce import context
import StringIO


def django_csv_reduce_pipeline(model, fields=[], shards=10):
    pipe = MapreducePipeline(
        "word_count",
        "djangae.contrib.mapreduce.shortcuts.instance_to_csv_map",
        "djangae.contrib.mapreduce.shortcuts.instance_to_csv_reduce",
        "djangae.contrib.mapreduce.input_readers.DjangoInputReader",
        "mapreduce.output_writers.GoogleCloudStorageOutputWriter",
        mapper_params={'input_reader': {'model': model}, 'fields': fields},
        reducer_params={"mime_type": "text/plain", 'output_writer': {'bucket_name': 'test'}},
        shards=10
    )
    return pipe


def instance_to_csv_map(instance, *args, **kwargs):
    """
        Converts a single instance to a CSV line
    """
    ctx = context.get()
    fields = ctx.mapreduce_spec.mapper.params['fields']
    data = [getattr(instance, field, None) for field in fields]
    si = StringIO.StringIO()
    cw = csv.writer(si)
    cw.writerow(data)
    line = si.getvalue()
    yield (0, line)


def instance_to_csv_reduce(key, values):
    """
        Converts a single instance to a CSV line
    """
    import ipdb; ipdb.set_trace()
    yield ''.join(values)
