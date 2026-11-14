"""Google OAuth 자체는 고정 응답, 세션·프로젝트·승인 연결은 실제 DB로 검증한다."""

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_scripted_flow import _Flow, _to_final_review

from specton.api import auth
from specton.api.main import create_app
from specton.config import Settings
from specton.integrations.google_identity import GoogleIdentity
from specton.persistence.runs import create_run

pytestmark = pytest.mark.db
ORIGIN = "http://localhost:5173"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        google_client_id="test-client",
        google_client_secret="test-secret",
        storage_dir=tmp_path,
        public_origin=ORIGIN,
        runner_poll_seconds=0.05,
    )


def login(client, monkeypatch, subject="one"):
    monkeypatch.setattr(
        auth, "exchange_code", lambda **kw: GoogleIdentity(subject, subject + "@example.com")
    )
    start = client.get("/api/v1/auth/google", follow_redirects=False)
    assert start.status_code == 302
    query = parse_qs(urlsplit(start.headers["location"]).query)
    assert query["scope"] == ["openid email"] and query["code_challenge_method"] == ["S256"]
    callback = "/api/v1/auth/google/callback?state=" + query["state"][0] + "&code=test"
    done = client.get(callback, follow_redirects=False)
    assert done.status_code == 303, done.text
    return callback


def headers(client):
    return {"origin": ORIGIN, "x-csrf-token": client.cookies.get(auth.CSRF)}


def test_google_state_is_browser_bound_single_use_and_session_is_revocable(
    pool, settings, monkeypatch
):
    a = TestClient(create_app(settings, pool))
    b = TestClient(create_app(settings, pool))
    start = a.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    assert (
        b.get("/api/v1/auth/google/callback", params={"state": state, "code": "x"}).status_code
        == 400
    )
    callback = login(a, monkeypatch)
    assert a.get(callback, follow_redirects=False).status_code == 400
    before = a.get("/api/v1/auth/me").json()["id"]
    old = a.cookies.get(auth.COOKIE)
    login(a, monkeypatch)
    assert a.get("/api/v1/auth/me").json()["id"] == before
    b.cookies.set(auth.COOKIE, old)
    assert b.get("/api/v1/auth/me").status_code == 401
    assert a.post("/api/v1/auth/logout").status_code == 403
    assert a.post("/api/v1/auth/logout", headers=headers(a)).status_code == 204
    assert a.get("/api/v1/auth/me").status_code == 401


def test_project_ownership_csrf_and_expiry(pool, settings, monkeypatch):
    a = TestClient(create_app(settings, pool))
    b = TestClient(create_app(settings, pool))
    assert a.post("/api/v1/projects", json={"name": "private"}).status_code == 401
    login(a, monkeypatch, "one")
    login(b, monkeypatch, "two")
    assert a.post("/api/v1/projects", json={"name": "private"}).status_code == 403
    project = a.post("/api/v1/projects", json={"name": "private"}, headers=headers(a)).json()["id"]
    assert b.get("/api/v1/projects").json() == []
    assert b.get("/api/v1/projects/" + project).status_code == 404
    with pool.connection() as conn:
        conn.execute("UPDATE login_session SET expires_at=now()-interval '1 second'")
    assert a.get("/api/v1/projects").status_code == 401


def test_claim_only_proven_legacy_owner_and_no_cross_project_move(pool, settings, monkeypatch):
    client = TestClient(create_app(settings, pool))
    login(client, monkeypatch)
    project = client.post("/api/v1/projects", json={"name": "one"}, headers=headers(client)).json()[
        "id"
    ]
    other = client.post("/api/v1/projects", json={"name": "two"}, headers=headers(client)).json()[
        "id"
    ]
    with pool.connection() as conn:
        run = create_run(conn, "A" * 43, "inventory").run_id
    url = f"/api/v1/projects/{project}/runs/{run}/claim"
    assert client.post(url, headers=headers(client)).status_code == 404
    client.cookies.set("specton_session", "A" * 43)
    assert client.post(url, headers=headers(client)).status_code == 200
    assert client.post(url, headers=headers(client)).status_code == 200
    assert (
        client.post(
            f"/api/v1/projects/{other}/runs/{run}/claim", headers=headers(client)
        ).status_code
        == 409
    )
    assert client.get(f"/runs/{run}").status_code == 200
    assert (
        client.post(
            f"/api/v1/projects/{project}/baselines",
            json={"run_id": str(run), "revision": 0},
            headers=headers(client),
        ).status_code
        == 422
    )


def test_actual_approved_design_connects_and_modified_bytes_are_rejected(
    pool, settings, monkeypatch
):
    flow = _Flow(pool, settings)
    flow.runner.start()
    try:
        run, current = _to_final_review(flow)
        assert (
            flow.resume(
                current, {"kind": "review", "decision": "approve", "feedback": ""}
            ).status_code
            == 202
        )
        done = flow.wait(run, state="completed")
        client = flow.client
        login(client, monkeypatch)
        project = client.post(
            "/api/v1/projects", json={"name": "inventory"}, headers=headers(client)
        ).json()["id"]
        assert (
            client.post(
                f"/api/v1/projects/{project}/runs/{run}/claim", headers=headers(client)
            ).status_code
            == 200
        )
        url = f"/api/v1/projects/{project}/baselines"
        payload = {"run_id": run, "revision": done["revision"]}
        first = client.post(url, json=payload, headers=headers(client))
        assert first.status_code == 201, first.text
        assert (
            client.post(url, json=payload, headers=headers(client)).json()["id"]
            == first.json()["id"]
        )
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT storage_ref FROM artifact a JOIN model_snapshot s USING(snapshot_id) "
                "WHERE s.run_id=%s AND a.kind='ddl'",
                (run,),
            ).fetchone()
        (settings.storage_dir / row["storage_ref"]).write_bytes(b"-- tampered")
        assert client.post(url, json=payload, headers=headers(client)).status_code == 422
        assert len(client.get("/api/v1/projects/" + project).json()["baselines"]) == 1
    finally:
        flow.runner.stop()
        flow.client.close()


def test_same_email_does_not_merge_google_subjects(pool, settings, monkeypatch):
    clients = [TestClient(create_app(settings, pool)) for _ in range(2)]
    ids = []
    for index, client in enumerate(clients):
        start = client.get("/api/v1/auth/google", follow_redirects=False)
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        identity = GoogleIdentity(str(index), "same@example.com")
        monkeypatch.setattr(auth, "exchange_code", lambda identity=identity, **kw: identity)
        result = client.get(
            "/api/v1/auth/google/callback",
            params={"state": state, "code": "test"},
            follow_redirects=False,
        )
        assert result.status_code == 303
        ids.append(client.get("/api/v1/auth/me").json()["id"])
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT token_hash FROM login_session WHERE user_id=%s", (ids[-1],)
            ).fetchone()
        assert row["token_hash"] != client.cookies.get(auth.COOKIE)
    assert ids[0] != ids[1]


def test_account_owner_id_cannot_be_used_as_legacy_session_proof(pool, settings, monkeypatch):
    victim = TestClient(create_app(settings, pool))
    attacker = TestClient(create_app(settings, pool))
    login(victim, monkeypatch, "victim")
    victim_id = victim.get("/api/v1/auth/me").json()["id"]
    login(attacker, monkeypatch, "attacker")
    project = attacker.post(
        "/api/v1/projects", json={"name": "attack"}, headers=headers(attacker)
    ).json()["id"]
    with pool.connection() as conn:
        run = create_run(conn, f"user:{victim_id}", "inventory").run_id
    attacker.cookies.set("specton_session", f"user:{victim_id}")
    assert (
        attacker.post(
            f"/api/v1/projects/{project}/runs/{run}/claim", headers=headers(attacker)
        ).status_code
        == 404
    )
    assert victim.get(f"/runs/{run}").status_code == 200
