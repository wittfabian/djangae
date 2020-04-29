from django.db import models


class ProcessedImage(models.Model):
    # The normalized URL sans-host for this processed image (including QS)
    # Not using URLField because it won't be a full URL
    path = models.CharField(primary_key=True)

    # The file path to the original image, not a FileField because this will be stored
    # on multiple ProcessedImages - ProcessImage doesn't own the source_file
    # This is the filepath relative to the cloud storage bucket
    source_file_path = models.CharField(max_length=500)

    # A hash of the original data, so that we can determine if the
    # source file changed and this image needs regenerating if necessary
    source_file_hash = models.CharField(max_length=64)

    # Keep track of when we created this image
    created = models.DateTimeField(auto_now_add=True)

    # This is the serving url of this processed image
    serving_url = models.URLField()

    # The data of this processed image
    data = models.ImageField()

    class Meta:
        app_label = "djangae"

    @staticmethod
    def normalise_url(url):
        # FIXME: Implement to make sure querystring parameters are in some
        # kind of consistent order
        return url

    def save(self, *args, **kwargs):
        self.path = self.normalise_url(self.path)
        # TODO: Populate source_file_path?
        super().save(*args, **kwargs)
