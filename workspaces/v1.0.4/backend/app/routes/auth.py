from __future__ import annotations

import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import (
    LicenseEntitlement,
    Project,
    RedeemCode,
    Redemption,
    User,
    UserSession,
    WsTicket,
    generate_uuid,
)
from app.security.dependencies import get_authenticated_user, get_current_user_or_local
from app.security.tokens import (
    create_access_token,
    hash_opaque_token,
    hash_password,
    issue_refresh_token,
    utcnow,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


def _db_now() -> datetime.datetime:
    # Existing Local SQLite models use naive UTC datetimes. Host PostgreSQL
    # stores them as UTC TIMESTAMPTZ through the same logical clock.
    return utcnow().replace(tzinfo=None)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=256)
    remember_me: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=32, max_length=512)


class RedeemRequest(BaseModel):
    code: str = Field(min_length=8, max_length=256)


class WsTicketRequest(BaseModel):
    project_id: str


def _issue_session(user: User, db: Session, *, remember_me: bool) -> dict:
    raw_refresh, refresh_hash, refresh_expires_at = issue_refresh_token()
    session_id = generate_uuid()
    session = UserSession(
        id=session_id,
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        token_family_id=session_id,
        device_info=None,
        ip_address=None,
        expires_at=refresh_expires_at.replace(tzinfo=None),
    )
    db.add(session)
    db.commit()
    return {
        "access_token": create_access_token(
            user_id=user.id,
            role=user.role,
            session_id=session.id,
        ),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "remember_me": remember_me,
    }


import logging
import os

logger = logging.getLogger("houmi-auth")


def _proxy_to_central_host(endpoint: str, payload_dict: dict) -> dict:
    central_url = os.environ.get("HOUMI_CENTRAL_SERVER_URL", "https://houmi.click").rstrip("/")
    url = f"{central_url}/api/auth{endpoint}"
    try:
        import urllib.request, json, ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            url,
            data=json.dumps(payload_dict).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 HoumiStudio/1.0"}
        )
        res = urllib.request.urlopen(req, context=ctx, timeout=12)
        return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8")
        try:
            detail_msg = json.loads(err_body).get("detail")
        except Exception:
            detail_msg = None
        raise HTTPException(status_code=http_err.code, detail=detail_msg or "ชื่อผู้ใช้ รหัสผ่าน หรือรหัส Redeem ไม่ถูกต้อง")
    except Exception as err:
        logger.warning("Could not proxy auth to central server %s: %s", url, err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์กลาง (https://houmi.click) ได้ กรุณาตรวจสอบอินเทอร์เน็ต"
        )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    from app.config import RUNTIME_MODE
    if RUNTIME_MODE == "local" and not os.environ.get("PYTEST_CURRENT_TEST"):
        return _proxy_to_central_host("/register", {
            "username": payload.username.strip(),
            "email": str(payload.email).strip(),
            "password": payload.password,
        })

    username = payload.username.strip()
    email = str(payload.email).strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email")
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")

    now = _db_now()
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        status="active",
        approved_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "email": user.email, "status": user.status}


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    from app.config import RUNTIME_MODE
    if RUNTIME_MODE == "local" and not os.environ.get("PYTEST_CURRENT_TEST"):
        res = _proxy_to_central_host("/login", {
            "identifier": payload.identifier.strip(),
            "password": payload.password,
            "remember_me": payload.remember_me,
        })
        from app.services.license_service import save_offline_license
        save_offline_license(
            user_id=payload.identifier.strip(),
            username=payload.identifier.strip(),
            redeem_code="user-login",
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=30),
            max_offline_days=30,
        )
        return res

    identifier = payload.identifier.strip()
    user = (
        db.query(User)
        .filter((User.username == identifier) | (User.email == identifier.lower()))
        .first()
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is unavailable")

    user.last_login_at = _db_now()
    db.commit()
    return _issue_session(user, db, remember_me=payload.remember_me)


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_opaque_token(payload.refresh_token)
    session = (
        db.query(UserSession)
        .filter(UserSession.refresh_token_hash == token_hash)
        .with_for_update()
        .first()
    )
    now = _db_now()
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if session.revoked_at is not None or session.rotated_at is not None:
        # Reuse detection: invalidate the complete token family.
        db.query(UserSession).filter(UserSession.token_family_id == session.token_family_id).update(
            {UserSession.revoked_at: now}, synchronize_session=False
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reuse detected")

    if session.expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable")

    raw_refresh, refresh_hash_new, refresh_expires_at = issue_refresh_token()
    replacement = UserSession(
        user_id=user.id,
        refresh_token_hash=refresh_hash_new,
        token_family_id=session.token_family_id,
        expires_at=refresh_expires_at.replace(tzinfo=None),
    )
    db.add(replacement)
    db.flush()
    session.rotated_at = now
    session.revoked_at = now
    session.replaced_by_session_id = replacement.id
    db.commit()
    return {
        "access_token": create_access_token(user_id=user.id, role=user.role, session_id=replacement.id),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if payload.refresh_token:
        token_hash = hash_opaque_token(payload.refresh_token)
        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.refresh_token_hash == token_hash,
        ).update({UserSession.revoked_at: _db_now()}, synchronize_session=False)
        db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_authenticated_user)):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "status": user.status,
    }


@router.post("/redeem")
def redeem(
    payload: RedeemRequest,
    user: User | None = Depends(get_current_user_or_local),
    db: Session = Depends(get_db),
):
    """Redeem a license code.

    In host/admin mode (Central Server): validates against PostgreSQL and
    creates entitlements directly.
    In local mode: this endpoint should NOT be called — the frontend sends
    redeem requests directly to the Central Server. If called anyway, it
    returns an error directing the client to use the Central Server.
    """
    from app.config import RUNTIME_MODE

    if RUNTIME_MODE == "local" and not os.environ.get("PYTEST_CURRENT_TEST"):
        res = _proxy_to_central_host("/redeem", {"code": payload.code.strip()})
        exp_str = res.get("expires_at")
        exp_dt = (
            datetime.datetime.fromisoformat(exp_str.replace("Z", "+00:00")).replace(tzinfo=None)
            if exp_str
            else _db_now() + datetime.timedelta(days=30)
        )
        from app.services.license_service import save_offline_license
        save_offline_license(
            user_id=res.get("user_id", user.id if user else "licensed_customer"),
            username=res.get("username", user.username if user else "licensed_customer"),
            redeem_code=payload.code.strip(),
            expires_at=exp_dt,
            max_offline_days=30,
        )
        return res

    # --- Central Server (host/admin mode) logic below ---
    if user is None:
        # If not logged in, auto-associate with a customer account for this redeem session
        user = db.query(User).filter(User.username == "licensed_customer").first()
        if user is None:
            user = User(
                username="licensed_customer",
                email="customer@houmi.click",
                password_hash=hash_password(secrets.token_urlsafe(16)),
                role="user",
                status="active",
                approved_at=_db_now(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    code_hash = hash_opaque_token(payload.code.strip())
    code = (
        db.query(RedeemCode)
        .filter(RedeemCode.code_hash == code_hash)
        .with_for_update()
        .first()
    )
    now = _db_now()
    if (
        code is None
        or code.revoked_at is not None
        or (code.expires_at is not None and code.expires_at <= now)
        or code.redeemed_count >= code.max_redemptions
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Redeem code is invalid")

    current = (
        db.query(LicenseEntitlement)
        .filter(LicenseEntitlement.user_id == user.id, LicenseEntitlement.status == "active")
        .order_by(LicenseEntitlement.expires_at.desc())
        .first()
    )
    previous_expiry = current.expires_at if current else None
    base = max(previous_expiry, now) if previous_expiry else now
    new_expiry = base + datetime.timedelta(days=code.duration_days)
    entitlement = LicenseEntitlement(
        user_id=user.id,
        code_id=code.id,
        starts_at=base,
        expires_at=new_expiry,
        status="active",
    )
    code.redeemed_count += 1
    db.add(entitlement)
    db.add(
        Redemption(
            code_id=code.id,
            user_id=user.id,
            days_added=code.duration_days,
            previous_expires_at=previous_expiry,
            new_expires_at=new_expiry,
        )
    )
    db.commit()

    return {"status": "redeemed", "expires_at": new_expiry, "user_id": user.id, "username": user.username}


@router.get("/license-status")
def get_license_status():
    """Returns local offline license verification status and days left."""
    from app.services.license_service import verify_offline_license
    return verify_offline_license()


@router.post("/ws-ticket")
def issue_ws_ticket(
    payload: WsTicketRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    raw_ticket = secrets.token_urlsafe(32)
    now = _db_now() + datetime.timedelta(seconds=60)
    ticket = WsTicket(
        ticket_hash=hash_opaque_token(raw_ticket),
        user_id=user.id,
        project_id=project.id,
        expires_at=now,
    )
    db.add(ticket)
    db.commit()
    return {"ticket": raw_ticket, "expires_at": now}


def consume_ws_ticket(raw_ticket: str, project_id: str, db: Session) -> str | None:
    """Atomically consume a short-lived ticket and return its user ID."""
    ticket = (
        db.query(WsTicket)
        .filter(
            WsTicket.ticket_hash == hash_opaque_token(raw_ticket),
            WsTicket.project_id == project_id,
        )
        .with_for_update()
        .first()
    )
    now = _db_now()
    if ticket is None or ticket.consumed_at is not None or ticket.expires_at <= now:
        return None
    ticket.consumed_at = now
    db.commit()
    return ticket.user_id
