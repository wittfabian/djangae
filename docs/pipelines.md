# Pipelines and MapReduce

Djangae now contains functionality to run Google's native Pipelines and MapReduce

## MapReduce

1. Add the MapReduce library to your project, e.g. `$ pip install GoogleAppEngineMapReduce` or from
[https://github.com/GoogleCloudPlatform/appengine-mapreduce](https://github.com/GoogleCloudPlatform/appengine-mapreduce).
2. Add `djangae.contrib.processing.mapreduce` to INSTALLED_APPS
3. Add the following rule to the top of your url patterns:

```
    url(r'^_ah/mapreduce/', include(djangae.contrib.processing.mapreduce.urls)),
```

Now you can create native MapReduce tasks from inside your Django application, the requests will be handled and forwarded to correct handlers

Documentation for the MapReduce api functionality
[https://github.com/GoogleCloudPlatform/appengine-mapreduce/wiki](https://github.com/GoogleCloudPlatform/appengine-mapreduce/wiki)

## DjangoInputReader

In `djange.contrib.processing.mapreduce.input_readers` there is a `DjangoInputReader` which can be used to read Django Querysets into a MapReduce task,
it uses a basic clustering algorithm similar to the `DatastoreInputReader` bundled with the MapReduce library.

## Helper functions

`djangae.contrib.processing.mapreduce.helpers` includes a number of functions for running and checking the status of
map and mapreduce jobs. These functions are:

 - `map_queryset(qs, func, finalize_func=None)`: Call `func` on all instances in a queryset
 - `map_entities(kind, namespace, func, finalize_func=None)`: Call `func` entities in a kind + namespace
 - `map_files(bucket, func, finalize_func=None, filenames=None)`: Call `func` on all files in a CloudStorage bucket
 - `map_reduce_queryset(queryset, map_func, reduce_func, output_writer)`
 - `map_reduce_entities(kind, namespace, map_func, reduce_func, output_writer)`

Each of these functions allows the following optional kwargs:

 - `_shards`
 - `_output_writer` (except `map_reduce_X` functions where it's a positional arg)
 - `_output_writer_kwargs`
 - `_job_name`
 - `_queue_name`

Each of the map functions returns a pipeline. The following functions can be used to check the status of running pipelines:

 - `pipeline_has_finished(pipeline_id)`: Returns True if the pipeline has finished
 - `pipeline_in_progress(pipeline_id)`: Returns True if the pipeline is running
 - `get_pipeline_by_id(pipeline_id)`: Returns a pipeline given an ID
 - `get_mapreduce_state(pipeline)`: Returns the MapreduceState object for the pipeline
