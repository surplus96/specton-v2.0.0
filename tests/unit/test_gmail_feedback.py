import base64
import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from specton.api.access_log import OAuthQueryFilter
from specton.config import Settings
from specton.integrations import gmail


def settings():
    return Settings(
        _env_file=None,
        google_client_id="client",
        google_client_secret="secret",
        gmail_token_key=Fernet.generate_key().decode(),
    )


def test_gmail_oauth_scope_pkce_and_encryption():
    config = settings()
    query = parse_qs(urlsplit(gmail.authorization_url(config, "state", "nonce", "verifier")).query)
    assert query["scope"] == ["openid email " + gmail.SCOPE]
    assert query["access_type"] == ["offline"] and query["code_challenge_method"] == ["S256"]
    encrypted = gmail.seal(config, "private-refresh")
    assert gmail.unseal(config, encrypted) == "private-refresh"
    with pytest.raises(gmail.GmailError, match="unreadable"):
        gmail.unseal(settings(), encrypted)


def test_html_mail_is_text_only_and_attachments_not_read():
    body = '<p>변경 요청</p><script>steal()</script><img src="https://tracker.invalid"><b>화면</b>'
    parsed = gmail.parse_message(
        {
            "id": "m",
            "internalDate": "1794700800000",
            "payload": {
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
                    },
                    {
                        "mimeType": "text/plain",
                        "filename": "secret.txt",
                        "body": {"size": 5, "data": "bad"},
                    },
                ],
            },
        }
    )
    assert "변경 요청" in parsed["body"] and "화면" in parsed["body"]
    assert "steal" not in parsed["body"] and "tracker" not in parsed["body"]
    assert parsed["attachments"][0]["name"] == "secret.txt"


@pytest.mark.parametrize(
    ("status", "payload", "code", "retry"),
    [
        (400, {"error": "invalid_grant"}, "gmail_reauth_required", False),
        (401, {}, "gmail_reauth_required", False),
        (403, {}, "gmail_access_denied", False),
        (429, {}, "gmail_temporarily_unavailable", True),
        (503, {}, "gmail_temporarily_unavailable", True),
    ],
)
def test_provider_failure_classification(status, payload, code, retry):
    with pytest.raises(gmail.GmailError) as caught:
        gmail.response_json(httpx.Response(status, json=payload))
    assert caught.value.code == code and caught.value.retryable is retry


def test_callback_access_log_redacts_code_state():
    path = gmail.CALLBACK + "?code=secret&state=private"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        "%s %s %s %s %s",
        ("remote", "GET", path, "1.1", 303),
        None,
    )
    OAuthQueryFilter().filter(record)
    assert "secret" not in record.getMessage() and "private" not in record.getMessage()


def test_collect_pages_history_recovery_and_known_ids(monkeypatch):
    seen = []
    client_class = httpx.Client

    def handler(request):
        seen.append(str(request.url))
        path = request.url.path
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "90071992547409931234"})
        if path.endswith("/history"):
            return httpx.Response(404, json={})
        if path.endswith("/messages"):
            assert "-in:drafts" in request.url.params["q"]
            if "pageToken" not in request.url.params:
                return httpx.Response(
                    200, json={"messages": [{"id": "known"}], "nextPageToken": "p2"}
                )
            return httpx.Response(200, json={"messages": [{"id": "new"}]})
        assert path.endswith("/messages/new")
        return httpx.Response(
            200, json={"id": "new", "internalDate": "1794700800000", "payload": {}}
        )

    monkeypatch.setattr(
        gmail.httpx,
        "Client",
        lambda **kw: client_class(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(gmail, "access_token", lambda *a: "access")
    messages, history, recovered = gmail.collect(
        settings(),
        {
            "encrypted_token": "cipher",
            "query": "newer_than:30d",
            "history_id": "1",
            "known_ids": {"known"},
        },
    )
    assert recovered and history == "90071992547409931234"
    assert [m["gmail_id"] for m in messages] == ["new"]
    assert len(seen) == 5


def test_collect_refuses_truncation_at_500(monkeypatch):
    client_class = httpx.Client

    def handler(request):
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        return httpx.Response(
            200, json={"messages": [{"id": str(i)} for i in range(100)], "nextPageToken": "more"}
        )

    monkeypatch.setattr(
        gmail.httpx,
        "Client",
        lambda **kw: client_class(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(gmail, "access_token", lambda *a: "access")
    with pytest.raises(gmail.GmailError, match="filter_too_broad"):
        gmail.collect(settings(), {"encrypted_token": "x", "query": "in:anywhere"})
