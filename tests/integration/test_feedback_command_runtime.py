"""The mailed command program is executed with real auth, DB, replay and rollback."""

from decimal import Decimal

import calculation_support
import pytest
from feedback_contract_support import QUOTE, reviews, suggestion
from test_atomic_commands import application as application
from test_atomic_commands import observed, submit

from specton.feedback.analysis import propose

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def mailed_program(monkeypatch):
    original = calculation_support.calculated_command

    def changed(domain):
        bundle, state, artifacts = original(domain)
        bundle, _ = propose(bundle, suggestion(bundle, True), QUOTE, reviews(bundle))
        return bundle, state, artifacts

    monkeypatch.setattr(calculation_support, "calculated_command", changed)


@pytest.mark.parametrize(
    "application", [("inventory", "calculated"), ("maintenance", "calculated")], indirect=True
)
def test_mail_changes_numeric_command_but_preserves_replay_and_rollback(application):
    a = application
    before = observed(a)
    assert submit(a, divisor=0).status_code == 409
    assert observed(a) == before
    assert (
        submit(a, amount="6.00" if a["domain"] == "inventory" else "101.00", divisor=1).status_code
        == 409
    )
    assert observed(a) == before
    response = submit(a, amount="1.03", divisor=2)
    assert response.status_code == 200, response.text
    parent, child, count = observed(a)
    # 1.03 / 2 = .515; mailed down policy yields .51 (previous half_even was .52).
    assert child[0]["amount"] == Decimal("0.51")
    assert parent[0]["amount"] == Decimal("4.49" if a["domain"] == "inventory" else "0.51")
    assert count == 1
    assert submit(a, amount="1.03", divisor=2).json() == response.json()
    assert observed(a) == (parent, child, count)
