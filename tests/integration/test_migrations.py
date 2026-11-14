"""실제 PostgreSQL에서 기존 데이터 보존·버전 위조·원자적 실패를 검증한다."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from specton.persistence.db import Pool, apply_schema, create_checkpointer
from specton.persistence.migrate import current_version, require_current_schema
from specton.persistence.migrations import HEAD, SchemaVersionError
from specton.persistence.runs import create_run, get_run

pytestmark = pytest.mark.db


def _schema(pool: Pool) -> str:
    with pool.connection() as conn:
        return conn.execute("SELECT current_schema() AS name").fetchone()["name"]


def test_legacy_baseline_keeps_rows_and_library_tables(pool: Pool) -> None:
    create_checkpointer(pool)
    with pool.connection() as conn:
        run = create_run(conn, "owner", "inventory")
        before = conn.execute("SELECT * FROM run").fetchall()
        library = conn.execute("SELECT * FROM checkpoint_migrations ORDER BY v").fetchall()
        conn.execute(
            "DROP TABLE design_baseline,project_run,project,login_session,"
            "oauth_attempt,app_user,alembic_version"
        )
    assert current_version(pool) is None
    with pytest.raises(SchemaVersionError, match="이전이 필요"):
        require_current_schema(pool)
    apply_schema(pool)
    apply_schema(pool)
    require_current_schema(pool)
    with pool.connection() as conn:
        assert conn.execute("SELECT * FROM run").fetchall() == before
        assert get_run(conn, run.run_id, "owner").run_id == run.run_id
        assert conn.execute("SELECT * FROM checkpoint_migrations ORDER BY v").fetchall() == library
    assert current_version(pool) == HEAD


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        "ALTER TABLE run ALTER COLUMN revision TYPE bigint",
        "ALTER TABLE document DROP CONSTRAINT document_run_id_fkey",
        "ALTER TABLE run DROP CONSTRAINT run_status_check",
        "CREATE INDEX unexpected_index ON run (pack)",
        "ALTER TABLE run ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE run ADD COLUMN unexpected text",
        "DROP TABLE job_lease",
    ],
)
def test_unknown_schema_changes_fail_without_stamp_or_data_loss(
    pool: Pool, versioned: bool, change: str
) -> None:
    with pool.connection() as conn:
        create_run(conn, "owner", "inventory")
        before = conn.execute("SELECT * FROM run").fetchall()
        if not versioned:
            conn.execute(
                "DROP TABLE design_baseline,project_run,project,login_session,"
                "oauth_attempt,app_user,alembic_version"
            )
        conn.execute(change.encode())
    with pytest.raises(SchemaVersionError):
        apply_schema(pool)
    assert current_version(pool) == (HEAD if versioned else None)
    with pool.connection() as conn:
        rows = conn.execute("SELECT * FROM run").fetchall()
        for row in rows:
            row.pop("unexpected", None)
        assert rows == before
        assert (
            conn.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname LIKE '_specton_reference_%'"
            ).fetchall()
            == []
        )


def test_unknown_future_version_blocks_startup(pool: Pool) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE alembic_version SET version_num='future_revision'")
    with pytest.raises(SchemaVersionError):
        require_current_schema(pool)


def test_concurrent_upgrade_is_idempotent(pool: Pool) -> None:
    schema = _schema(pool)
    with pool.connection() as conn:
        conn.execute(
            "DROP TABLE design_baseline,project_run,project,login_session,"
            "oauth_attempt,app_user,alembic_version"
        )

    def migrate_in_process() -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "specton.persistence.migrate", "upgrade", "--schema", schema],
            env={**os.environ, "SPECTON_APP_DATABASE_URL": str(pool.conninfo)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [executor.submit(migrate_in_process) for _ in range(2)]
        for future in results:
            future.result(timeout=35)
    assert current_version(pool) == HEAD


def test_destructive_baseline_downgrade_is_refused(pool: Pool) -> None:
    with pool.connection() as conn:
        create_run(conn, "owner", "inventory")
        before = conn.execute("SELECT * FROM run").fetchall()
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[2] / "specton/persistence/migrations")
    )
    config.attributes.update(dsn=pool.conninfo, arguments={"schema": _schema(pool)})
    with pytest.raises(SchemaVersionError, match="삭제"):
        command.downgrade(config, "base")
    assert current_version(pool) == HEAD
    with pool.connection() as conn:
        assert conn.execute("SELECT * FROM run").fetchall() == before
