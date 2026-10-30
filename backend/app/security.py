from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Donor
from app.settings import settings

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(donor: Donor) -> tuple[str, int]:
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY must be configured with at least 32 characters.",
        )
    expires_in = settings.access_token_expire_minutes * 60
    payload = {
        "sub": str(donor.id),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM), expires_in


def get_current_donor(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Donor:
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(status_code=503, detail="JWT_SECRET_KEY is not configured.")
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        donor_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    donor = db.get(Donor, donor_id)
    if donor is None or not donor.is_active:
        raise HTTPException(status_code=401, detail="Account is unavailable.")
    return donor


def require_admin(donor: Donor = Depends(get_current_donor)) -> Donor:
    if not donor.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return donor
