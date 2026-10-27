from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from layer0.infrastructure.db.session import Base
# Import models so they're registered on Base.metadata before autogenerate runs.
from layer0.infrastructure.db import models  # noqa: F401
from layer1.infrastructure.db import models as layer1_models  # noqa: F401
from auth import models as auth_models  # noqa: F401
from trips import models as trips_models  # noqa: F401
from personal import models as personal_models  # noqa: F401
from hive2 import models as hive2_models  # noqa: F401
from shared.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata

# PostGIS creates its own system tables/views (spatial_ref_sys, geometry_columns,
# etc.) that are NOT part of our application schema. Without this filter,
# autogenerate sees them as "unknown to our metadata" and generates a
# migration that DROPS them — which breaks PostGIS. Confirmed by actually
# running `alembic revision --autogenerate` against a real PostGIS instance;
# the first attempt did exactly this before this filter was added.
_POSTGIS_SYSTEM_TABLES = {"spatial_ref_sys", "geometry_columns", "geography_columns", "raster_columns", "raster_overviews"}

_EXTENSION_TABLES_QUERY = text("""
    SELECT c.relname
    FROM pg_depend d
    JOIN pg_class c ON c.oid = d.objid AND c.relkind = 'r'
    JOIN pg_extension e ON e.oid = d.refobjid
    WHERE d.deptype = 'e'
""")


def _make_include_object(extension_tables: set[str]):
    excluded = _POSTGIS_SYSTEM_TABLES | extension_tables

    def include_object(object_, name, type_, reflected, compare_to):
        if type_ == "table" and name in excluded:
            return False
        return True

    return include_object


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, include_object=_make_include_object(set()),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    extension_tables = {row[0] for row in connection.execute(_EXTENSION_TABLES_QUERY).fetchall()}
    context.configure(
        connection=connection, target_metadata=target_metadata,
        include_object=_make_include_object(extension_tables),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
