from django.db.models.expressions import Expression
from djangae.db.utils import get_prepared_db_value


CONNECTORS = {
    Expression.ADD: lambda l, r: l + r,
    Expression.SUB: lambda l, r: l - r,
    Expression.MUL: lambda l, r: l * r,
    Expression.DIV: lambda l, r: l / r,
}


def evaluate_expression(expression, instance, connection):
    """ A limited evaluator for Django's F expressions. Although they're evaluated
        before the database call, so they don't provide the race condition protection,
        but neither does our update() implementation so we provide this for convenience.
    """
    if hasattr(expression, 'name'):
        field = instance._meta.get_field(expression.name)
        return get_prepared_db_value(connection, instance._original, field)

    if hasattr(expression, 'value'):
        return expression.value

    if hasattr(expression, 'connector') and expression.connector in CONNECTORS:
        return CONNECTORS[expression.connector](
            evaluate_expression(expression.lhs, instance, connection),
            evaluate_expression(expression.rhs, instance, connection),
        )

    raise NotImplementedError("Support for expression %r isn't implemented", expression)
