# Pipelines and MapReduce

Djangae now contains functionality to run Google's native Pipelines and MapReduce

## Pipelines

1. Add the pipelines library to your project, e.g. `$ pip install GoogleAppEnginePipeline` or from
[https://github.com/GoogleCloudPlatform/appengine-pipelines](https://github.com/GoogleCloudPlatform/appengine-pipelines)
2. Ensure that you have included `djangae.urls` in your URL config.

This will give access to all the appengine-pipelines functionality

[https://github.com/GoogleCloudPlatform/appengine-pipelines/wiki](https://github.com/GoogleCloudPlatform/appengine-pipelines/wiki)


## MapReduce

1. Add the MapReduce library to your project, e.g. `$ pip install GoogleAppEngineMapReduce` or from
[https://github.com/GoogleCloudPlatform/appengine-mapreduce](https://github.com/GoogleCloudPlatform/appengine-mapreduce).
1. Add this handler to your applications root urls

```
url(r'^mapreduce/', include(djangae.contrib.mapreduce.urls))
```

Now you can create native MapReduce tasks from inside your Django application, the requests will be handled and forwarded to correct handlers

- Unfortunately overriding the `mapreduce` url is not available yet, but should become available eventually.

Documentation for the MapReduce api functionality
[https://github.com/GoogleCloudPlatform/appengine-mapreduce/wiki](https://github.com/GoogleCloudPlatform/appengine-mapreduce/wiki)

## DjangoInputReader

In `djange.contrib.mapreduce.input_reader` there is a `DjangoInputReader` which can be used to read Django Querysets into a MapReduce task,
it uses a basic clustering algorithm similar to the `DatastoreInputReader` bundled with the MapReduce library.
