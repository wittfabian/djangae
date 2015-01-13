from django.conf.urls import patterns, include, url
from django.http import HttpResponse


import pipeline
from mapreduce import handlers, status, main

def djangae_webapp(request_hander):
    """ Decorator for wrapping a webapp2.RequestHandler to work with
    the django wsgi hander"""

    def request_hander_wrapper(request, *args, **kwargs):
        from webapp2 import Request, Response, WSGIApplication

        class Route:
            handler_method = request.method.lower()

        req = Request(request.environ)
        req.route = Route()
        req.route_args = args
        req.route_kwargs = kwargs
        req.app = WSGIApplication()
        response = Response()
        view_func = request_hander(req, response)

        try:
            view_func.dispatch()
        except Exception as e:
            raise e

        django_response = HttpResponse(response.body, status=response.status)
        for header, value in response.headers.iteritems():
            django_response[header] = value

        return django_response

    return request_hander_wrapper

from mapreduce.main import create_handlers_map

# This should work but does not
# wrapped_urls = [url(url_re, djangae_webapp(func)) for url_re, func in create_handlers_map()]


urlpatterns = patterns('',
    url(r'^pipeline/output', djangae_webapp(pipeline.pipeline._BarrierHandler)),
    url(r'^pipeline/run', djangae_webapp(pipeline.pipeline._PipelineHandler)),
    url(r'^pipeline/finalized', djangae_webapp(pipeline.pipeline._PipelineHandler)),
    url(r'^pipeline/cleanup', djangae_webapp(pipeline.pipeline._CleanupHandler)),
    url(r'^pipeline/abort', djangae_webapp(pipeline.pipeline._PipelineHandler)),
    url(r'^pipeline/fanout', djangae_webapp(pipeline.pipeline._FanoutHandler)),
    url(r'^pipeline/fanout_abort', djangae_webapp(pipeline.pipeline._FanoutAbortHandler)),
    url(r'^pipeline/callback', djangae_webapp(pipeline.pipeline._CallbackHandler)),
    url(r'^pipeline/rpc/tree', djangae_webapp(pipeline.status_ui._TreeStatusHandler)),
    url(r'^pipeline/rpc/class_paths', djangae_webapp(pipeline.status_ui._ClassPathListHandler)),
    url(r'^pipeline/rpc/list', djangae_webapp(pipeline.status_ui._RootListHandler)),
    url(r'^pipeline/(.*)', djangae_webapp(pipeline.status_ui._StatusUiHandler)),
    url(r'^worker_callback/*', djangae_webapp(handlers.MapperWorkerCallbackHandler)),
    url(r'^controller_callback/*', djangae_webapp(handlers.ControllerCallbackHandler)),
    url(r'^kickoffjob_callback/*', djangae_webapp(handlers.KickOffJobHandler)),
    url(r'^finalizejob_callback/*', djangae_webapp(handlers.FinalizeJobHandler)),
    url(r'^command/start_job', djangae_webapp(handlers.StartJobHandler)),
    url(r'^command/cleanup_job', djangae_webapp(handlers.CleanUpJobHandler)),
    url(r'^command/abort_job', djangae_webapp(handlers.AbortJobHandler)),
    url(r'^command/list_configs', djangae_webapp(status.ListConfigsHandler)),
    url(r'^command/list_jobs', djangae_webapp(status.ListJobsHandler)),
    url(r'^command/get_job_detail', djangae_webapp(status.GetJobDetailHandler)),
    url(r'^([^/]*\\.(?:css|js)|status|detail)$', djangae_webapp(status.ResourceHandler)),
    url(r'^$', djangae_webapp(main.RedirectHandler)),
)
