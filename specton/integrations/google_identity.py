"""Google OIDC 서명 검증과 authorization code 교환. Gmail 권한은 요청하지 않는다."""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

_KEYS = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", timeout=10)


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str


def authorization_url(
    client_id: str, redirect_uri: str, state: str, nonce: str, verifier: str
) -> str:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )


def verify_identity(token: str, client_id: str, nonce: str) -> GoogleIdentity:
    key = _KEYS.get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=["https://accounts.google.com", "accounts.google.com"],
        options={"require": ["exp", "iat", "sub", "aud", "iss", "nonce"]},
    )
    if not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"], nonce):
        raise ValueError("Google nonce mismatch")
    if claims.get("azp", client_id) != client_id or claims.get("email_verified") is not True:
        raise ValueError("Google identity not verified")
    subject, email = claims["sub"], claims.get("email")
    if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
        raise ValueError("Google identity is incomplete")
    return GoogleIdentity(subject, email)


def exchange_code(
    *, code: str, client_id: str, client_secret: str, redirect_uri: str, verifier: str, nonce: str
) -> GoogleIdentity:
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
        response.raise_for_status()
        token = response.json().get("id_token")
    if not isinstance(token, str):
        raise ValueError("Google ID token missing")
    return verify_identity(token, client_id, nonce)
