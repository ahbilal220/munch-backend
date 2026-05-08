from datetime import datetime, timedelta, timezone
from typing import Optional,Union,Any
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials

from app.core.config import settings

# ── Password hashing (bcrypt with salt, per NFR-03) ──────────────────────────
oauth2_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash password with bcrypt salt-hashing (NFR-03)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def validate_university_email(email: str) -> bool:
    """Restrict registration to @university.edu domain (FR-01)."""
    return email.lower().endswith(f"@{settings.ALLOWED_EMAIL_DOMAIN}")


# ── JWT tokens ────────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ── Dependency: current user ──────────────────────────────────────────────────
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services import user_service


async def get_current_user(
    token_auth: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Main dependency to get the authenticated user.
    token_auth.credentials automatically strips 'Bearer ' from the header.
    """
    payload = decode_token(token_auth.credentials)
    user_id: str = payload.get("sub")
    
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    user = await user_service.get_user_by_id(db, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
        
    return user

async def get_current_admin(current_user=Depends(get_current_user)):
    if current_user.role not in ("admin", "kitchen_staff"):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


async def get_kitchen_or_admin(current_user=Depends(get_current_user)):
    if current_user.role not in ("admin", "kitchen_staff"):
        raise HTTPException(status_code=403, detail="Kitchen or Admin access required")
    return current_user
