"""External OAuth/Gmail/LLM fixtures; actual owner/session/queue/spec/source/adoption database."""

from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_adoptions import review as adoption_review
from test_identity_projects import headers, login
from test_previews import settings as settings
from test_previews import source as source
from test_previews import verified as verified
from test_previews import workspace as workspace

from specton.api.main import create_app
from specton.feedback import analysis, jobs, worker
from specton.integrations import gmail
from specton.integrations.google_identity import GoogleIdentity

pytestmark = pytest.mark.db


@pytest.fixture
def connected(verified, settings, monkeypatch):
    settings.gmail_token_key = SecretStr(Fernet.generate_key().decode())
    settings.feedback_analysis_enabled = True
    client = verified[0][0]
    monkeypatch.setattr(
        gmail, "exchange", lambda *a: (GoogleIdentity("one", "one@example.com"), "refresh-secret")
    )
    monkeypatch.setattr(gmail, "revoke", lambda *a: True)
    start = client.post("/api/v1/integrations/gmail/connect", headers=headers(client))
    assert start.status_code == 200, start.text
    url = start.json()["url"]
    query = parse_qs(urlsplit(url).query)
    assert gmail.SCOPE in query["scope"][0]
    callback = gmail.CALLBACK + "?state=" + query["state"][0] + "&code=test"
    result = client.get(callback, follow_redirects=False)
    assert result.status_code == 303, result.text
    assert result.headers["location"].endswith("connected"), result.headers
    assert client.get(callback, follow_redirects=False).status_code == 400
    conn = client.get("/api/v1/integrations/gmail").json()["connection"]
    return client, conn, verified


def mail():
    import base64

    return gmail.parse_message(
        {
            "id": "m1",
            "threadId": "t1",
            "internalDate": "1794700800000",
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Subject", "value": "화면 이름 변경 요청"}],
                "body": {
                    "data": base64.urlsafe_b64encode(
                        "화면 이름을 고객 재고로 바꿔주세요.".encode()
                    ).decode()
                },
            },
        }
    )


def collect(connected, pool, settings, monkeypatch):
    client, connection, _ = connected
    monkeypatch.setattr(gmail, "collect", lambda *a: ([mail()], "12345678901234567890", False))
    url = "/api/v1/integrations/gmail/" + connection["id"] + "/sync"
    first = client.post(url, headers=headers(client))
    assert first.status_code == 202, first.text
    assert client.post(url, headers=headers(client)).json()["id"] == first.json()["id"]
    assert worker.run_once(pool, settings)
    listing = client.get("/api/v1/feedback").json()
    assert len(listing["items"]) == 1
    return listing["items"][0]


def adopted(verified):
    client, url, _, payload = adoption_review(verified)
    result = client.post(url + "/adoptions", json=payload, headers=headers(client))
    assert result.status_code == 200, result.text
    return result.json()


def request_change(connected, pool, settings, monkeypatch):
    client, _, verified = connected
    baseline = adopted(verified)
    msg = collect(connected, pool, settings, monkeypatch)
    response = client.post(
        "/api/v1/feedback/" + msg["id"] + "/changes",
        headers=headers(client),
        json={
            "project_id": baseline["project_id"],
            "request_key": str(uuid4()),
            "title": "재고 화면 이름",
            "quote": mail()["body"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def suggested(verified):
    screen = verified[0][1]["bundle"]["screens"][0]
    return analysis.Analysis(
        summary="고객 요청에 따라 화면 이름 수정",
        quotes=[mail()["body"]],
        requests=["화면 이름 변경"],
        questions=[],
        unsupported=[],
        suggestions=[
            analysis.Suggestion(
                section="screens",
                object_id=screen["id"],
                field="name",
                value_json='"고객 재고"',
                rationale="고객 원문 요청",
            )
        ],
    )


def test_gmail_tokens_ownership_sync_and_disconnect(connected, pool, settings, monkeypatch):
    client, connection, _ = connected
    msg = collect(connected, pool, settings, monkeypatch)
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM gmail_connection").fetchone()
        assert "refresh-secret" not in row["encrypted_token"]
        assert gmail.unseal(settings, row["encrypted_token"]) == "refresh-secret"
        assert row["history_id"] == "12345678901234567890"
    assert "refresh-secret" not in client.get("/api/v1/integrations/gmail").text
    other = TestClient(create_app(settings, pool))
    login(other, monkeypatch, "other")
    assert other.get("/api/v1/feedback/" + msg["id"]).status_code == 404
    assert (
        other.post(
            "/api/v1/integrations/gmail/" + connection["id"] + "/sync", headers=headers(other)
        ).status_code
        == 404
    )
    assert client.delete("/api/v1/integrations/gmail/" + connection["id"]).status_code == 403
    result = client.delete(
        "/api/v1/integrations/gmail/" + connection["id"], headers=headers(client)
    )
    assert result.json()["state"] == "disconnected"
    assert (
        client.post(
            "/api/v1/integrations/gmail/" + connection["id"] + "/sync", headers=headers(client)
        ).status_code
        == 409
    )
    with pool.connection() as conn:
        assert (
            conn.execute("SELECT encrypted_token FROM gmail_connection").fetchone()[
                "encrypted_token"
            ]
            is None
        )


def test_feedback_review_approval_implementation(connected, pool, settings, monkeypatch):
    client, _, verified = connected
    row = request_change(connected, pool, settings, monkeypatch)
    root = "/api/v1/changes/" + row["id"]
    proposal = suggested(verified).model_dump(mode="json")
    response = client.put(
        root + "/proposal",
        headers=headers(client),
        json={"expected_version": row["version"], "analysis": proposal},
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["state"] == "awaiting_decision"
    assert (
        client.post(
            root + "/implement", headers=headers(client), json={"expected_version": row["version"]}
        ).status_code
        == 409
    )
    decision = client.post(
        root + "/decide",
        headers=headers(client),
        json={
            "expected_version": row["version"],
            "target_hash": row["proposal_hash"],
            "decision": "approve",
            "note": "고객 요청 및 실행 변경 범위를 확인합니다.",
            "acknowledge_unverified_acceptance": True,
        },
    )
    assert decision.status_code == 200, decision.text
    row = decision.json()
    result = client.post(
        root + "/implement", headers=headers(client), json={"expected_version": row["version"]}
    )
    assert result.status_code == 200, result.text
    implemented = result.json()
    assert implemented["state"] == "validating" and implemented["implementation_id"]
    assert (
        client.post(
            root + "/implement", headers=headers(client), json={"expected_version": row["version"]}
        ).json()["implementation_id"]
        == implemented["implementation_id"]
    )
    spec = client.get("/api/v1/specs/" + row["spec_id"]).json()
    assert spec["bundle"]["screens"][0]["name"] == "고객 재고"
    assert spec["status"] == "approved"


def test_sync_fencing_and_retry(connected, pool, settings, monkeypatch):
    client, connection, _ = connected
    url = "/api/v1/integrations/gmail/" + connection["id"]
    client.post(url + "/sync", headers=headers(client))
    with pool.connection() as conn:
        job = jobs.claim(conn)
    client.patch(
        url,
        headers=headers(client),
        json={"query": "from:customer@example.com", "automatic": False},
    )
    monkeypatch.setattr(gmail, "collect", lambda *a: ([mail()], "100", False))
    with pytest.raises(gmail.GmailError):
        worker.sync(pool, settings, job)
    assert client.get("/api/v1/feedback").json()["items"] == []
    client.post(url + "/sync", headers=headers(client))

    def retry(*args):
        raise gmail.GmailError("gmail_temporarily_unavailable", True, 120)

    monkeypatch.setattr(gmail, "collect", retry)
    assert worker.run_once(pool, settings)
    assert client.get("/api/v1/feedback-jobs").json()[0]["state"] == "queued"


def test_analysis_consent_and_erasure_fences_publication(connected, pool, settings, monkeypatch):

    client, _, verified = connected
    settings.openai_api_key = SecretStr("test-key")
    row = request_change(connected, pool, settings, monkeypatch)
    root = "/api/v1/changes/" + row["id"]
    assert (
        client.post(
            root + "/analyse",
            headers=headers(client),
            json={"expected_version": row["version"], "consent_external_analysis": False},
        ).status_code
        == 422
    )
    queued = client.post(
        root + "/analyse",
        headers=headers(client),
        json={"expected_version": row["version"], "consent_external_analysis": True},
    )
    assert queued.status_code == 202, queued.text
    monkeypatch.setattr(analysis, "run", lambda *a: (suggested(verified), []))
    assert worker.run_once(pool, settings)
    analysed = client.get(root).json()
    assert analysed["state"] == "awaiting_decision", analysed
    assert (
        client.delete("/api/v1/feedback/" + row["message_id"], headers=headers(client)).status_code
        == 200
    )
    assert client.get(root).json()["quote"] == ""
    assert client.get("/api/v1/feedback").json()["items"] == []
    collect_url = "/api/v1/integrations/gmail/" + connected[1]["id"] + "/sync"
    client.post(collect_url, headers=headers(client))
    assert worker.run_once(pool, settings)
    assert client.get("/api/v1/feedback").json()["items"] == []


def test_feedback_stale_spec_and_unsupported_change(connected, pool, settings, monkeypatch):
    from test_specifications import edit

    client, _, verified = connected
    row = request_change(connected, pool, settings, monkeypatch)
    root = "/api/v1/changes/" + row["id"]
    proposal = suggested(verified).model_dump(mode="json")
    proposal["unsupported"] = ["새 테이블은 별도 설계가 필요합니다."]
    saved = client.put(
        root + "/proposal",
        headers=headers(client),
        json={"expected_version": row["version"], "analysis": proposal},
    ).json()
    assert saved["state"] == "needs_input"
    assert (
        client.post(
            root + "/decide",
            headers=headers(client),
            json={
                "expected_version": saved["version"],
                "target_hash": saved["proposal_hash"],
                "decision": "approve",
                "note": "아직 추가 설계가 필요한 요청입니다.",
                "acknowledge_unverified_acceptance": True,
            },
        ).status_code
        == 409
    )
    spec = client.get("/api/v1/specs/" + row["spec_id"]).json()
    spec["bundle"]["screens"][0]["name"] = "다른 변경"
    assert edit(client, spec, spec["bundle"]).status_code == 200
    assert (
        client.put(
            root + "/proposal",
            headers=headers(client),
            json={"expected_version": saved["version"], "analysis": proposal},
        ).status_code
        == 409
    )


def test_disconnect_during_oauth_exchange_cannot_reconnect(connected, settings, monkeypatch):
    client, connection, _ = connected
    start = client.post("/api/v1/integrations/gmail/connect", headers=headers(client)).json()
    state = parse_qs(urlsplit(start["url"]).query)["state"][0]

    def racing(*args):
        assert (
            client.delete(
                "/api/v1/integrations/gmail/" + connection["id"], headers=headers(client)
            ).status_code
            == 200
        )
        return GoogleIdentity("one", "one@example.com"), "new-token"

    monkeypatch.setattr(gmail, "exchange", racing)
    response = client.get(
        gmail.CALLBACK, params={"state": state, "code": "test"}, follow_redirects=False
    )
    assert response.headers["location"].endswith("failed")
    assert client.get("/api/v1/integrations/gmail").json()["connection"]["state"] == "disconnected"


def test_analysis_lease_expiry_is_not_retried_automatically(connected, pool, settings, monkeypatch):
    client, _, _ = connected
    settings.openai_api_key = SecretStr("test-key")
    row = request_change(connected, pool, settings, monkeypatch)
    root = "/api/v1/changes/" + row["id"]
    client.post(
        root + "/analyse",
        headers=headers(client),
        json={"expected_version": row["version"], "consent_external_analysis": True},
    )
    with pool.connection() as conn:
        job = jobs.claim(conn)
        conn.execute(
            "UPDATE feedback_job SET lease_until=now()-interval '1 second' WHERE id=%s",
            (job["id"],),
        )
        assert jobs.claim(conn) is None
        assert not jobs.fenced(conn, job)
    assert client.get(root).json()["state"] == "failed"
