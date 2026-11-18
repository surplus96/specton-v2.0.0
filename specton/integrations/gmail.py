"""Read-only Gmail transport. Secrets never appear in URLs, logs or public errors."""

import base64
import hashlib
import json
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from cryptography.fernet import Fernet

from specton.config import Settings
from specton.integrations import google_identity

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALLBACK = "/api/v1/integrations/gmail/callback"


class GmailError(Exception):
    def __init__(self, code: str, retryable: bool = False, retry_after: int = 0):
        super().__init__(code)
        self.code, self.retryable, self.retry_after = code, retryable, retry_after


def cipher(settings: Settings) -> Fernet:
    if not settings.gmail_token_key:
        raise GmailError("gmail_key_missing")
    try:
        return Fernet(settings.gmail_token_key.get_secret_value().encode())
    except ValueError:
        raise GmailError("gmail_key_invalid") from None


def seal(settings: Settings, token: str) -> str:
    return cipher(settings).encrypt(token.encode()).decode()


def unseal(settings: Settings, encrypted: str) -> str:
    try:
        return cipher(settings).decrypt(encrypted.encode()).decode()
    except Exception:
        raise GmailError("gmail_token_unreadable") from None


def authorization_url(settings: Settings, state: str, nonce: str, verifier: str) -> str:
    cipher(settings)
    if not settings.google_client_id or not settings.google_client_secret:
        raise GmailError("google_config_missing")
    url = google_identity.authorization_url(
        settings.google_client_id,
        settings.public_origin.rstrip("/") + CALLBACK,
        state,
        nonce,
        verifier,
    )
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update(
        scope="openid email " + SCOPE, access_type="offline", prompt="consent select_account"
    )
    return urlunsplit(parts._replace(query=urlencode(query)))


def response_json(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 429 or response.status_code >= 500:
        retry = response.headers.get("retry-after", "")
        raise GmailError(
            "gmail_temporarily_unavailable", True, min(int(retry), 3600) if retry.isdigit() else 0
        )
    if response.status_code == 401:
        raise GmailError("gmail_reauth_required")
    if response.status_code == 404:
        raise GmailError("gmail_not_found")
    if response.status_code >= 400:
        try:
            if response.json().get("error") == "invalid_grant":
                raise GmailError("gmail_reauth_required")
        except (ValueError, AttributeError):
            pass
        raise GmailError("gmail_access_denied")
    if len(response.content) > 8 * 1024 * 1024:
        raise GmailError("gmail_message_too_large")
    data = response.json()
    if not isinstance(data, dict):
        raise GmailError("gmail_invalid_response")
    return data


def exchange(settings: Settings, code: str, nonce: str, verifier: str) -> tuple[Any, str | None]:
    assert settings.google_client_secret and settings.google_client_id
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        data = response_json(
            client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret.get_secret_value(),
                    "redirect_uri": settings.public_origin.rstrip("/") + CALLBACK,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
        )
    identity = google_identity.verify_identity(data["id_token"], settings.google_client_id, nonce)
    if SCOPE not in data.get("scope", "").split():
        raise GmailError("gmail_consent_required")
    return identity, str(data["refresh_token"]) if data.get("refresh_token") else None


def access_token(settings: Settings, encrypted: str) -> str:
    assert settings.google_client_secret and settings.google_client_id
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        data = response_json(
            client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret.get_secret_value(),
                    "refresh_token": unseal(settings, encrypted),
                    "grant_type": "refresh_token",
                },
            )
        )
    if not isinstance(data.get("access_token"), str):
        raise GmailError("gmail_invalid_response")
    return str(data["access_token"])


def revoke(settings: Settings, encrypted: str) -> bool:
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(
                "https://oauth2.googleapis.com/revoke", data={"token": unseal(settings, encrypted)}
            )
        return response.status_code in (200, 400)
    except Exception:
        return False


class TextHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag in ("br", "p", "div", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def parse_message(data: dict[str, Any]) -> dict[str, Any]:
    plain: list[str] = []
    html: list[str] = []
    attachments = []
    count = 0

    def visit(part: dict[str, Any], depth: int = 0) -> None:
        nonlocal count
        count += 1
        if depth > 20 or count > 200:
            raise GmailError("gmail_mime_limit")
        if part.get("filename"):
            attachments.append(
                {
                    "name": str(part["filename"])[:250],
                    "mime_type": str(part.get("mimeType", ""))[:100],
                    "size": part.get("body", {}).get("size", 0),
                }
            )
            return
        encoded = part.get("body", {}).get("data")
        if encoded and part.get("mimeType") in ("text/plain", "text/html"):
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            if len(raw) > 200000:
                raise GmailError("gmail_body_limit")
            # Gmail payload headers retain the declared MIME charset.
            from email.message import Message

            mime = Message()
            for h in part.get("headers", []):
                if h.get("name", "").lower() == "content-type":
                    mime["Content-Type"] = h["value"]
            try:
                value = raw.decode(mime.get_content_charset() or "utf-8", errors="replace")
            except LookupError:
                value = raw.decode("utf-8", errors="replace")
            (plain if part["mimeType"] == "text/plain" else html).append(value)
        for child in part.get("parts", []):
            visit(child, depth + 1)

    payload = data.get("payload", {})
    visit(payload)
    if plain:
        body = "\n".join(plain)
    else:
        parser = TextHTML()
        parser.feed("\n".join(html))
        body = "".join(parser.parts)
    if len(body) > 100000:
        raise GmailError("gmail_body_limit")
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    return {
        "gmail_id": data["id"],
        "thread_id": data.get("threadId", data["id"]),
        "subject": headers.get("subject", "")[:1000],
        "sender": headers.get("from", "")[:1000],
        "received_at": datetime.fromtimestamp(int(data["internalDate"]) / 1000, UTC),
        "body": body,
        "attachments": attachments,
        "content_hash": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
    }


def collect(
    settings: Settings, connection: dict[str, Any]
) -> tuple[list[dict[str, Any]], str, bool]:
    """All pages or no cursor advancement. Initial >500 requires a narrower collection filter."""
    token = access_token(settings, connection["encrypted_token"])
    started = time.monotonic()
    with httpx.Client(
        timeout=20, follow_redirects=False, headers={"Authorization": "Bearer " + token}
    ) as client:

        def get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            if time.monotonic() - started > 180:
                raise GmailError("gmail_sync_timeout", True)
            return response_json(
                client.get("https://gmail.googleapis.com/gmail/v1/users/me/" + path, params=params)
            )

        # Capture before scanning; changes during the scan are replayed on the next sync.
        profile = get("profile")
        start = connection.get("history_id")
        recovered = False
        if start:
            try:
                page = get("history", {"startHistoryId": start, "maxResults": 100})
                for _ in range(100):
                    if not page.get("nextPageToken"):
                        break
                    page = get(
                        "history",
                        {
                            "startHistoryId": start,
                            "maxResults": 100,
                            "pageToken": page["nextPageToken"],
                        },
                    )
                else:
                    raise GmailError("gmail_history_limit")
            except GmailError as exc:
                if exc.code != "gmail_not_found":
                    raise
                recovered = True
        # Reconcile the bounded query on every poll, including labels changed/removed in Gmail.
        # Existing collected messages remain historical evidence until explicit deletion/retention.
        ids: list[str] = []
        next_page = None
        while True:
            params = {"q": "(" + connection["query"] + ") -in:drafts", "maxResults": 100}
            if next_page:
                params["pageToken"] = next_page
            page = get("messages", params)
            ids.extend(item["id"] for item in page.get("messages", []))
            next_page = page.get("nextPageToken")
            if len(ids) > 500 or (len(ids) >= 500 and next_page):
                raise GmailError("gmail_filter_too_broad")
            if not next_page:
                break
        messages = []
        for mid in dict.fromkeys(ids):
            if mid in connection.get("known_ids", set()):
                continue
            try:
                messages.append(parse_message(get("messages/" + mid, {"format": "full"})))
            except GmailError as exc:
                if exc.code != "gmail_not_found":  # Deleted between list and get.
                    raise
        return messages, str(profile["historyId"]), recovered
