from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings
from mrv.models import Tenant

bearer_scheme = HTTPBearer(auto_error=False)
JWT_SECRET = settings.JWT_SECRET_KEY
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "predictive-green-energy-engine"
ACCESS_TOKEN_MINUTES = 60


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
            "iss": JWT_ISSUER,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid bearer token required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, TypeError, ValueError, KeyError):
        raise unauthorized from None

    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise unauthorized
    return user


def get_tenant_for_user(user, tenant_id) -> Tenant:
    tenant = Tenant.objects.filter(pk=tenant_id, members__pk=user.pk).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant
