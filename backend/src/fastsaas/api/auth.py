"""HTTP endpoints for the identity layer.

Routes are intentionally thin — service-level errors carry `(code, status_code)`
and we translate them to `HTTPException`. The refresh cookie is the one piece
of session state that flows through cookies; everything else is JSON in/out.

`X-Refresh: 1` is required on `POST /auth/refresh` per ADR-008 §8b — a
custom-header CSRF defense that browsers can't preflight without CORS opt-in.

Email side effects piggy-back on `BackgroundTasks`, which run AFTER the
session-scoped transaction has committed; we never email out for a request
whose DB write failed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse

from fastsaas.config import get_settings
from fastsaas.identity import email as email_service
from fastsaas.identity import service
from fastsaas.identity.auth import oauth as oauth_module
from fastsaas.identity.middleware import (
    CurrentActorDep,
    SessionDep,
)
from fastsaas.identity.schemas import (
    CurrentActor,
    LoginRequest,
    MagicLinkConsumeBody,
    MagicLinkRequestBody,
    PasswordResetConsumeBody,
    PasswordResetRequestBody,
    RegisterRequest,
    RegisterResponse,
    TokensResponse,
    VerifyEmailBody,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/auth"
REFRESH_MAX_AGE = 30 * 24 * 3600  # 30 days

PKCE_COOKIE = "oauth_pkce"
PKCE_PATH = "/auth"
PKCE_MAX_AGE = 10 * 60


def _service_error_to_http(exc: service.AuthServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc) or exc.code},
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.env != "dev",
        samesite="lax",
        path=REFRESH_PATH,
        max_age=REFRESH_MAX_AGE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value="",
        httponly=True,
        secure=settings.env != "dev",
        samesite="lax",
        path=REFRESH_PATH,
        max_age=0,
    )


def _set_pkce_cookie(response: Response, verifier: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=PKCE_COOKIE,
        value=verifier,
        httponly=True,
        secure=settings.env != "dev",
        samesite="lax",
        path=PKCE_PATH,
        max_age=PKCE_MAX_AGE,
    )


def _clear_pkce_cookie(response: Response) -> None:
    settings = get_settings()
    response.set_cookie(
        key=PKCE_COOKIE,
        value="",
        httponly=True,
        secure=settings.env != "dev",
        samesite="lax",
        path=PKCE_PATH,
        max_age=0,
    )


def _resolve_provider(name: str) -> oauth_module.OIDCProvider:
    if name == "google":
        return oauth_module.google_provider()
    if name == "microsoft":
        return oauth_module.microsoft_provider()
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "auth.oauth_provider_unknown", "message": f"unknown provider {name!r}"},
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
)
async def register(
    body: RegisterRequest, session: SessionDep, background: BackgroundTasks
) -> RegisterResponse:
    try:
        actor, raw_token = await service.register_user(
            session, email=body.email, password=body.password
        )
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    background.add_task(email_service.send_verification, body.email, raw_token)
    return RegisterResponse(actor_id=actor.id, email=body.email, email_verified=False)


@router.post("/verify-email")
async def verify_email(body: VerifyEmailBody, session: SessionDep) -> dict:
    try:
        await service.verify_email(session, raw_token=body.token)
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    return {"status": "verified"}


@router.post("/login", response_model=TokensResponse)
async def login(
    body: LoginRequest, session: SessionDep, response: Response
) -> TokensResponse:
    try:
        issued = await service.login_with_password(
            session, email=body.email, password=body.password
        )
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    _set_refresh_cookie(response, issued.refresh_token)
    return TokensResponse(access_token=issued.access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    if refresh_token:
        await service.logout(refresh_token)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/refresh", response_model=TokensResponse)
async def refresh(
    session: SessionDep,
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    x_refresh: Annotated[str | None, Header(alias="X-Refresh")] = None,
) -> TokensResponse:
    if x_refresh != "1":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "auth.refresh_missing_header",
                "message": "X-Refresh: 1 header is required",
            },
        )
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "auth.token_missing", "message": "no refresh cookie"},
        )
    try:
        issued = await service.refresh_session(session, refresh_token=refresh_token)
    except service.AuthServiceError as e:
        if isinstance(e, (service.RefreshReusedApiError, service.RefreshUnknownApiError)):
            _clear_refresh_cookie(response)
        raise _service_error_to_http(e) from e
    _set_refresh_cookie(response, issued.refresh_token)
    return TokensResponse(access_token=issued.access_token)


@router.post("/magic-link/request", status_code=status.HTTP_202_ACCEPTED)
async def request_magic_link(
    body: MagicLinkRequestBody, session: SessionDep, background: BackgroundTasks
) -> dict:
    try:
        raw = await service.request_magic_link(session, email=body.email)
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    if raw is not None:
        background.add_task(email_service.send_magic_link, body.email, raw)
    return {"status": "accepted"}


@router.post("/magic-link/consume", response_model=TokensResponse)
async def consume_magic_link(
    body: MagicLinkConsumeBody, session: SessionDep, response: Response
) -> TokensResponse:
    try:
        issued = await service.login_with_magic_link(session, raw_token=body.token)
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    _set_refresh_cookie(response, issued.refresh_token)
    return TokensResponse(access_token=issued.access_token)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    body: PasswordResetRequestBody, session: SessionDep, background: BackgroundTasks
) -> dict:
    try:
        raw = await service.request_password_reset(session, email=body.email)
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    if raw is not None:
        background.add_task(email_service.send_password_reset, body.email, raw)
    return {"status": "accepted"}


@router.post("/password-reset/consume")
async def consume_password_reset(
    body: PasswordResetConsumeBody, session: SessionDep
) -> dict:
    try:
        await service.complete_password_reset(
            session, raw_token=body.token, new_password=body.password
        )
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    return {"status": "reset"}


@router.get("/me", response_model=CurrentActor)
async def me(actor: CurrentActorDep) -> CurrentActor:
    return actor


@router.get("/oauth/dev/start", response_model=TokensResponse)
async def oauth_dev_start(
    session: SessionDep, response: Response, email: str, redirect_to: str = "/"
) -> TokensResponse:
    """Dev-only short-circuit: skip the provider round-trip, log in by email.

    Returns 404 unless `OAUTH_DEV_BYPASS=true` so it cannot be enabled by accident.
    Declared BEFORE `/oauth/{provider}/start` so FastAPI's prefix-matched router
    resolves `/oauth/dev/start` here rather than treating "dev" as a provider name.
    """
    settings = get_settings()
    if not settings.oauth_dev_bypass:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    claims = oauth_module.OAuthIdentityClaims(
        provider="dev",
        provider_uid=f"dev:{email}",
        email=email,
        email_verified=True,
        redirect_to=redirect_to,
    )
    try:
        issued = await service.complete_oauth(session, claims=claims)
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e
    _set_refresh_cookie(response, issued.refresh_token)
    return TokensResponse(access_token=issued.access_token)


@router.get("/oauth/{provider}/start")
async def oauth_start(
    provider: str, request: Request, redirect_to: str = "/"
) -> Response:
    p = _resolve_provider(provider)
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    authorize_url, _, code_verifier = await p.start(
        redirect_uri=redirect_uri, redirect_to=redirect_to
    )
    response = RedirectResponse(
        authorize_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    _set_pkce_cookie(response, code_verifier)
    return response


@router.get("/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: str,
    request: Request,
    session: SessionDep,
    response: Response,
    code: str,
    state: str,
    pkce: Annotated[str | None, Cookie(alias=PKCE_COOKIE)] = None,
) -> TokensResponse:
    if pkce is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "auth.oauth_pkce_missing", "message": "PKCE cookie absent"},
        )
    p = _resolve_provider(provider)
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    try:
        identity = await p.complete(
            code=code,
            state_token=state,
            code_verifier=pkce,
            redirect_uri=redirect_uri,
        )
        issued = await service.complete_oauth(session, claims=identity)
    except oauth_module.OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": e.code, "message": str(e)},
        ) from e
    except service.AuthServiceError as e:
        raise _service_error_to_http(e) from e

    _clear_pkce_cookie(response)
    _set_refresh_cookie(response, issued.refresh_token)
    return TokensResponse(access_token=issued.access_token)
