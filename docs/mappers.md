## Map Reduce

Djangae contains functionality to allow Google's mapreduce library to run over instances of Django models.

Instructions:

1. Add the mapreduce library to your project, e.g. `$ pip install GoogleAppEngineMapReduce` or from [https://github.com/GoogleCloudPlatform/appengine-mapreduce](https://github.com/GoogleCloudPlatform/appengine-mapreduce).
1. Ensure that you have included `djangae.urls` in your URL config.
1. Add `'djangae.contrib.processing.mapreduce'` to `INSTALLED_APPS` in your Django settings.
1. Subclass `djangae.contrib.mappers.pipes.MapReduceTask`, and define your `map` method.
1. Your class can also override attributes such as `shard_count`, `job_name`, and `queue_name` (see the code for all options).
1. The model to map over can either be defined as a attribute on the class or can be passed in when you instantiate it.
1. In your code, call `YourMapreduceClass().start()` to trigger the mapping of the `map` method over all of the instances of your model. Optionally you can use the `queue_name` keyword argument to specify a task queue that will be used (don't forget to [define the queue in queue.yaml](https://cloud.google.com/appengine/docs/python/config/queue)).
1. You can optionally pass any additional args and/or kwargs to the `.start()` method, which will then be passed to each call of the `.map()` method for you.

Note that currently only the 'map' stage is implemented.  There is currently no reduce stage, but you could contribute it :-).

## Helpful functions

### djangae.contrib.mappers.defer_iteration

This function takes a `queryset` and a `callback`, and also optionally a `shard_size` and a `_queue`. It
defers background tasks to iterate over the entire queryset on the specified task queue calling your
callback function on each Django model instance in the queryset.

* The shard size is the number of instance which it will attempt to process in a single task, and defaults to 500.
    * Depending on how long your callback function is likely to take on each instance, you should reduce the shard size in order that it can safely process that many instances in App Engine's task time limit of 10 minutes.
* There is no exception handling around the callback function, so an exception is raised when processing one of the instances then that task will fail and be retried, thus re-processing any prior instances in that same shard.
    * Your callback function should be idempotent.
