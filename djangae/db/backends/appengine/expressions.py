from django.db.models.expressions import F
from djangae.db.utils import get_prepared_db_value


CONNECTORS = {
    F.ADD: lambda l, r: l + r,
    F.SUB: lambda l, r: l - r,
    F.MUL: lambda l, r: l * r,
    F.DIV: lambda l, r: l / r,
}


def evaluate_expression(expression, instance, connection):
    """ A limited evaluator for Django's F expressions. Although they're evaluated
        before the database call, so they don't provide the race condition protection,
        but neither does our update() implementation so we provide this for convenience.
    """
    if isinstance(expression, (basestring, int, float)):
        return expression

    if hasattr(expression, 'name'):
        field = instance._meta.get_field(expression.name)
        return get_prepared_db_value(connection, instance._original, field)

    if hasattr(expression, 'value'):
        return expression.value

    if hasattr(expression, 'connector') and expression.connector in CONNECTORS:
        if hasattr(expression, 'children'):
            lhs, rhs = expression.children
        else:
            lhs, rhs = expression.lhs, expression.rhs

        return CONNECTORS[expression.connector](
            evaluate_expression(lhs, instance, connection),
            evaluate_expression(rhs, instance, connection),
        )

    raise NotImplementedError("Support for expression %r isn't implemented", expression)
