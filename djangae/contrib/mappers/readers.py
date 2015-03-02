from mapreduce import input_readers
import itertools
import logging
from django.db.models.loading import cache as model_cache
from djangae import utils
from google.appengine.ext import blobstore


class DjangoInputReader(input_readers.InputReader):

    REQUIRED_PARAMS = ('model',)

    def __init__(self, start_id, end_id, model, *args, **kwargs):
        self.shard_id = 1
        self.start_id = start_id
        self.end_id = end_id
        self.raw_model = model
        app, model = self.raw_model.split('.')
        self.model = model_cache.get_model(app, model)
        super(DjangoInputReader, self).__init__(*args, **kwargs)


    def __iter__(self):
        if self.start_id > self.end_id:
            # This can happen if we are the last shard and
            # the shard size caused each previous shard to process an additional model
            return

        query = self.model.objects

        if self.start_id:
            query = query.filter(pk__gt=self.start_id).filter(pk__lte=self.end_id)
        query = query.order_by('pk')

        for model in utils.get_in_batches(query, batch_size=500):
            # From the mapreduce docs (AbstractDatastoreInputReader):
            #     The caller must consume yielded values so advancing the KeyRange
            #     before yielding is safe.
            self.start_id = model.id
            yield model


    @classmethod
    def validate(cls, mapper_spec):
        if mapper_spec.input_reader_class() != cls:
            raise input_readers.BadReaderParamsError("Input reader class mismatch")
        params = input_readers._get_params(mapper_spec)
        for param in cls.REQUIRED_PARAMS:
            if not param in params:
                raise input_readers.BadReaderParamsError("Parameter missing: %s" % param)


    @classmethod
    def split_input(cls, mapper_spec):
        shard_count = mapper_spec.shard_count

        # Grab the input parameters for the split
        params = input_readers._get_params(mapper_spec)
        logging.info("Params: %s" % params)
        # Unpickle the query
        app, model = params['model'].split('.')
        model = model_cache.get_model(app, model)

        # Grab the lowest pk
        query = model.objects.all()
        query = query.order_by('pk')

        try:
            first_id = query.values_list('pk', flat=True)[:1][0]

            query = query.order_by('-pk')
            last_id = query.values_list('pk', flat=True)[:1][0]
        except IndexError:
            return [DjangoInputReader(0,0, params['model'])]

        pk_range = last_id - first_id

        logging.info("Query range: %s - %s = %s" % (first_id, last_id, pk_range))

        if pk_range < shard_count or shard_count == 1:
            return [DjangoInputReader(first_id-1, last_id, params['model'])]

        readers = []
        max_shard_size = int(float(pk_range) / float(shard_count))
        if pk_range % shard_count:
            max_shard_size += 1

        shard_id = 1
        # Splitting could be much smarter by taking a __scatter__ sample and
        # clustering, which is how the DatastoreInputWriter from the mapreduce
        # splits on pks
        for i in itertools.count(first_id-1, max_shard_size):
            if i >= last_id:
                break

            shard_start_id = i
            shard_end_id = i + max_shard_size
            if shard_end_id > last_id:
                shard_end_id = last_id

            logging.info("Creating shard: %s - %s" % (shard_start_id, shard_end_id))
            reader = DjangoInputReader(shard_start_id, shard_end_id, params['model'])
            reader.shard_id = shard_id
            readers.append(reader)
            shard_id += 1
        return readers


    @classmethod
    def from_json(cls, input_shard_state):
        start_id = input_shard_state['start']
        end_id = input_shard_state['end']
        shard_id = input_shard_state['shard_id']
        model = input_shard_state['model']

        reader = DjangoInputReader(start_id, end_id, model)
        reader.shard_id = shard_id
        return reader


    def to_json(self):
        return {
            'start': self.start_id,
            'end': self.end_id,
            'shard_id': self.shard_id,
            'model': self.raw_model
        }


class DjangoQuerySpec(object):
  """Encapsulates everything about a query needed by DatastoreInputReader."""

  DEFAULT_BATCH_SIZE = 50

  def __init__(self,
               entity_kind,
               keys_only=None,
               filters=None,
               batch_size=None,
               model_class_path=None,
               app=None,
               ns=None):
    self.entity_kind = entity_kind
    self.keys_only = keys_only or False
    self.filters = filters or None
    self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE
    self.model_class_path = model_class_path
    self.app = app
    self.ns = ns

  def to_json(self):
    return {"entity_kind": self.entity_kind,
            "keys_only": self.keys_only,
            "filters": self.filters,
            "batch_size": self.batch_size,
            "model_class_path": self.model_class_path,
            "app": self.app,
            "ns": self.ns}

  @classmethod
  def from_json(cls, json):
    return cls(json["entity_kind"],
               json["keys_only"],
               json["filters"],
               json["batch_size"],
               json["model_class_path"],
               json["app"],
               json["ns"])


class BlobstoreUniversalLineInputReader(input_readers.BlobstoreLineInputReader):
    """A version of the BlobstoreLineInputReader that works with Mac, Windows and Linux line endings"""

    def next(self):
        """Returns the next input from as an (offset, line) tuple."""
        self._has_iterated = True

        if self._read_before_start:
            self._read_line()
            self._read_before_start = False
        start_position = self._blob_reader.tell()

        if start_position > self._end_position:
            raise StopIteration()

        line = self._read_line()

        if not line:
            raise StopIteration()

        return start_position, line.rstrip("\n")

    def _read_line(self):
        buf = []  # A buffer to store our line
        #Read characters until we find a \r or \n
        c = self._blob_reader.read(size=1)
        while c != '\n' and c != '\r':
            if not c:
                break

            buf.append(c)
            c = self._blob_reader.read(size=1)

        # If we found a \r, it could be "\r\n" so read the next char
        if c == '\r':
            n = self._blob_reader.read(size=1)

            #If the \r wasn't followed by a \n, then it was a mac line ending
            #so we seek backwards 1
            if n and n != '\n':
                #We only check n != '\n' if we weren't EOF (e.g. n evaluates to False) otherwise
                #we'd read nothing, and then seek back 1 which would then be re-read next loop etc.
                self._blob_reader.seek(-1, 1)  # The second 1 means to seek relative to the current position

        if buf:
            buf.append("\n")  # Add our trailing \n, no matter what the line endings were

            #Return the line, that ends with a \n
            return "".join(buf)

    @classmethod
    def from_json(cls, json):
        """Instantiates an instance of this InputReader for the given shard spec."""
        return cls(json[cls.BLOB_KEY_PARAM],
                   json[cls.INITIAL_POSITION_PARAM],
                   json[cls.END_POSITION_PARAM])

    @classmethod
    def split_input(cls, mapper_spec):
        """Returns a list of shard_count input_spec_shards for input_spec.

        Args:
          mapper_spec: The mapper specification to split from. Must contain
              'blob_keys' parameter with one or more blob keys.

        Returns:
          A list of BlobstoreInputReaders corresponding to the specified shards.
        """
        params = input_readers._get_params(mapper_spec)
        blob_keys = params[cls.BLOB_KEYS_PARAM]
        if isinstance(blob_keys, basestring):
            blob_keys = blob_keys.split(",")

        blob_sizes = {}
        for blob_key in blob_keys:
            blob_info = blobstore.BlobInfo.get(blobstore.BlobKey(blob_key))
            blob_sizes[blob_key] = blob_info.size

        shard_count = min(cls._MAX_SHARD_COUNT, mapper_spec.shard_count)
        shards_per_blob = shard_count // len(blob_keys)
        if shards_per_blob == 0:
            shards_per_blob = 1

        chunks = []
        for blob_key, blob_size in blob_sizes.items():
            blob_chunk_size = blob_size // shards_per_blob

            for i in xrange(shards_per_blob - 1):
                chunks.append(BlobstoreUniversalLineInputReader.from_json({
                    cls.BLOB_KEY_PARAM: blob_key,
                    cls.INITIAL_POSITION_PARAM: blob_chunk_size * i,
                    cls.END_POSITION_PARAM: blob_chunk_size * (i + 1)
                }))
            chunks.append(BlobstoreUniversalLineInputReader.from_json({
                cls.BLOB_KEY_PARAM: blob_key,
                cls.INITIAL_POSITION_PARAM: blob_chunk_size * (shards_per_blob - 1),
                cls.END_POSITION_PARAM: blob_size
            }))
        return chunks
