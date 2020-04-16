import re

import PIL

def resize(image, width, height):
    # FIXME: Do stuff
    return image

def resize_height(image, height):
    # FIXME: Do stuff
    return image

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
