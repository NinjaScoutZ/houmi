from __future__ import annotations

import datetime
import hmac
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import RUNTIME_MODE, WORKER_SHARED_SECRET
from app.models.all_models import Asset, LicenseEntitlement, Page, Project, RemoteJob, TextBlock, User
from app.security.tokens import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.query(User).filter(User.id == str(claims["sub"])).first()
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is unavailable",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_or_local(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Returns authenticated User if bearer token is provided, or None if omitted or unauthenticated."""
    if credentials is None:
        return None
    try:
        return get_authenticated_user(credentials, db)
    except HTTPException:
        return None


def ensure_project_access(project: Project | None, user: User | None) -> Project:
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if user is not None and hasattr(user, "role") and hasattr(user, "id"):
        if user.role != "admin" and project.owner_id != user.id:
            # Hide resource existence from another tenant.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project



def require_admin(user: User = Depends(get_authenticated_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permission required",
        )
    return user


def require_worker(worker_key: str | None = Header(default=None, alias="X-Houmi-Worker-Key")) -> None:
    if not worker_key or not hmac.compare_digest(worker_key, WORKER_SHARED_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Worker authentication required")


def require_pipeline_access(user: User | None = Depends(get_current_user_or_local), db: Session = Depends(get_db)) -> User | None:
    """Protect heavy pipeline endpoints in Host mode while preserving Local Mode."""
    if user is None or user.role == "admin":
        return user
    now = datetime.datetime.utcnow()
    entitlement = (
        db.query(LicenseEntitlement)
        .filter(
            LicenseEntitlement.user_id == user.id,
            LicenseEntitlement.status == "active",
            LicenseEntitlement.expires_at > now,
        )
        .order_by(LicenseEntitlement.expires_at.desc())
        .first()
    )
    if entitlement is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active license required")
    return user


async def require_resource_access(
    request: Request,
    user: User | None = Depends(get_current_user_or_local),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve nested resource IDs and enforce tenant ownership at the edge."""
    if user is None or user.role == "admin":
        return user

    params = request.path_params
    values = {**request.query_params, **params}
    project_id = values.get("project_id")
    page_id = values.get("page_id")
    block_id = values.get("block_id")
    job_id = values.get("job_id")
    asset_id = values.get("asset_id")

    # FastAPI resolves dependencies before binding a JSON body to its Pydantic
    # model. Reading request.json() here is safe because Starlette caches the
    # body; it lets bulk/import-style endpoints enforce ownership too.
    body: dict = {}
    if request.method not in {"GET", "HEAD", "DELETE"} and "application/json" in request.headers.get("content-type", ""):
        try:
            candidate = await request.json()
            if isinstance(candidate, dict):
                body = candidate
        except Exception:
            body = {}

    project_ids = set()
    if project_id:
        project_ids.add(str(project_id))
    for candidate in (body.get("project_id"), body.get("page_project_id")):
        if candidate:
            project_ids.add(str(candidate))
    query_project_ids = values.get("project_ids")
    if query_project_ids:
        project_ids.update(value.strip() for value in str(query_project_ids).split(",") if value.strip())

    if block_id:
        block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
        if block is None or block.page is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        project_id = block.page.project_id
    elif page_id:
        page = db.query(Page).filter(Page.id == page_id).first()
        if page is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        project_id = page.project_id
    elif job_id:
        job = db.query(RemoteJob).filter(RemoteJob.id == job_id).first()
        if job is None or job.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return user
    elif asset_id:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if asset is None or asset.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return user

    body_block_ids = body.get("block_ids") or []
    if not isinstance(body_block_ids, list):
        body_block_ids = [body_block_ids]
    for candidate_id in body_block_ids:
        if not candidate_id:
            continue
        block = db.query(TextBlock).filter(TextBlock.id == str(candidate_id)).first()
        if block is None or block.page is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        project_ids.add(str(block.page.project_id))

    body_asset_ids = body.get("asset_ids") or []
    if not isinstance(body_asset_ids, list):
        body_asset_ids = [body_asset_ids]
    for candidate_id in body_asset_ids:
        if not candidate_id:
            continue
        asset = db.query(Asset).filter(Asset.id == str(candidate_id)).first()
        if asset is None or asset.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    body_page_id = body.get("page_id")
    if body_page_id:
        page = db.query(Page).filter(Page.id == str(body_page_id)).first()
        if page is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        project_ids.add(str(page.project_id))

    if project_id:
        project_ids.add(str(project_id))
    for candidate_project_id in project_ids:
        project = db.query(Project).filter(Project.id == candidate_project_id).first()
        ensure_project_access(project, user)
    return user
