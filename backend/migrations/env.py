import os

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

# Use the configured PostgreSQL connection without logging or interpolating its password.
database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    raise RuntimeError("DATABASE_URL is required for migrations")
url = make_url(database_url).set(drivername="postgresql+psycopg")

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
