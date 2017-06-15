
from django.db.backends.base.introspection import (
    BaseDatabaseIntrospection, TableInfo
)


class DatabaseIntrospection(BaseDatabaseIntrospection):
    def get_table_list(self, cursor):
        sql = """
SELECT
  t.table_name
FROM
  information_schema.tables AS t
WHERE
  t.table_catalog = '' and t.table_schema = '';
""".strip()

        cursor.execute(sql)
        results = cursor.fetchall()
        return [TableInfo(row[0], 't') for row in results]

