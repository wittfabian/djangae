from djangae.contrib.locking import Lock
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseRedirect,
)

from PIL import Image

from .models import ProcessedImage
from .processors import PROCESSOR_MATCHER, PROCESSOR_LOOKUP
import logging


class UnsupportedTransformationError(Exception):
    def __init__(self, transform):
        self.transform = transform


def _get_transformation_string(url):
    # FIXME: Querystring should not be returned as part of transformation string

    # FIXME: This will need changing when we introduce support for params
    # which allow values (and thus need an `=` character)

    # Get overall string representing transformations to apply
    # e.g. https://www.example.com/serve/image.jpg=w1080-cc-fh-l78 => w1080-cc-fh-l78
    parts = url.rpartition('=')
    if parts[1] != '':
        return parts[2]

    return None


def _parse_transformation_parameters(url):
    """
    Work out which transformations have been requested. Syntax for specifying
    transformations is the same as how get_serving_url worked in the Python 2
    standard environment on App Engine.

    Example: https://www.example.com/serve/image.jpg=w1080 requests image.jpg
    rescaled to 1080px width.
    """
    transforms_string = _get_transformation_string(url)

    # Get list of individual transformations
    # e.g. w1080-cc-fh-l78 => [w1080,cc,fh,l78]
    transforms = transforms_string.split('-')

    # Build into a list of tuples with transformation type and params
    transforms_list = []

    for t in transforms:
        valid = False

        for pattern, name in PROCESSOR_MATCHER:
            match = pattern.fullmatch(t)
            if match:
                valid = True
                transforms_list.append((name, match.groups()))

        if not valid:
            # Not a transform we support, ignore it.
            logging.warning(f'Ignoring unrecognised transform: "{t}"')

    return transforms_list


def _is_source_image(url):
    return _get_transformation_string(url) is None


def _serve_image(url):
    # FIXME: Probably use file serving magic from
    # djangae.storage
    return HttpResponse("Something")


def _get_source_image(url):
    # FIXME: I can't think how to do this right now
    # again it should probably leverage djangae.storage
    # return pil.Image created from the data
    pass


def _process_image(image_path, transformations):
    image = Image.open(image_path)
    # image.show()

    for command in transformations:
        processor, args = command[0], command[1]

        try:
            func = PROCESSOR_LOOKUP[processor]
            image = func(image, *args)
        except KeyError:
            raise UnsupportedTransformationError(processor)

    return image

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
        for command in _parse_transformation_parameters(url):
            processor, args = command[0], command[1:]

            try:
                func = PROCESSOR_LOOKUP[processor]
                func(image, *args)
            except KeyError:
                raise Http404()  # Not a supported thing

        processed_image = ProcessedImage.objects.create(...)

    return _serve_image(processed_image.data)
