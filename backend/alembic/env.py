from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers tables)
from app.core.config import get_settings
from app.core.db import Base, normalise_url

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
# "%" must be doubled for configparser (Supabase passwords may contain it after URL-encoding)
config.set_main_option("sqlalchemy.url", normalise_url(get_settings().database_url).replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # A caller (app/migrate.py) may pass its own open connection, e.g. one holding an advisory lock.
    given = config.attributes.get("connection")
    if given is not None:
        context.configure(connection=given, target_metadata=target_metadata, compare_type=True)
        context.run_migrations()
        return
    is_pg = config.get_main_option("sqlalchemy.url").startswith("postgresql")
    connect_args = {"prepare_threshold": None} if is_pg else {}
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool, connect_args=connect_args)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
