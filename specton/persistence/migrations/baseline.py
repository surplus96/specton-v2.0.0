"""기존 DB의 구조를 확인한 뒤에만 기준 버전을 등록한다.

현재 연결의 트랜잭션 안에서 비어 있는 비교 스키마를 만들고 제거한다.
데이터는 복사하지 않으며 체크포인터 등 다른 모듈의 표는 건드리지 않는다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, inspect, text

from specton.persistence.migrations import SchemaVersionError

TABLES = frozenset(
    {
        "run",
        "document",
        "source_block",
        "model_snapshot",
        "finding",
        "approval",
        "artifact",
        "artifact_validation",
        "approval_basis",
        "run_event",
        "job_lease",
    }
)


def baseline_sql() -> str:
    return files("specton.persistence").joinpath("schema.sql").read_text(encoding="utf-8")


def _search_path(conn: Connection, value: str) -> None:
    conn.execute(text("SELECT set_config('search_path', :path, true)"), {"path": value})


@contextmanager
def _reference(conn: Connection) -> Iterator[str]:
    previous = conn.exec_driver_sql("SHOW search_path").scalar_one()
    schema = f"_specton_reference_{uuid4().hex}"
    with conn.begin_nested():
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        _search_path(conn, schema)
        conn.exec_driver_sql(baseline_sql(), execution_options={"no_parameters": True})
        yield schema
        _search_path(conn, previous)
        conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def _signature(conn: Connection, schema: str) -> dict[str, Any]:
    _search_path(conn, schema)
    inspector = inspect(conn)
    result: dict[str, Any] = {}
    for table in sorted(TABLES & set(inspector.get_table_names(schema=schema))):
        columns = {
            c["name"]: {
                "type": str(c["type"]),
                "nullable": c["nullable"],
                "default": c["default"],
                "identity": c.get("identity"),
                "computed": c.get("computed"),
            }
            for c in inspector.get_columns(table, schema=schema)
        }
        foreign = inspector.get_foreign_keys(table, schema=schema)
        for fk in foreign:
            if fk["referred_schema"] == schema:
                fk["referred_schema"] = "__self__"
        result[table] = {
            "columns": columns,
            "pk": inspector.get_pk_constraint(table, schema=schema),
            "unique": sorted(
                inspector.get_unique_constraints(table, schema=schema), key=lambda x: str(x["name"])
            ),
            "foreign": sorted(foreign, key=lambda x: str(x["name"])),
            "checks": {
                c["name"]: c["sqltext"]
                for c in inspector.get_check_constraints(table, schema=schema)
            },
            "indexes": sorted(
                inspector.get_indexes(table, schema=schema), key=lambda x: str(x["name"])
            ),
        }
    return result


def _check_extra_behavior(conn: Connection, schema: str) -> None:
    rows = (
        conn.execute(
            text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema AND c.relname = ANY(:tables) AND (
            c.relkind <> 'r' OR c.relrowsecurity OR c.relforcerowsecurity OR EXISTS (
                SELECT 1 FROM pg_trigger t WHERE t.tgrelid = c.oid AND NOT t.tgisinternal
            ) OR EXISTS (SELECT 1 FROM pg_rewrite r WHERE r.ev_class = c.oid)
            OR EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid
                       AND NOT k.convalidated)
            OR EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid
                       AND (NOT i.indisvalid OR NOT i.indisready))
            OR EXISTS (SELECT 1 FROM pg_inherits h WHERE h.inhrelid = c.oid OR h.inhparent = c.oid)
        )
    """),
            {"schema": schema, "tables": sorted(TABLES)},
        )
        .scalars()
        .all()
    )
    if rows:
        raise SchemaVersionError(f"지원하지 않는 플랫폼 표 동작: {', '.join(rows)}")


def _legacy_signature(conn: Connection, schema: str, actual: dict[str, Any]) -> dict[str, Any]:
    """알려진 과거 열·CHECK 차이만 수용한다. 임의 type/FK/제약 변경은 거절한다."""
    expected = _signature(conn, schema)
    for table, names in {
        "run": ("stage", "interrupt", "error"),
        "source_block": ("notice", "user_decision", "excluded_reason"),
    }.items():
        for name in names:
            if name not in actual.get(table, {}).get("columns", {}):
                del expected[table]["columns"][name]
                if name == "user_decision":
                    expected[table]["checks"].pop("source_block_user_decision_check")
    if "source_block" in actual:
        expected["source_block"]["columns"]["source_text"]["nullable"] = (
            actual["source_block"]["columns"].get("source_text", {}).get("nullable", True)
        )
    old_checks = {
        ("document", "document_file_format_check"): "file_format IN ('xlsx', 'csv', 'pdf', 'hwpx')",
        (
            "artifact",
            "artifact_kind_check",
        ): "kind IN ('requirements', 'functions', 'erd', 'ddl', 'rtm', 'review')",
        (
            "artifact",
            "artifact_file_format_check",
        ): "file_format IN ('md', 'pdf', 'mmd', 'sql', 'xlsx', 'csv')",
    }
    for (table, name), expression in old_checks.items():
        conn.exec_driver_sql(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"')
        conn.exec_driver_sql(f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK ({expression})')
        old = _signature(conn, schema)[table]["checks"][name]
        if actual.get(table, {}).get("checks", {}).get(name) == old:
            expected[table]["checks"][name] = old
    return expected


def verify_baseline(conn: Connection, *, allow_legacy: bool = False) -> None:
    schema = str(conn.exec_driver_sql("SELECT current_schema()").scalar_one())
    _check_extra_behavior(conn, schema)
    actual = _signature(conn, schema)
    with _reference(conn) as reference:
        expected = (
            _legacy_signature(conn, reference, actual)
            if allow_legacy
            else _signature(conn, reference)
        )
    different = sorted(t for t in TABLES if actual.get(t) != expected.get(t))
    if different:
        raise SchemaVersionError(
            f"플랫폼 스키마 불일치 ({', '.join(different)}). 자동 stamp/수정하지 않습니다. "
            "백업 사본의 구조를 검토하세요."
        )


def install_baseline(conn: Connection) -> None:
    schema = str(conn.exec_driver_sql("SELECT current_schema()").scalar_one())
    objects = set(inspect(conn).get_table_names(schema=schema))
    objects.update(inspect(conn).get_view_names(schema=schema))
    _check_extra_behavior(conn, schema)
    if objects & TABLES:
        verify_baseline(conn, allow_legacy=True)
    conn.exec_driver_sql(baseline_sql(), execution_options={"no_parameters": True})
    verify_baseline(conn)
