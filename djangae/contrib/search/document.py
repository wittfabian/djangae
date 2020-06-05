

# Puncuation list is taken from the list the App Engine search
# API used: https://cloud.google.com/appengine/docs/standard/python/search

PUNCTUATION = {
    "!", '"', "%", "(", ")", "*", ",", "-", "|", "/",
    "[", "]", "^", "`", ":", "=", ">", "?", "@", "{",
    "}", "~", "$"
}


class Field(object):
    def __init__(self, default=None, null=True):
        self.default = default
        self.null = null

    def normalize_value(self, value):
        from nltk.corpus import stopwords  # Inline import so not a hard requirement

        stop_words = stopwords('english')  # FIXME: Multiple languages

        # Default behaviour is to lower-case, remove punctuation
        # and then remove stop words

        if value is None:
            return None

        value = value.lower()

        to_remove = set(stop_words).union(PUNCTUATION)

        tokens = value.split()  # Split on whitespace
        tokens = [x for x in tokens if x not in to_remove]
        return " ".join(tokens)

    def tokenize_value(self, value):
        """
            Given a value set on a document, this
            returns a list of tokens that are indexed
        """
        raise NotImplementedError()


class AtomField(Field):
    pass


class TextField(Field):
    pass


class DateTimeField(Field):
    pass


class NumberField(Field):
    pass


class Document(object):
    def __init__(self, **kwargs):
        self._data = None

        self._fields = {}

        klass = type(self)

        for attr_name in dir(klass):
            attr = getattr(klass, attr_name)

            if isinstance(attr, Field):
                attr.attname = attr_name
                self._fields[attr_name] = attr

                # Apply any field values passed into the init
                if attr in kwargs:
                    setattr(self, attr, kwargs[attr])

    @property
    def id(self):
        return self._data.pk if self._data else None

    def _set_data(self, data):
        self._data = data

    def get_fields(self):
        return self._fields
