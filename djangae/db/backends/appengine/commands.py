
class SelectCommand(object):
    def __init__(self, connection, model, queried_fields, where):
        self.connection = connection
        self.pk_col = model._meta.pk.column
        self.model = model
        self.queried_fields = queried_fields

        if not self.queried_fields:
            self.queried_fields = [ x.column for x in model._meta.fields ]

        projection_fields = [ x for x in self.queried_fields if x != self.pk_col ]
        self.projected_fields = set(projection_fields)
        self.projection = projection_fields or None     
        self.keys_only = False
        self.where = self.parse_where_and_check_projection(where)

        try:
            #If the PK was queried, we switch it in our queried
            #fields store with __key__
            pk_index = self.queried_fields.index(self.pk_col)
            self.queried_fields[pk_index] = "__key__"
            self.keys_only = len(self.queried_fields) == 1
        except ValueError:
            pass
           
    def parse_where_and_check_projection(self, where):
        result = []

        for child in where.children:
            if isinstance(child, tuple):
                constraint, op, annotation, value = child

                #Disable projection if it's not supported
                if constraint.col in self.projected_fields:
                    if op in ("exact", "in"):
                        self.projection = None

                    db_type = constraint.field.db_type(self.connection)
                    if db_type in ("bytes", "text"):
                        self.projection = None

                return (constraint.col, op, value)
            else:
                result.append(self.parse_where_and_check_projection(child))
        return result

    def is_supported(self):
        if model._meta.get_parent_list() and not model._meta.abstract:                    
            return (False, "Multi-table inheritance is not supported")

        return (True, "")

class FlushCommand(object):
    """
        sql_flush returns the SQL statements to flush the database,
        which are then executed by cursor.execute()

        We instead return a list of FlushCommands which are called by
        our cursor.execute
    """
    def __init__(self, table):
        self.table = table

    def execute(self):
        table = self.table

        all_the_things = list(datastore.Query(table, keys_only=True).Run())
        while all_the_things:
            datastore.Delete(all_the_things)
            all_the_things = list(datastore.Query(table, keys_only=True).Run())

        cache.clear()

class InsertCommand(object):
    def __init__(self, model, entities):
        if model._meta.get_parent_list() and not model._meta.abstract:
            raise RuntimeError("Multi-table inheritance is not supported")

        self.entities = entities
        self.model = model
