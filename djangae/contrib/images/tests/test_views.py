import io
import os

from django.core.files.base import File
from django.core.files.images import ImageFile
from django.test.client import RequestFactory
from djangae.contrib.images.models import ProcessedImage
from djangae.contrib.images.tests.helpers import get_test_image_file
from djangae.contrib.images.views import (
    _get_source_image,
    _get_transformation_string,
    _is_source_image,
    _parse_transformation_parameters,
    _process_image
)
from djangae.storage import (
    CloudStorage,
    _get_storage_client,
)
from djangae.test import TestCase
from PIL import Image

class ImageServingUnitTests(TestCase):
    def test_parse_transformation_parameters(self):
        # Test height transformation
        url = '/serve/image.jpg=h600'
        result = _parse_transformation_parameters(url)
        self.assertEqual([('h', ('600',))], result)

        # Test width transformation
        url = '/serve/image.jpg=w1080'
        result = _parse_transformation_parameters(url)
        self.assertEqual([('w', ('1080',))], result)

        # Test size transformation
        url = '/serve/image.jpg=s1200'
        result = _parse_transformation_parameters(url)
        self.assertEqual([('s', ('1200',))], result)

        # Multiple (even though mixing w, s and h doesn't make sense)
        url = '/serve/image.jpg=w1080-s1280-h600'
        result = _parse_transformation_parameters(url)
        self.assertEqual([
            ('w', ('1080',)),
            ('s', ('1280',)),
            ('h', ('600',)),
        ], result)

        # Ensure unknown params are ignored
        url = '/serve/image.jpg=p1222-w1080'
        result = _parse_transformation_parameters(url)
        self.assertEqual([('w', ('1080',))], result)

    def test_process_image_resize(self):
        directory = os.path.dirname(os.path.realpath(__file__))
        # Landscape image
        image_file = get_test_image_file('desert.jpg')

        transformations = [
            ('s', ('1000',)),
        ]
        result = _process_image(image_file, transformations)
        self.assertEqual((1000, 667), result.size)

        # Portrait image
        image_file = get_test_image_file('lake.jpg')
        transformations = [
            ('s', ('1000',)),
        ]
        result = _process_image(image_file, transformations)
        self.assertEqual((792, 1000), result.size)

    def test_process_image_resize_height(self):
        directory = os.path.dirname(os.path.realpath(__file__))
        image_file = get_test_image_file('desert.jpg')
        transformations = [
            ('h', ('300',)),
        ]
        result = _process_image(image_file, transformations)
        self.assertEqual((450, 300), result.size)

    def test_process_image_resize_width(self):
        directory = os.path.dirname(os.path.realpath(__file__))
        image_file = get_test_image_file('desert.jpg')
        transformations = [
            ('w', ('1080',)),
        ]
        result = _process_image(image_file, transformations)
        self.assertEqual((1080, 720), result.size)

    def test_is_source_image(self):
        url = '/serve/image.jpg'
        result = _is_source_image(url)
        self.assertTrue(result)

        url = '/serve/image.jpg=w1080'
        result = _is_source_image(url)
        self.assertFalse(result)

    def test_get_transformation_string(self):
        # Test single transformation
        url = '/serve/image.jpg=s1200'
        result = _get_transformation_string(url)
        expected = 's1200'
        self.assertEqual(result, expected)

        # Multiple (even though mixing w, s and h doesn't make sense)
        url = '/serve/image.jpg=w1080-s1280-h600'
        result = _get_transformation_string(url)
        expected = 'w1080-s1280-h600'
        self.assertEqual(result, expected)

    def test_get_source_image(self):
        # Add test images to storage
        image = get_test_image_file('desert.jpg')

        storage = CloudStorage()
        f = ImageFile(image, name='desert.jpg')
        filename = storage.save('desert.jpg', f)

        url = 'desert.jpg'
        source_image = _get_source_image('test_bucket', url)
        self.assertEqual(source_image, f)

        url = 'image/path/with/many/dirs/desert.jpg=w100'
        source_image = _get_source_image('test_bucket', url)
        self.assertEqual(source_image, f)
        pass

    # def test_serve_image(self):
    #     # Ensure serves ProcessedImage
        # image = ProcessedImage.objects.create(url="…")

    # def tests_serve_or_process(self):
    #     rf = RequestFactory()
    #     request = rf.get('/serve/image.jpg=w1080')

# TODO: Add test for uploading image with same path/filename.


class ImageExistsServingViewTests(TestCase):
    def setUp(self):
        super(ImageExistsServingViewTests, self).setUp()

    def test_returns_original_image(self):
        pass

    def test_resizes_height(self):
        response = self.client.get()

    def test_resizes_width(self):
        pass

