from django.db.models.expressions import Star
from django.db.models.sql.datastructures import EmptyResultSet

from .version_19 import Parser as BaseParser


class Parser(BaseParser):
    def _prepare_for_transformation(self):
        from django.db.models.sql.where import EmptyWhere
        if isinstance(self.django_query.where, EmptyWhere):
            # Empty where means return nothing!
            raise EmptyResultSet()

    def _determine_query_kind(self):
        query = self.django_query
        if query.annotations:
            if "__count" in query.annotations:
                field = query.annotations["__count"].input_field
                if isinstance(field, Star) or field.value == "*":
                    return "COUNT"

        return "SELECT"
