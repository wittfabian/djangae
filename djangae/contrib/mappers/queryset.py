from django.db.models.loading import cache as model_cache


def make_immutable(spec_item):
    kwargs = {}
    args = []
    # could eliminate this cruft if not needing to support the old
    # non __getattr__ usage of QueryDef
    if len(spec_item) == 3:
        method, args, kwargs = spec_item
    elif len(spec_item) == 2:
        method, spec = spec_item
        if hasattr(spec, 'items'):
            kwargs = spec
        elif len(spec):
            args = spec

    return (method, tuple(args), frozenset(kwargs.iteritems()))


class QueryDef(object):
    """
    Django querysets are lazy, however they are designed to evaluate when you
    pickle them, so their internal cache of model instances gets populated.

    This will happen whenever you pass a queryset to a task queue, or save in
    memcache. Sometimes you want to a queryset to 'stay lazy' and not evaluate
    until you actually run the task for example.

    This class allows you to pass the 'definition' of a query into a task,
    from which you can construct a real queryset and evaluate it later.

    This class is hashable and will return a consistent hash value for
    equivalent querysets (i.e. querysets with exactly the same set of filters)
    so you can use it directly, for example as a key in a memoization dict.
    """

    def __init__(self, model_path, manager_name="objects", method_spec=None):
        """
        Arguments:
            model_path - string in "app.ModelClass" format
            manager_name - string name of manager attribute to use
            method_spec - <deprecated> list of ("method name", [args list] and/or {kwargs dict}) tuples,
                in the order you want them applied on the manager

        Usage:
            querydef = QueryDef('app.ModelClass').filter(name='bob')
            queryset = querydef()

            # deprecated old usage:
            querydef = QueryDef(
                'app.ModelClass',
                method_spec=[('filter', {'name':'bob'}),]
            )
            queryset = querydef.get_queryset()
        """
        self.model_path = model_path
        self.manager_name = manager_name

        # to support the old non __getattr__ usage of QueryDef... we only
        # create this method if method_spec is passed in, so that if you had a
        # manager method also called 'get_queryset' you could use the new
        # __getattr__ style without collisions
        if method_spec is not None:
            self.__use_get_queryset = True

        method_spec = method_spec or ()
        # store method_spec in immutable form (to get a consistent hash value)
        self.method_spec = tuple(map(make_immutable, method_spec))

    def __get_queryset(self):
        return self()

    def __str__(self):
        return "%s_%s_%s" % (self.model_path, self.manager_name, str(self.method_spec))

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            return super(QueryDef, self).__getattr__(key)
        if name == 'get_queryset' and self.__use_get_queryset:
            return self.__get_queryset
        def appended_method(*args, **kwargs):
            self.method_spec += (make_immutable((name, args, kwargs)),)
            return self
        return appended_method

    def __eq__(self, other):
        return self.__hash__() == hash(other)

    def __hash__(self):
        return hash((self.model_path, self.manager_name, self.method_spec))

    def __call__(self):
        try:
            model = model_cache.get_model(*self.model_path.split('.'))
        except Exception as e:
            import pdb; pdb.set_trace()
        qs = getattr(model, self.manager_name)
        for method, args, kwargs in self.method_spec:
            qs = getattr(qs, method)(*args, **dict(kwargs))
        return qs
