import re

import PIL

def resize(image, size):
    """
    resize image, maintaining aspect ratio, so that it's longest edge
    is `size` pixels.
    """
    orig_height = image.height
    orig_width = image.width
    aspect_ratio = orig_height / orig_width

    edge = 'width' if image.width >= image.height else 'height'
    if edge == 'width':
        new_width = int(size)
        new_height = int(round(new_width * aspect_ratio))
    else:
        new_height = int(size)
        new_width = int(round(new_height / aspect_ratio))

    resized = image.resize(size=(new_width, new_height), resample=PIL.Image.LANCZOS)
    return resized

def resize_height(image, height):
    height = int(height)
    orig_height = image.height
    orig_width = image.width
    aspect_ratio = orig_height / orig_width
    new_width = int(round(height / aspect_ratio))
    resized = image.resize(size=(new_width, height), resample=PIL.Image.LANCZOS)
    return resized

def resize_width(image, width):
    width = int(width)
    orig_height = image.height
    orig_width = image.width
    aspect_ratio = orig_height / orig_width
    new_height = int(round(width * aspect_ratio))
    resized = image.resize(size=(width, new_height), resample=PIL.Image.LANCZOS)
    return resized

# get_serving_url params https://stackoverflow.com/questions/25148567/list-of-all-the-app-engine-images-service-get-serving-url-uri-options
PROCESSOR_MATCHER = [
    (re.compile("h([0-9]+)"), "h"),
    (re.compile("s([0-9]+)"), "s"),
    (re.compile("w([0-9]+)"), "w"),
]

PROCESSOR_LOOKUP = {
    "h": resize_height,
    "s": resize,
    "w": resize_width,
}
