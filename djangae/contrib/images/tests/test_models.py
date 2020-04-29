from djangae.contrib.images.models import (
    compute_image_hash,
    get_url_parts,
    ProcessedImage
)
from djangae.contrib.images.tests.helpers import get_test_image_file
from djangae.test import TestCase

class ProcessedImageModelUnitTests(TestCase):
    def test_creates_source_file_hash_on_save(self):
        pass

    def test_populates_source_file_path_on_save(self):
        img = ProcessedImage(path='/path/to/processed/image.jpg=s100')
        img.save()
        self.assertEqual(img.source_file_path, '/path/to/processed/image.jpg')


class GetUrlPartsUnitTests(TestCase):
    def test_no_transformation_params(self):
        url = '/path/to/image.jpg'
        result = get_url_parts(url)
        self.assertEqual(('/path/to/image.jpg', None), result)

    def test_returns_path_and_transformation_params(self):
        url = '/path/to/image.jpg=w100'
        result = get_url_parts(url)
        self.assertEqual(('/path/to/image.jpg', 'w100'), result)


class CalculateImageHashUnitTests(TestCase):
    def test_computes_hash_of_pixel_data(self):
        image_file = get_test_image_file('desert.jpg')
        h = compute_image_hash(image_file)
        self.assertEqual(b'\xe6\xaa3#\xd1\xff\xe6H\xb5,/\xcc:\x7f%\n\xedO\xf5o\x1e\x10\x9dp\nIP\xf6X\xdd?W', h)
