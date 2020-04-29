import io
import os
from django.core.files.images import ImageFile

def get_test_image_file(filename):
    directory = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(directory, filename)

    # open file in binary mode
    file = io.open(path, 'rb')
    image_file = ImageFile(file)
    return image_file
