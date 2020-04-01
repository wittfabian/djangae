from djangae.contrib.locking import Lock
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseRedirect,
)

from .models import ProcessedImage
from .processors import PROCESSOR_LOOKUP


def _parse_querystring_parameters(url):
    # FIXME: Return a list of tuples of the querystring
    # commands and any arguments
    return []


def _is_source_image(url):
    # FIXME: Probably just check if there's a querystring?
    return False


def _serve_image(url):
    # FIXME: Probably use file serving magic from
    # djangae.storage
    return HttpResponse("Something")


def _get_source_image(url):
    # FIXME: I can't think how to do this right now
    # again it should probably leverage djangae.storage
    # return pil.Image created from the data
    pass


def serve_or_process(request):
    url = request.get_full_path()

    if _is_source_image(url):
        return _serve_image(url)

    url = ProcessedImage.normalise_url(url)

    existing_image = ProcessedImage.objects.filter(pk=url).first()
    if existing_image:
        return HttpResponseRedirect(existing_image.serving_url)

    # OK, we've never dealt with this URL before, let's do this!

    # We acquire a lock to prevent multiple requests to the same URL
    # all generating the image at the same time
    with Lock.acquire(url, wait=True):
        existing_image = ProcessedImage.objects.filter(pk=url).first()
        if existing_image:
            # OK, another thread processed this image while we were waiting
            # so just return
            return HttpResponseRedirect(existing_image.serving_url)

        image = _get_source_image(url)

        # Run processing
        for command in _parse_querystring_parameters(url):
            processor, args = command[0], command[1:]

            try:
                func = PROCESSOR_LOOKUP[processor]
                func(image, *args)
            except KeyError:
                raise Http404()  # Not a supported thing

        processed_image = ProcessedImage.objects.create(...)

    return _serve_image(processed_image.data)
