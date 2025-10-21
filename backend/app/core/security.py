"""Security helpers for REST and WebSocket authentication."""

from __future__ import annotations

import base64
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings


class UserRole(StrEnum):
    PLAYER = "player"
    MODERATOR = "moderator"
    PARENT = "parent"


@dataclass
class AuthenticatedSubject:
    user_id: UUID
    role: UserRole


bearer_scheme = HTTPBearer(auto_error=False)


def _sign(message: str, secret: str) -> str:
    return hmac.new(secret.encode(), message.encode(), sha256).hexdigest()


def create_access_token(
    *,
    user_id: UUID,
    role: UserRole,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": str(user_id), "role": str(role), "exp": int(expire.timestamp())}
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    signature = _sign(encoded, settings.auth_secret_key)
    return f"{encoded}.{signature}"


def decode_token(token: str) -> AuthenticatedSubject:
    settings = get_settings()
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:  # pragma: no cover - invalid format
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token"
        ) from exc

    expected = _sign(encoded, settings.auth_secret_key)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_signature"
        )

    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "==").decode())
    except Exception as exc:  # pragma: no cover - malformed payload
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token"
        ) from exc

    try:
        exp_ts = int(payload.get("exp", 0))
        if datetime.now(timezone.utc).timestamp() > exp_ts:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="token_expired"
            )
        role = UserRole(payload["role"])
        user_id = UUID(str(payload["sub"]))
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_subject"
        ) from exc

    return AuthenticatedSubject(user_id=user_id, role=role)


async def get_current_subject(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedSubject:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token"
        )
    return decode_token(credentials.credentials)


def require_roles(
    *roles: UserRole,
) -> Callable[[AuthenticatedSubject], AuthenticatedSubject]:
    allowed: set[UserRole] = set(roles)

    async def dependency(
        subject: AuthenticatedSubject = Depends(get_current_subject),
    ) -> AuthenticatedSubject:
        if subject.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role"
            )
        return subject

    return dependency
