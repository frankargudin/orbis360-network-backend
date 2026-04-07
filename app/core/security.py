"""JWT authentication, password hashing, and RBAC."""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Role hierarchy: admin > operator > viewer
ROLES = {
    "admin": 3,
    "operator": 2,
    "viewer": 1,
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, role: str = "viewer", username: str = "") -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "username": username, "exp": expires}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    return decode_token(token)


def require_role(min_role: str):
    """Dependency that requires a minimum role level.
    Usage: dependencies=[Depends(require_role("operator"))]
    """
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        user_level = ROLES.get(user.get("role", "viewer"), 0)
        required_level = ROLES.get(min_role, 0)
        if user_level < required_level:
            role_names = {"admin": "Administrador", "operator": "Operador", "viewer": "Visor"}
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol de {role_names.get(min_role, min_role)} o superior",
            )
        return user
    return checker


# Convenience aliases
require_admin = require_role("admin")
require_operator = require_role("operator")
