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

In `djange.contrib.mapreduce.input_reader` there is a `DjangoInputReader` which can be used to read Django Querysets into a MapReduce task,
it uses a basic clustering algorithm similar to the `DatastoreInputReader` bundled with the MapReduce library.
