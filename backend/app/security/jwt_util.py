from datetime import datetime, timedelta
from typing import Optional
from ..config import settings

# Support either `python-jose` (preferred) or `PyJWT` as a fallback so tests
# can run in environments where `jose` isn't installed.
try:
    from jose import jwt as _jose_jwt
    _HAS_JOSE = True
except Exception:
    _HAS_JOSE = False
    try:
        import jwt as _pyjwt
    except Exception:
        _pyjwt = None


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=(expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"sub": subject, "exp": expire}
    if _HAS_JOSE:
        return _jose_jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    if _pyjwt is not None:
        return _pyjwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    raise RuntimeError("No JWT library available: install `python-jose` or `PyJWT`")


def decode_token(token: str) -> dict:
    if _HAS_JOSE:
        return _jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if _pyjwt is not None:
        return _pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    raise RuntimeError("No JWT library available: install `python-jose` or `PyJWT`")
