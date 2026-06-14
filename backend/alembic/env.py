import os
from pathlib import Path
from logging.config import fileConfig
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import engine_from_config, pool

from alembic import context

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

if load_dotenv is not None:
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env", override=True)
    load_dotenv(backend_root / ".env", override=True)


def _normalize_database_url(raw_url: str):
    parsed = urlparse(raw_url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    normalized_url = urlunparse(parsed._replace(query=urlencode(query_items)))

    if parsed.scheme.startswith("postgresql+asyncpg"):
        normalized_url = urlunparse(parsed._replace(scheme="postgresql+psycopg2", query=urlencode(query_items)))
    elif parsed.scheme == "postgresql":
        normalized_url = urlunparse(parsed._replace(scheme="postgresql+psycopg2", query=urlencode(query_items)))

    return normalized_url, {}

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.models import metadata as target_metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/agentic_rag")
DATABASE_URL, DATABASE_CONNECT_ARGS = _normalize_database_url(DATABASE_URL)
config.set_main_option('sqlalchemy.url', DATABASE_URL.replace('%', '%%'))


def _sqlite_fallback_url():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    db_path = os.path.abspath(os.path.join(base_dir, "alembic_fallback.db"))
    return "sqlite:///" + db_path.replace("\\", "/")


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    def do_run_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    try:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section),
            prefix='sqlalchemy.',
            poolclass=pool.NullPool,
            connect_args=DATABASE_CONNECT_ARGS,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)
    except Exception as exc:
        fallback_url = _sqlite_fallback_url()
        print(f"Alembic could not reach {DATABASE_URL!r} ({exc.__class__.__name__}: {exc}). Falling back to SQLite at {fallback_url!r}.")
        config.set_main_option('sqlalchemy.url', fallback_url)
        connectable = engine_from_config(
            config.get_section(config.config_ini_section),
            prefix='sqlalchemy.',
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
