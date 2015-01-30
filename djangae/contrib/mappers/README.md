## Map Reduce

Djangae contains functionality to allow Google's mapreduce library to run over instances of Django models.

Instructions:

1. Add the mapreduce library to your project, e.g. `$ pip install GoogleAppEngineMapReduce` or from [https://github.com/GoogleCloudPlatform/appengine-mapreduce](https://github.com/GoogleCloudPlatform/appengine-mapreduce).
1. Ensure that you have included `djangae.urls` in your URL config.
1. Subclass `djangae.contrib.mappers.pipes.MapReduceTask`, and define your `map` method.
1. Your class can also override attributes such as `shard_count`, `job_name`, and `queue_name` (see the code for all options).
1. The model to map over can either be defined as a attribute on the class or can be passed in when you instantiate it.
1. In your code, call `YourMapreduceClass().start()` to trigger the mapping of the `map` method over all of the instances of your model.
1. You can optionally pass any additional args and/or kwargs to the `.start()` method, which will then be passed into to each call of the `.map()` method for you.

Note that currently only the 'map' stage is implemented.  There is currently no reduce stage, but you could contribute it :-).
