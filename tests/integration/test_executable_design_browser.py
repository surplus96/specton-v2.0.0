"""Real list/update API and browser probes, followed by mail-driven design regeneration."""

import pytest
from implementation_support import collection_executable, inventory_executable
from test_feedback_browser import connected as connected
from test_feedback_browser import settings as settings
from test_feedback_browser import test_browser_mail_to_adoption as test_browser_mail_to_adoption
from test_feedback_browser import verified as verified
from test_feedback_browser import workspace as workspace
from test_identity_projects import headers
from test_specifications import edit, expectation

from specton.contracts import DesignState

pytestmark = [pytest.mark.db, pytest.mark.docker_browser]


@pytest.fixture
def source(workspace, pool):
    client, initial, _, run = workspace
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s "
            "ORDER BY revision DESC LIMIT 1",
            (run,),
        ).fetchone()
    state = DesignState.model_validate({**row["normalized_model"], "run_id": run})
    bundle = collection_executable(inventory_executable(initial, state))
    response = edit(client, initial, bundle)
    assert response.status_code == 200, response.text
    spec = response.json()
    url = "/api/v1/specs/" + spec["bundle"]["spec_id"]
    assert (
        client.post(url + "/approve", json=expectation(spec), headers=headers(client)).status_code
        == 200
    )
    result = client.post(url + "/implementations", json=expectation(spec), headers=headers(client))
    assert result.status_code == 200, result.text
    return client, spec, result.json()
