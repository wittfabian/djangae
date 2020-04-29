from djangae.contrib.images.models import (
    get_url_parts,
    ProcessedImage
)
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
