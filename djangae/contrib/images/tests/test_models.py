from djangae.contrib.images.models import (
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

