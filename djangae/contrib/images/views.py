import os
from django.core.exceptions import ImproperlyConfigured
from djangae.contrib.locking import Lock
from djangae.storage import CloudStorage
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseRedirect,
)

from PIL import Image

from .models import (
    get_url_parts,
    ProcessedImage
)
from .processors import PROCESSOR_MATCHER, PROCESSOR_LOOKUP
import logging


class UnsupportedTransformationError(Exception):
    def __init__(self, transform):
        self.transform = transform


def _get_transformation_string(url):
    return get_url_parts(1)


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


def _get_image(path):
    directory = os.path.dirname(os.path.realpath(__file__))
    image_path = os.path.join(directory, 'tests', path)
    # image = Image.open(image_path)
    pass


def _is_source_image(url):
    return _get_transformation_string(url) is None


def _serve_image(url):
    # Stick to Django File abstraction - don't use python filesystem
    # stuff directly

    image = ProcessedImage.objects.find(url)

    # FIXME: Probably use file serving magic from
    # djangae.storage
    return HttpResponse("Something")


# FIXME: Not correct
def _get_source_image(bucket, path):
    # FIXME: I can't think how to do this right now
    # again it should probably leverage djangae.storage
    # return pil.Image created from the data

    # Stick to Django File abstraction
    storage = CloudStorage()
    transformation_string = _get_transformation_string(path)

    if transformation_string is not None:
        source_file_path = path.split(transformation_string)
    else:
        source_file_path = path

    file = storage.open(source_file_path)
    return file


def _process_image(image_file, transformations):
    """
    :image_file: instance of ImageFile
    :transformations: iterable of commands
    """
    image = Image.open(image_file)
    image.show()

    for command in transformations:
        processor, args = command[0], command[1]

        try:
            func = PROCESSOR_LOOKUP[processor]
            image = func(image, *args)
        except KeyError:
            raise UnsupportedTransformationError(processor)

    return image

def _open_image(bucket, image_path):
    storage = CloudStorage(bucket_name=bucket)

    return storage._open(image_path)

def serve_or_process(request, image_path, bucket=None):
    if bucket is None:
        raise ImproperlyConfigured('You must provide a bucket name')

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

        image = _open_image(bucket, image_path)
        # TODO:  Hash source file and pass to ProcessedImage

        # No existing image for these transformation params, generate it
        source_image = _get_source_image(bucket, path)
        transformations = _parse_transformation_parameters(url)
        processed_image_data = _process_image(source_image_path, transformations)
        processed_image = ProcessedImage.objects.create(
            url=url,
            source_file_path='',
            source_file_hash='',
            data=processed_image_data
        )

    return _serve_image(processed_image.data)