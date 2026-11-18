"""Google 로그인과 서버 저장 세션. 외부 토큰은 저장하거나 브라우저에 반환하지 않는다."""

import hashlib
import secrets
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from specton.api.deps import ConnDep, SettingsDep
from specton.integrations.google_identity import authorization_url, exchange_code

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])
COOKIE = "specton_login"
CSRF = "specton_csrf"
BROWSER = "specton_oauth"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def current_user(request: Request, conn: ConnDep) -> dict[str, Any]:
    token = request.cookies.get(COOKIE, "")
    row = (
        conn.execute(
            "SELECT u.id,u.email,s.csrf_hash FROM login_session s "
            "JOIN app_user u ON u.id=s.user_id "
            "WHERE s.token_hash=%s AND s.expires_at>now()",
            (digest(token),),
        ).fetchone()
        if token
        else None
    )
    if row is None:
        raise HTTPException(401, "로그인이 필요합니다")
    return row


UserDep = Annotated[dict[str, Any], Depends(current_user)]


def mutation(request: Request, user: UserDep, settings: SettingsDep) -> None:
    if request.headers.get("origin") != settings.public_origin.rstrip("/"):
        raise HTTPException(403, "요청 출처가 일치하지 않습니다")
    token = request.headers.get("x-csrf-token", "")
    if not token or not secrets.compare_digest(digest(token), user["csrf_hash"]):
        raise HTTPException(403, "요청 확인 토큰이 일치하지 않습니다")


Mutation = Annotated[None, Depends(mutation)]


@router.get("/google", operation_id="googleLogin", status_code=302)
def google_login(conn: ConnDep, settings: SettingsDep) -> RedirectResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(503, "Google 로그인 설정이 필요합니다")
    state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    conn.execute("DELETE FROM oauth_attempt WHERE expires_at<=now()")
    conn.execute(
        "INSERT INTO oauth_attempt VALUES(%s,%s,%s,%s,now()+interval '10 minutes')",
        (digest(state), digest(browser), nonce, verifier),
    )
    url = authorization_url(
        settings.google_client_id,
        settings.public_origin.rstrip("/") + "/api/v1/auth/google/callback",
        state,
        nonce,
        verifier,
    )
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        BROWSER,
        browser,
        max_age=600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/google/callback", operation_id="googleCallback", status_code=303)
def callback(
    request: Request, conn: ConnDep, settings: SettingsDep, state: str = "", code: str = ""
) -> RedirectResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(503, "Google 로그인 설정이 필요합니다")
    attempt = conn.execute(
        "DELETE FROM oauth_attempt WHERE state_hash=%s AND browser_hash=%s "
        "AND expires_at>now() RETURNING nonce,verifier",
        (digest(state), digest(request.cookies.get(BROWSER, ""))),
    ).fetchone()
    if attempt is None or not code:
        raise HTTPException(400, "로그인 요청이 만료됐거나 일치하지 않습니다")
    try:
        identity = exchange_code(
            code=code,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret.get_secret_value(),
            redirect_uri=settings.public_origin.rstrip("/") + "/api/v1/auth/google/callback",
            verifier=attempt["verifier"],
            nonce=attempt["nonce"],
        )
    except Exception:
        raise HTTPException(401, "Google 로그인을 확인할 수 없습니다. 다시 시작하세요") from None
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with conn.transaction():
        user = conn.execute(
            "INSERT INTO app_user(id,google_subject,email) VALUES(%s,%s,%s) "
            "ON CONFLICT(google_subject) DO UPDATE SET email=excluded.email RETURNING id",
            (uuid4(), identity.subject, identity.email),
        ).fetchone()
        assert user is not None
        conn.execute(
            "DELETE FROM login_session WHERE token_hash=%s OR expires_at<=now()",
            (digest(request.cookies.get(COOKIE, "")),),
        )
        conn.execute(
            "INSERT INTO login_session VALUES(%s,%s,%s,now()+%s*interval '1 day')",
            (digest(token), user["id"], digest(csrf), settings.login_days),
        )
    response = RedirectResponse("/projects", status_code=303)
    for key, value, hidden in ((COOKIE, token, True), (CSRF, csrf, False)):
        response.set_cookie(
            key,
            value,
            max_age=settings.login_days * 86400,
            httponly=hidden,
            secure=settings.session_cookie_secure,
            samesite="lax",
        )
    response.delete_cookie(BROWSER)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/me", operation_id="currentUser")
def me(user: UserDep, response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    return {"id": str(user["id"]), "email": user["email"]}


@router.post("/logout", operation_id="logout", status_code=204)
def logout(request: Request, conn: ConnDep, response: Response, checked: Mutation) -> None:
    conn.execute(
        "DELETE FROM login_session WHERE token_hash=%s", (digest(request.cookies.get(COOKIE, "")),)
    )
    for name in (COOKIE, CSRF, BROWSER, "specton_session"):
        response.delete_cookie(name)
