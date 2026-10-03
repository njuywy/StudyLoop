import psycopg


def check_database(database_url: str) -> bool:
    if not database_url:
        return False
    try:
        with psycopg.connect(
            database_url, connect_timeout=3, options="-c statement_timeout=3000"
        ) as connection:
            return connection.execute("SELECT 1").fetchone() == (1,)
    except psycopg.Error:
        # Connection strings and database error details may contain credentials.
        return False
