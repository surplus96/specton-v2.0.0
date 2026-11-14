"""명시적 플랫폼 이전 CLI: python -m specton.persistence.migrate upgrade|check|current."""

import argparse
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from specton.persistence.migrations import HEAD, SchemaVersionError

if TYPE_CHECKING:
    from specton.persistence.db import Pool

_COMMAND_LOCK = Lock()  # Alembic의 프로세스 전역 context도 직렬화한다.


def _schema_name(value: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value) or value.startswith("pg_"):
        raise ValueError("schema는 PostgreSQL 내부 이름이 아닌 소문자 식별자여야 합니다")
    return value


@contextmanager
def migration_connection(config: Config) -> Iterator[Connection]:
    from specton.config import Settings

    dsn = config.attributes.get("dsn") or str(Settings().app_database_url)
    arguments = context_arguments(config)
    schema = _schema_name(arguments.get("schema", "public"))
    engine = create_engine(
        "postgresql+psycopg://",
        creator=lambda: psycopg.connect(dsn, connect_timeout=5),
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_namespace WHERE nspname=:schema"), {"schema": schema}
            ).scalar()
            if exists is None:
                raise SchemaVersionError("대상 schema가 없습니다. 빈 schema를 먼저 준비하세요.")
            conn.info["migration_schema"] = schema
            conn.execute(
                text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
            )
            conn.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
            conn.exec_driver_sql("SET LOCAL statement_timeout = '60s'")
            conn.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended("
                    "current_database() || ':specton:migration:' || :schema, 0))"
                ),
                {"schema": schema},
            )
            yield conn
    finally:
        engine.dispose()


def context_arguments(config: Config) -> dict[str, str]:
    result = dict(config.attributes.get("arguments", {}))
    for item in getattr(config.cmd_opts, "x", None) or []:
        key, _, value = item.partition("=")
        result[key] = value
    return result


def upgrade(dsn: str, *, schema: str = "public") -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    config.attributes.update(dsn=dsn, arguments={"schema": _schema_name(schema)})
    with _COMMAND_LOCK:
        command.upgrade(config, "head")


def current_version(pool: "Pool") -> str | None:
    with pool.connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() "
            "AND table_name='alembic_version'"
        ).fetchone()
        if exists is None:
            return None
        versions = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        if len(versions) != 1:
            raise SchemaVersionError("플랫폼 스키마 버전은 하나여야 합니다")
        return str(versions[0]["version_num"])


def require_current_schema(pool: "Pool") -> None:
    if current_version(pool) != HEAD:
        raise SchemaVersionError(
            "플랫폼 DB 이전이 필요합니다. 서비스 시작 전에 "
            "uv run python -m specton.persistence.migrate upgrade를 실행하세요."
        )


def main() -> None:
    from specton.config import Settings
    from specton.persistence.db import create_pool

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("upgrade", "check", "current"))
    parser.add_argument("--schema", default="public", type=_schema_name)
    args = parser.parse_args()
    settings = Settings()
    try:
        if args.action == "upgrade":
            upgrade(str(settings.app_database_url), schema=args.schema)
            print(f"플랫폼 스키마: {HEAD}")
        else:
            with create_pool(settings, schema=args.schema) as pool:
                if args.action == "check":
                    require_current_schema(pool)
                print(current_version(pool) or "unversioned")
    except SchemaVersionError as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
