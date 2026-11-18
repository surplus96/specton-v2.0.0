"""Actual sessions, approved generated code, decimal HTTP values and PostgreSQL rows."""

from decimal import Decimal

import psycopg
import pytest
from psycopg import sql
from test_atomic_commands import application as application
from test_atomic_commands import login, observed, submit

pytestmark = [pytest.mark.db]


@pytest.fixture
def seeded(application):
    a = application
    with psycopg.connect(a["dsn"]) as conn:
        conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(a["child"])))
    headers = login(a["client"], "administrator")
    op = next(
        o
        for o in a["config"]["operations"]
        if o["table_id"] == a["config"]["tables"][1]["id"] and o["action"] == "insert"
    )
    for sequence, (when, amount) in enumerate(
        [("2030-01-01", "1.01"), ("2030-01-02", "2.02"), ("2030-02-01", "99.00")], 1
    ):
        r = a["client"].post(
            "/api" + op["path"],
            json={
                "parent_id": "one",
                "sequence": sequence,
                "scheduled": when,
                "status": "open",
                "amount": amount,
            },
            headers={**headers, "Idempotency-Key": "seed-" + str(sequence)},
        )
        assert r.status_code == 200, r.text
    a["headers"] = login(a["client"], "operator")
    return a


def query(a, **changes):
    return a["client"].post(
        "/api/calculations/summary",
        json={"id": "one", "start": "2030-01-01", "end": "2030-02-01", "budget": "3.00", **changes},
        headers=a["headers"],
    )


@pytest.mark.parametrize(
    "application", [("inventory", "query"), ("maintenance", "query")], indirect=True
)
def test_exact_aggregates_boundary_half_even_ratio_and_no_writes(seeded):
    a = seeded
    before = observed(a)
    result = query(a)
    assert result.status_code == 200, result.text
    assert result.json() == {
        "count": "2",
        "total": "3.03",
        "average": "1.52",
        "minimum": "1.01",
        "maximum": "2.02",
        "ratio": "1.0100",
    }
    assert query(a, end="2030-01-01").json() == {
        "count": "0",
        "total": "0.00",
        "average": None,
        "minimum": "0.00",
        "maximum": "0.00",
        "ratio": "0.0000",
    }
    assert query(a, start="2030-01-02").json()["total"] == "2.02"
    assert observed(a) == before


@pytest.mark.parametrize(
    "application", [("inventory", "query"), ("maintenance", "query")], indirect=True
)
def test_zero_denominator_reversed_range_row_limit_auth_and_csrf(seeded):
    a = seeded
    before = observed(a)
    for body in [{"budget": "0.00"}, {"start": "2031-01-01"}]:
        r = query(a, **body)
        assert r.status_code == 409 and r.json()["detail"] == "CALCULATION_ERROR"
    assert (
        a["client"]
        .post(
            "/api/calculations/summary",
            json={"id": "one", "start": "2030-01-01", "end": "2030-02-01", "budget": "3.00"},
        )
        .status_code
        == 403
    )
    a["headers"] = login(a["client"], "administrator")
    assert query(a).status_code == 403
    a["headers"] = login(a["client"], "operator")
    assert observed(a) == before
    with psycopg.connect(a["dsn"]) as conn:
        for seq in [4, 5]:
            conn.execute(
                sql.SQL("INSERT INTO {} VALUES(%s,%s,%s,%s,%s)").format(sql.Identifier(a["child"])),
                ("one", seq, "2030-01-03", "open", Decimal("1.00")),
            )
    r = query(a)
    assert r.status_code == 409 and r.json()["detail"] == "RESULT_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    "application", [("inventory", "calculated"), ("maintenance", "calculated")], indirect=True
)
def test_calculated_values_participate_in_atomic_rollback_and_retry(application):
    a = application
    before = observed(a)
    zero = submit(a, divisor=0)
    assert zero.status_code == 409 and zero.json()["detail"] == "CALCULATION_ERROR"
    assert observed(a) == before
    # The generated command's after-write guard still rolls back both written records.
    r = submit(a, amount="6.00" if a["domain"] == "inventory" else "101.00", divisor=1)
    assert r.status_code == 409 and observed(a) == before
    success = submit(a, amount="2.00", divisor=1)
    assert success.status_code == 200, success.text
    assert submit(a, amount="2.00", divisor=1).json() == success.json()
    assert observed(a)[2] == 1
