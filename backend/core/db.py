from django.db import connection


def scalar(sql, params=()):
    """Run a query that returns one value (usually a function call) and return it."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]
