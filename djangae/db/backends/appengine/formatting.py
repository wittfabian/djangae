import json


SELECT_PATTERN = """
SELECT (%(columns)s) FROM %(table)s
WHERE %(where)s
ORDER BY %(order)s
OFFSET %(offset)s
LIMIT %(limit)s
""".lstrip()

INSERT_PATTERN = """
INSERT INTO %(table)s (%(columns)s)
VALUES (%(values)s)
""".lstrip()

UPDATE_PATTERN = """
UPDATE %(table)s (%(columns)s)
VALUES (%(values)s)
WHERE %(where)s
""".lstrip()

DELETE_PATTERN = """
DELETE FROM %(table)s
WHERE %(where)s
""".lstrip()


def _generate_insert_sql(command):
    return ""


def _generate_select_sql(command, representation):
    has_offset = representation["low_mark"] > 0
    has_limit = representation["high_mark"] is not None
    has_ordering = bool(representation["order_by"])
    has_where = bool(representation["where"])

    lines = SELECT_PATTERN.split("\n")

    # Remove limit and offset and where if we don't need them
    if not has_limit:
        del lines[4]

    if not has_offset:
        del lines[3]

    if not has_ordering:
        del lines[2]

    if not has_where:
        del lines[1]

    sql = "\n".join(lines)

    columns = (
        "*" if not representation["columns"]
        else ", ".join(sorted(representation["columns"])) # Just to make the output predictable
    )

    where = []
    for branch in representation["where"]:
        branch = "(" + " AND ".join(["%s%s" % (k, v) for k, v in branch.items()]) + ")"
        where.append(branch)

    ordering = [
        ("%s %s" % (x.lstrip("-"), "DESC" if x.startswith("-") else "")).strip()
        for x in representation["order_by"]
    ]

    replacements = {
        "table": representation["table"],
        "columns": columns,
        "offset": representation["low_mark"],
        "limit": (representation["high_mark"] or 0) - (representation["low_mark"] or 0),
        "where": " OR ".join(where),
        "order": ", ".join(ordering)
    }

    return (sql % replacements).replace("\n", " ").strip()


def _generate_delete_sql(command, representation):
    return ""


def _generate_update_sql(command, representation):
    return ""


def generate_sql_representation(command):
    from .commands import SelectCommand, DeleteCommand, UpdateCommand, InsertCommand

    if isinstance(command, InsertCommand):
        # Inserts don't have a .query so we have to deal with them
        # seprately
        return _generate_insert_sql(command)

    representation = json.loads(command.query.serialize())

    if isinstance(command, SelectCommand):
        return _generate_select_sql(command, representation)
    elif isinstance(command, DeleteCommand):
        return _generate_delete_sql(command, representation)
    elif isinstance(command, UpdateCommand):
        return _generate_update_sql(command, representation)

    raise NotImplementedError("Unrecognized query type")

    
