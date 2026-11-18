"""Rehearse a sealed domain version change in two disposable schemas, atomically.

This is NOT a live deployment/migration endpoint. Only an unchanged schema and existing
field invariants are supported. Business rows and committed idempotency records are preserved.
"""

import hashlib
import json
import re
from typing import Any
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from specton.contracts import Column, DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.consistency import check
from specton.implementation.verify import inspect_package
from specton.specification.readiness import spec_hash

SCHEMA = re.compile(r"^specton_transfer_[a-f0-9]{32}_(?:before|after)$")
COMMANDS_DDL = (
    "CREATE TABLE _specton_commands(scope text,key text,request_hash text,result jsonb,"
    "PRIMARY KEY(scope,key))"
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _column_type(column: Column) -> str:
    kind = column.data_type.value
    if kind in {"char", "varchar"}:
        return ("character" if kind == "char" else "character varying") + f"({column.length})"
    if kind == "numeric":
        return f"numeric({column.precision},{column.scale or 0})"
    if kind in {"time", "timestamp", "timestamptz"}:
        base = "time" if kind == "time" else "timestamp"
        if column.time_precision is not None:
            base += f"({column.time_precision})"
        return base + (" with time zone" if kind == "timestamptz" else " without time zone")
    return kind


def plan(before: bytes, before_hash: str, after: bytes, after_hash: str) -> dict[str, Any]:
    left, lm = inspect_package(before, before_hash)
    right, rm = inspect_package(after, after_hash)
    specs = [SpecBundle.model_validate_json(f["spec/approved-spec.json"]) for f in (left, right)]
    result: dict[str, Any] = {
        "version": "domain-transfer-rehearsal-v1",
        "status": "blocked",
        "reasons": [],
        "source_hash": before_hash,
        "candidate_hash": after_hash,
        "source_spec_hash": spec_hash(specs[0]),
        "candidate_spec_hash": spec_hash(specs[1]),
        "schema_changed": left["backend/approved.sql"] != right["backend/approved.sql"],
        "scope": "isolated_same_schema_copy",
        "execution": "not_run",
        "deployment": "not_run",
        "business_acceptance": "not_run",
        "limitations": [
            "업무 테이블과 완료 요청 기록의 격리 복사만 검사합니다. "
            "고객 계정·세션 테이블이 있는 DB는 별도 이전 계약이 필요합니다."
        ],
        "tables": [],
    }
    if not all(s.domain for s in specs):
        result["reasons"].append("도메인 실행 명세의 동일 구조 이전만 지원합니다.")
    if (
        specs[0].baseline.project_id != specs[1].baseline.project_id
        or specs[0].spec_id != specs[1].spec_id
    ):
        result["reasons"].append("같은 프로젝트·명세의 버전만 비교할 수 있습니다.")
    if result["schema_changed"]:
        result["reasons"].append("저장 구조가 달라 별도의 이전·값 변환 계약이 필요합니다.")
    if specs[0].invariants != specs[1].invariants:
        result["reasons"].append("저장 데이터 조건 변경에는 기존 값의 적합성 검사가 필요합니다.")
    if (specs[0].domain.commands if specs[0].domain else ()) != (
        specs[1].domain.commands if specs[1].domain else ()
    ):
        result["reasons"].append(
            "원자 명령 변경에는 기존 업무 값과 중복 요청 이력의 이전 계약이 필요합니다."
        )
    for files, manifest in ((left, lm), (right, rm)):
        if manifest["template_version"] not in {
            "executable-design-v7",
            "executable-design-v8",
            "executable-design-v9",
            "executable-design-v10",
            "executable-design-v11",
        }:
            result["reasons"].append("이전 템플릿은 새 명세 일치 검사로 재생성이 필요합니다.")
        else:
            check(
                files,
                regenerate=manifest["template_version"]
                in {
                    "executable-design-v8",
                    "executable-design-v9",
                    "executable-design-v10",
                    "executable-design-v11",
                },
            )
    if not result["reasons"]:
        state = DesignState.model_validate_json(right["spec/design-state.json"])
        assert state.normalized is not None
        tables = {t.id: t for t in state.normalized.tables}
        parents: dict[str, set[str]] = {key: set() for key in tables}
        for fk in state.normalized.foreign_keys:
            parents[fk.table_id].add(fk.parent_table_id)
        ordered = []
        while parents:
            ready = sorted(key for key, values in parents.items() if not values)
            if not ready:
                result["reasons"].append("순환 참조 데이터에는 별도 이전 순서 계약이 필요합니다.")
                break
            for key in ready:
                table = tables[key]
                ordered.append(
                    {
                        "name": table.physical_name,
                        "columns": [c.physical_name for c in table.columns],
                        "column_types": [
                            [c.physical_name, _column_type(c), not c.nullable]
                            for c in table.columns
                        ],
                        "keys": [
                            next(c.physical_name for c in table.columns if c.id == key)
                            for key in table.primary_key
                        ],
                    }
                )
                del parents[key]
            for values in parents.values():
                values.difference_update(ready)
        if not result["reasons"]:
            result["tables"] = [
                *ordered,
                {
                    "name": "_specton_commands",
                    "columns": ["scope", "key", "request_hash", "result"],
                    "column_types": [
                        ["scope", "text", True],
                        ["key", "text", True],
                        ["request_hash", "text", False],
                        ["result", "jsonb", False],
                    ],
                    "keys": ["scope", "key"],
                },
            ]
            result["status"] = "ready_for_rehearsal"
    return {**result, "plan_hash": digest(result)}


def _shape(conn: psycopg.Connection[Any], schema: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity,"
        "a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped "
        "WHERE n.nspname=%s AND c.relkind IN ('r','p','v','m','f') ORDER BY c.relname,a.attnum",
        (schema,),
    ).fetchall()
    constraints = conn.execute(
        "SELECT c.relname,pg_get_constraintdef(k.oid) FROM pg_constraint k "
        "JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s ORDER BY 1,2",
        (schema,),
    ).fetchall()
    indexes = conn.execute(
        "SELECT tablename,indexdef FROM pg_indexes WHERE schemaname=%s ORDER BY 1,2", (schema,)
    ).fetchall()
    triggers = conn.execute(
        "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND NOT t.tgisinternal",
        (schema,),
    ).fetchone()
    if (
        triggers is None
        or triggers[0]
        or any(r[1] != "r" or r[2] or r[3] or r[7] or r[8] for r in rows)
    ):
        raise ValueError("지원하지 않는 트리거·테이블·행 정책·생성 컬럼입니다.")
    return {
        "columns": rows,
        "constraints": [(r[0], r[1].replace(schema + ".", "SCHEMA.")) for r in constraints],
        "indexes": [(r[0], r[1].replace(schema + ".", "SCHEMA.")) for r in indexes],
    }


def _fingerprint(
    conn: psycopg.Connection[Any], schema: str, table: dict[str, Any]
) -> dict[str, Any]:
    query = sql.SQL("SELECT to_jsonb(t)::text FROM {} t ORDER BY {} LIMIT 10001").format(
        sql.Identifier(schema, table["name"]), sql.SQL(",").join(map(sql.Identifier, table["keys"]))
    )
    h = hashlib.sha256()
    count = 0
    size = 0
    with conn.cursor(name="transfer_" + uuid4().hex, row_factory=tuple_row) as cursor:
        cursor.itersize = 100
        cursor.execute(query)
        for row in cursor:
            data = row[0].encode()
            count += 1
            size += len(data)
            if count > 10000 or size > 10 * 1024 * 1024:
                raise ValueError("격리 이전 검증의 데이터 한도를 초과했습니다.")
            h.update(len(data).to_bytes(8, "big"))
            h.update(data)
    return {"rows": count, "sha256": h.hexdigest()}


def transfer(
    conn: psycopg.Connection[Any],
    frozen: dict[str, Any],
    source_schema: str,
    target_schema: str,
    *,
    fault_after_tables: int | None = None,
) -> dict[str, Any]:
    """One transaction; source is locked/read only and target must be empty.

    Fault injection is a bounded rehearsal option, not executable customer input.
    Callers keep the old version active until separate review/cutover; this never switches it.
    """
    if (
        frozen.get("plan_hash") != digest({k: v for k, v in frozen.items() if k != "plan_hash"})
        or frozen.get("status") != "ready_for_rehearsal"
        or not SCHEMA.fullmatch(source_schema)
        or not SCHEMA.fullmatch(target_schema)
        or source_schema == target_schema
        or conn.info.transaction_status != TransactionStatus.IDLE
        or conn.row_factory is not tuple_row
    ):
        raise ValueError("고정 계획·별도 격리 스키마·빈 트랜잭션이 필요합니다.")
    tables = frozen["tables"]
    if not tables or any(
        not re.fullmatch(r"_?[a-z][a-z0-9_]{0,62}", n)
        for t in tables
        for n in [t["name"], *t["columns"], *t["keys"]]
    ):
        raise ValueError("이전 테이블 식별자가 잘못됐습니다.")
    with conn.transaction():
        conn.execute("SET LOCAL search_path=pg_catalog")
        conn.execute("SET LOCAL lock_timeout='2s'")
        conn.execute("SET LOCAL statement_timeout='15s'")
        for schema, table in sorted(
            (s, t["name"]) for s in (source_schema, target_schema) for t in tables
        ):
            conn.execute(
                sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
                    sql.Identifier(schema, table)
                )
            )
        left, right = _shape(conn, source_schema), _shape(conn, target_schema)
        if left != right:
            raise ValueError("실제 DB 구조가 서로 다릅니다.")
        columns: dict[str, list[str]] = {}
        for row in left["columns"]:
            columns.setdefault(row[0], []).append(row[4])
        if columns != {t["name"]: t["columns"] for t in tables}:
            raise ValueError("실제 테이블·컬럼이 고정 계획과 다릅니다.")
        types: dict[str, list[list[Any]]] = {}
        for row in left["columns"]:
            types.setdefault(row[0], []).append([row[4], row[5], row[6]])
        if types != {t["name"]: t["column_types"] for t in tables}:
            raise ValueError("실제 자료형·필수 여부가 승인 구조와 다릅니다.")
        source = {t["name"]: _fingerprint(conn, source_schema, t) for t in tables}
        if any(_fingerprint(conn, target_schema, t)["rows"] for t in tables):
            raise ValueError("대상 DB가 비어 있지 않습니다. 기존 값을 덮어쓰지 않습니다.")
        for index, table in enumerate(tables, 1):
            cols = sql.SQL(",").join(map(sql.Identifier, table["columns"]))
            conn.execute(
                sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                    sql.Identifier(target_schema, table["name"]),
                    cols,
                    cols,
                    sql.Identifier(source_schema, table["name"]),
                )
            )
            if fault_after_tables == index:
                raise RuntimeError("INJECTED_TRANSFER_FAILURE")
        target = {t["name"]: _fingerprint(conn, target_schema, t) for t in tables}
        unchanged = {t["name"]: _fingerprint(conn, source_schema, t) for t in tables}
        if source != target or source != unchanged:
            raise ValueError("행 수·값 해시가 다릅니다.")
    return {
        "status": "passed",
        "plan_hash": frozen["plan_hash"],
        "tables": target,
        "source_unchanged": True,
        "atomic": True,
        "cutover": "not_run",
        "business_acceptance": "not_run",
    }
