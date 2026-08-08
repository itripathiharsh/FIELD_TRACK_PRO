# FieldTrack Pro — Authentication (JWT/OAuth2)
### Phase 3.2 — Backend Development
### Revision 2 — rewritten for Python/FastAPI

Builds directly on Security Design doc decisions. Stateless JWT auth, refresh tokens tracked server-side for revocation. **All behavior described below is identical to the original Spring implementation** — only the code changed.

---

## 1. Auth Dependencies (Replaces Spring Security's Filter Chain)

FastAPI has no global filter-chain concept — route protection is expressed as reusable `Depends()` functions applied per-router or per-route, which is functionally equivalent to Spring's `authorizeHttpRequests` rules:

```python
# app/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.security.jwt import decode_access_token
from app.models.user import Role

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db=Depends(get_db),
):
    payload = decode_access_token(credentials.credentials)   # raises 401 internally on invalid/expired
    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active:
        # re-checks the DB record, not just the token payload — per Security Design Section 2:
        # a token can be structurally valid but the account deactivated mid-session
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account inactive or not found")
    return user


def require_role(role: Role):
    async def checker(user=Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user
    return checker


require_admin = require_role(Role.ADMIN)
require_employee = require_role(Role.EMPLOYEE)
```

Public routes (`/auth/*`, `/docs`) simply omit `Depends(get_current_user)` entirely — the FastAPI equivalent of Spring Security's `permitAll()`. Every other router includes the appropriate dependency at the router or route level:

```python
# app/api/v1/employees.py
router = APIRouter(dependencies=[Depends(require_admin)])   # whole router is ADMIN-only, matches original rule
```

---

## 2. JWT Handling

```python
# app/security/jwt.py
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, status
from app.config import settings

ALGORITHM = "HS256"


def create_access_token(user) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
```

Same claims, same 15-minute expiry, same HS256 algorithm as the original — a client (Android/Web) parsing this token sees no difference at all.

---

## 3. Refresh Token Handling

Refresh tokens remain **opaque random strings, hashed before storage** (never store the raw token — same principle as passwords, unchanged from the original design):

```python
# app/services/refresh_token_service.py
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from app.models.refresh_token import RefreshToken
from app.config import settings


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class RefreshTokenService:
    def __init__(self, db):
        self.db = db

    async def issue(self, user) -> str:
        raw_token = f"{secrets.token_hex(16)}.{secrets.token_hex(16)}"
        entity = RefreshToken(
            user_id=user.id,
            token_hash=_hash(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expiry_days),
            revoked=False,
        )
        self.db.add(entity)
        await self.db.commit()
        return raw_token

    async def validate_and_get_user(self, raw_token: str):
        entity = await self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token))
        )
        if entity is None or entity.revoked or entity.expires_at < datetime.now(timezone.utc):
            raise InvalidTokenException("Refresh token invalid or expired")
        return await self.db.get(User, entity.user_id)

    async def revoke(self, raw_token: str):
        entity = await self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token))
        )
        if entity:
            entity.revoked = True
            await self.db.commit()

    async def revoke_all_for_user(self, user_id):
        await self.db.execute(
            update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True)
        )
        await self.db.commit()
```

**Why this still matters, unchanged from the original**: this is what makes "deactivate employee" (B1) actually take effect immediately — `revoke_all_for_user` is called from `EmployeeService.deactivate()`, so a deactivated employee's existing session dies on their next token refresh, not after a 7-day wait.

---

## 4. Password Hashing

```python
# app/security/password.py
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(raw_password: str) -> str:
    return pwd_context.hash(raw_password)


def verify_password(raw_password: str, hashed: str) -> bool:
    return pwd_context.verify(raw_password, hashed)
```

Bcrypt, cost factor 12 — identical parameters to the original `BCryptPasswordEncoder(12)`.

---

## 5. Auth Endpoints

```python
# app/api/v1/auth.py
from fastapi import APIRouter, Depends
from app.schemas.auth import LoginRequest, RefreshRequest, AuthResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, auth_service: AuthService = Depends()):
    # rate-limit check happens inside authenticate() before credentials are even checked (see Section 6)
    user = await auth_service.authenticate(request.identifier, request.password)
    access_token = create_access_token(user)
    refresh_token = await auth_service.refresh_token_service.issue(user)
    return AuthResponse(access_token=access_token, refresh_token=refresh_token, user=user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: RefreshRequest, auth_service: AuthService = Depends()):
    user = await auth_service.refresh_token_service.validate_and_get_user(request.refresh_token)
    new_access_token = create_access_token(user)
    return AuthResponse(access_token=new_access_token, refresh_token=request.refresh_token, user=user)


@router.post("/logout", status_code=204)
async def logout(request: RefreshRequest, auth_service: AuthService = Depends()):
    await auth_service.refresh_token_service.revoke(request.refresh_token)
```

Request/response shapes (`identifier` + `password` in, `accessToken`/`refreshToken`/`user` out) are byte-for-byte identical to the API Design doc's original contract — Android and Web needed zero changes.

---

## 6. Login Rate Limiting

```python
# app/security/rate_limiter.py
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from fastapi import HTTPException, status

MAX_ATTEMPTS = 5
WINDOW = timedelta(minutes=15)


class LoginRateLimiter:
    def __init__(self):
        self._attempts: dict[str, list[datetime]] = defaultdict(list)

    def check_allowed(self, identifier: str):
        now = datetime.now(timezone.utc)
        recent = [t for t in self._attempts[identifier] if now - t < WINDOW]
        self._attempts[identifier] = recent
        if len(recent) >= MAX_ATTEMPTS:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts — try again later")

    def record_failure(self, identifier: str):
        self._attempts[identifier].append(datetime.now(timezone.utc))

    def record_success(self, identifier: str):
        self._attempts.pop(identifier, None)


# Single process-wide instance, same in-memory approach and same scaling caveat as the original
login_rate_limiter = LoginRateLimiter()
```

**Same flag as the original, restated**: this in-memory approach resets on process restart and doesn't work across multiple backend instances. Fine for MVP single-container deployment (no Kubernetes, one Uvicorn process per the Tech Stack decision). If horizontal scaling ever happens, this needs to move to Redis — not a Phase 3 concern.

---

## 7. "OAuth2" Clarification

Unchanged from the original doc's framing: this build uses **JWT-based stateless authentication issued by our own backend**, not third-party OAuth2 login. OAuth2 as a protocol concept (bearer tokens, access/refresh token pattern) is followed, but there's no external identity provider — employees/admins are created directly by admins (B1), not self-registered via a social login. If Google/Microsoft SSO login for admins is ever wanted, that's a real scope addition worth flagging when it comes up, not assumed silently.

---

**Next up:** Core APIs (Phase 3.3) — Employee, Customer, and Visit routers/services built on top of this auth layer.
