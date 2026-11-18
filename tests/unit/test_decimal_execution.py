"""Independent decimal edge oracles against the code shipped to customer applications."""

from decimal import Decimal

import pytest
from fastapi import HTTPException

from specton.implementation.package import TEMPLATES

namespace = {}
exec(
    compile((TEMPLATES / "runtime/calculations.py.txt").read_text(), "calculations.py", "exec"),
    namespace,
)
rounded, calculate, aggregate = (namespace[name] for name in ["rounded", "calculate", "aggregate"])


def policy(rounding="half_even", precision=8, scale=2):
    return {"precision": precision, "scale": scale, "rounding": rounding, "unit": {}}


@pytest.mark.parametrize(
    "value,rounding,expected",
    [
        ("1.005", "half_even", "1.00"),
        ("1.005", "half_up", "1.01"),
        ("-1.009", "down", "-1.00"),
        ("-0.001", "down", "0.00"),
    ],
)
def test_explicit_rounding_and_negative_zero(value, rounding, expected):
    assert str(rounded(Decimal(value), policy(rounding))) == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "999.995"])
def test_invalid_or_overflow_after_rounding_is_an_error(value):
    with pytest.raises(HTTPException) as caught:
        rounded(Decimal(value), policy(precision=5))
    assert caught.value.status_code == 409 and caught.value.detail == "CALCULATION_ERROR"


@pytest.mark.parametrize(
    "zero,expected", [("zero", Decimal("0.00")), ("null", None), ("error", "error")]
)
def test_explicit_zero_denominator_policy(zero, expected):
    program = [
        {
            "id": "x",
            "operator": "divide",
            "left": {"kind": "number", "value": "1"},
            "right": {"kind": "number", "value": "0"},
            "result": policy(),
            "null_policy": "error",
            "zero_division": zero,
        }
    ]
    if expected == "error":
        with pytest.raises(HTTPException):
            calculate(program, lambda _: None)
    else:
        assert calculate(program, lambda _: None) == {"x": expected}


def test_step_order_rounding_absolute_multiplication_and_null_propagation():
    program = [
        {
            "id": "first",
            "operator": "divide",
            "left": {"kind": "number", "value": "1"},
            "right": {"kind": "number", "value": "8"},
            "result": policy(),
            "null_policy": "error",
            "zero_division": "error",
        },
        {
            "id": "second",
            "operator": "multiply",
            "left": {"kind": "calculated", "calculation_id": "first"},
            "right": {"kind": "number", "value": "100"},
            "result": policy(),
            "null_policy": "error",
            "zero_division": "error",
        },
        {
            "id": "third",
            "operator": "absolute",
            "left": {"kind": "number", "value": "-2.51"},
            "right": None,
            "result": policy(),
            "null_policy": "error",
            "zero_division": "error",
        },
        {
            "id": "missing",
            "operator": "add",
            "left": {"kind": "input", "name": "nullable"},
            "right": {"kind": "number", "value": "2"},
            "result": policy(),
            "null_policy": "propagate",
            "zero_division": "error",
        },
    ]
    assert calculate(program, lambda _: None) == {
        "first": Decimal("0.12"),
        "second": Decimal("12.00"),
        "third": Decimal("2.51"),
        "missing": None,
    }


def test_aggregate_null_count_empty_and_all_null_are_explicit():
    measure = {
        "id": "mean",
        "operator": "average",
        "name": "amount",
        "null_policy": "ignore",
        "empty_policy": "null",
        "result": policy(),
    }
    rows = [{"amount": Decimal("1.00")}, {"amount": None}, {"amount": Decimal("2.00")}]
    assert aggregate(rows, [measure]) == {"mean": Decimal("1.50")}
    assert aggregate([{"amount": None}], [measure]) == {"mean": None}
    assert aggregate([], [{**measure, "empty_policy": "zero"}]) == {"mean": Decimal("0.00")}
    for samples, changes in [(rows, {"null_policy": "error"}), ([], {"empty_policy": "error"})]:
        with pytest.raises(HTTPException):
            aggregate(samples, [{**measure, **changes}])
    assert aggregate(
        [{"amount": None}],
        [{**measure, "id": "n", "operator": "count", "name": None, "result": policy(scale=0)}],
    ) == {"n": Decimal(1)}
