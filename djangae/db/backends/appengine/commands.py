from google.appengine.api import datastore
from django.core.cache import cache

from django.db.models.sql.where import AND, OR

class SelectCommand(object):
    def __init__(self, connection, model, queried_fields, where, is_count=False):
        self.connection = connection
        self.pk_col = model._meta.pk.column
        self.model = model
        self.queried_fields = queried_fields
        self.is_count = is_count

        self.included_pks = []
        self.excluded_pks = []

        if not self.queried_fields:
            self.queried_fields = [ x.column for x in model._meta.fields ]

        projection_fields = []
        for field in self.queried_fields:
            if field == self.pk_col:
                continue

            #Text and byte fields aren't indexed, so we can't do a 
            #projection query
            db_type = model._meta.get_field(field).db_type(connection)
            if db_type in ("bytes", "text"):                        
                projection_fields = []
                break

            projection_fields.append(field)

        self.projection = list(set(projection_fields)) or None     
        if model._meta.parents:
            self.projection = None
            
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
           
    def parse_where_and_check_projection(self, where, negated=False):
        result = []

        if where.negated:
            negated = not negated

        if not negated and where.connector != AND:
            raise DatabaseError("Only AND filters are supported")

        for child in where.children:
            if isinstance(child, tuple):
                constraint, op, annotation, value = child

                #Disable projection if it's not supported
                if self.projection and constraint.col in self.projection:
                    if op in ("exact", "in"):
                        #If we are projecting, but we are doing an 
                        #equality filter on one of the columns, then we 
                        #can't project
                        self.projection = None

                if negated:
                    if op in ("exact", "in") and constraint.field.primary_key:
                        self.excluded_pks.append(value)
                    #else: FIXME when excluded_pks is handled, we can put the
                    #next section in an else block
                    if op == "exact":
                        col = constraint.col
                        result.append((col, "gt_and_lt", value))
                    else:
                        raise RuntimeError("Unsupported negated lookup: " + op)
                else:
                    if op in ("exact", "in") and constraint.field.primary_key:
                        if isinstance(value, (list, tuple)):
                            self.included_pks.extend(list(value))
                        else:
                            self.included_pks.append(value)
                    #else: FIXME when included_pks is handled, we can put the
                    #next section in an else block
                    col = constraint.col
                    result.append((col, op, value))
            else:
                result.extend(self.parse_where_and_check_projection(child, negated))
        return result

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
        self.entities = entities
        self.model = model
