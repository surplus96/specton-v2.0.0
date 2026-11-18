"""독립 RSA 키로 Google ID 토큰의 검증 조건을 시험한다. 네트워크 호출은 없다."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from specton.integrations import google_identity as google


@pytest.fixture
def signed(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        google._KEYS,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=key.public_key()),
    )

    def create(**changes):
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "stable-subject",
            "aud": "client",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "nonce": "nonce",
            "email": "user@example.com",
            "email_verified": True,
            **changes,
        }
        return jwt.encode(claims, key, algorithm="RS256")

    return create


def test_valid_google_subject_is_identity(signed):
    assert google.verify_identity(signed(), "client", "nonce").subject == "stable-subject"


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.test"},
        {"aud": "other"},
        {"exp": 0},
        {"nonce": "other"},
        {"email_verified": False},
        {"azp": "other"},
        {"sub": ""},
    ],
)
def test_wrong_identity_claims_are_rejected(signed, claims):
    with pytest.raises((ValueError, jwt.PyJWTError)):
        google.verify_identity(signed(**claims), "client", "nonce")


def test_modified_payload_signature_is_rejected(signed):
    import base64
    import json

    token = signed()
    header, body, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims["sub"] = "attacker"
    replacement = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    with pytest.raises(jwt.InvalidSignatureError):
        google.verify_identity(f"{header}.{replacement}.{signature}", "client", "nonce")
