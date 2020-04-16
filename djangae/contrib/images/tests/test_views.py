import os

from django.test.client import RequestFactory
from djangae.test import TestCase
from djangae.contrib.images.views import _parse_transformation_parameters, _process_image

class ImageServingViewTests(TestCase):
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
        image_path = os.path.join(directory, 'desert.jpg')
        transformations = [
            ('s', ('1000',)),
        ]
        result = _process_image(image_path, transformations)
        result.show()
        self.assertEqual((1000, 667), result.size)

        # Portrait image
        image_path = os.path.join(directory, 'lake.jpg')
        transformations = [
            ('s', ('1000',)),
        ]
        result = _process_image(image_path, transformations)
        self.assertEqual((792, 1000), result.size)

    def test_process_image_resize_height(self):
        directory = os.path.dirname(os.path.realpath(__file__))
        image_path = os.path.join(directory, 'desert.jpg')
        transformations = [
            ('h', ('300',)),
        ]
        result = _process_image(image_path, transformations)
        self.assertEqual((450, 300), result.size)


    def test_process_image_resize_width(self):
        directory = os.path.dirname(os.path.realpath(__file__))
        image_path = os.path.join(directory, 'desert.jpg')
        transformations = [
            ('w', ('1080',)),
        ]
        result = _process_image(image_path, transformations)
        self.assertEqual((1080, 720), result.size)


    # def tests_serve_or_process(self):
    #     rf = RequestFactory()
    #     request = rf.get('/serve/image.jpg=w1080')
