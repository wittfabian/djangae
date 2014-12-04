from django.db import models

class BlobField(models.Field):
    def db_type(self, connection):
        return 'bytes'

    def get_default(self):
        if self.has_default():
            return super(BlobField, self).get_default()
        return ''
