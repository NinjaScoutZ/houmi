import datetime
import uuid
from sqlalchemy import (
    Boolean,
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import CHAR, TypeDecorator


class PortableUUID(TypeDecorator):
    """Use native PostgreSQL UUID while preserving local SQLite string IDs.

    The existing desktop database and tests contain a few legacy non-UUID IDs,
    so SQLite deliberately keeps a permissive CHAR representation. Host
    PostgreSQL still gets native UUID validation/storage.
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID

            return dialect.type_descriptor(UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_project_id_owner"),
    )

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    source_lang = Column(String, default="ko")
    target_lang = Column(String, default="th")
    # Nullable during the staged migration so existing Local projects can be
    # backfilled before Host PostgreSQL enforces NOT NULL.
    owner_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    settings = Column(JSON, default=dict)

    # Relationships
    pages = relationship("Page", back_populates="project", cascade="all, delete-orphan")
    owner = relationship("User", back_populates="projects")
    assets = relationship("Asset", back_populates="project", cascade="all, delete-orphan")

class Page(Base):
    __tablename__ = "pages"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    project_id = Column(PortableUUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    name = Column(String, nullable=True)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    source_image_path = Column(String, nullable=False)
    inpainted_image_path = Column(String, nullable=True)
    rendered_image_path = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, processed, error

    # Relationships
    project = relationship("Project", back_populates="pages")
    text_blocks = relationship("TextBlock", back_populates="page", cascade="all, delete-orphan")

class TextBlock(Base):
    __tablename__ = "text_blocks"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    page_id = Column(PortableUUID(), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    block_index = Column(Integer, nullable=False)
    
    # Coordinates mapping to Full-scale Original Image (in pixels)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    rotation_deg = Column(Float, default=0.0)
    
    # Texts
    source_text = Column(String, default="")
    translation = Column(String, default="")
    
    # Typographies and Styles
    font_family = Column(String, default="NotoSansThai")
    font_size = Column(Float, default=20.0)
    color_hex = Column(String, default="#000000")
    bold = Column(Boolean, default=False)
    italic = Column(Boolean, default=False)
    
    # Layout alignments
    text_direction = Column(String, default="horizontal")  # horizontal, vertical
    text_align = Column(String, default="center")          # left, center, right
    balloon_type = Column(String, default="bubble")        # bubble, narrative, sfx
    
    confidence = Column(Float, default=1.0)
    extra_metadata = Column(JSON, default=dict)

    # Smart Balloon Auto-Resize columns
    smart_x = Column(Float, nullable=True)
    smart_y = Column(Float, nullable=True)
    smart_width = Column(Float, nullable=True)
    smart_height = Column(Float, nullable=True)
    smart_mask_path = Column(String(512), nullable=True)

    @property
    def smart_bbox(self) -> dict:
        """Returns smart bbox if available, otherwise falls back to canonical bbox."""
        if self.smart_x is not None and self.smart_y is not None and self.smart_width is not None and self.smart_height is not None:
            return {"x": self.smart_x, "y": self.smart_y, "width": self.smart_width, "height": self.smart_height}
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    # Relationships
    page = relationship("Page", back_populates="text_blocks")


class TranslationMemory(Base):
    __tablename__ = "translation_memory"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    source_text = Column(String, nullable=False, index=True)
    translation = Column(String, nullable=False)
    source_language = Column(String, default="ja")
    target_language = Column(String, default="th")
    project_id = Column(PortableUUID(), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    frequency = Column(Integer, default=1)
    last_used_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    username = Column(String(50), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    status = Column(String(20), nullable=False, default="active")
    approved_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    projects = relationship("Project", back_populates="owner")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    licenses = relationship("LicenseEntitlement", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="owner", foreign_keys="Asset.owner_id")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(String(255), nullable=False, unique=True)
    token_family_id = Column(PortableUUID(), nullable=False, index=True)
    device_info = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    rotated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    replaced_by_session_id = Column(PortableUUID(), ForeignKey("user_sessions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="sessions")


class RedeemCode(Base):
    __tablename__ = "redeem_codes"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    code_hash = Column(String(255), nullable=False, unique=True)
    code_prefix = Column(String(20), nullable=False)
    duration_days = Column(Integer, nullable=False)
    max_redemptions = Column(Integer, nullable=False, default=1)
    redeemed_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_by = Column(PortableUUID(), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class LicenseEntitlement(Base):
    __tablename__ = "license_entitlements"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_id = Column(PortableUUID(), ForeignKey("redeem_codes.id"), nullable=True)
    starts_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="active")
    grace_period_days = Column(Integer, nullable=False, default=7)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="licenses")


class Redemption(Base):
    __tablename__ = "redemptions"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    code_id = Column(PortableUUID(), ForeignKey("redeem_codes.id"), nullable=False, index=True)
    user_id = Column(PortableUUID(), ForeignKey("users.id"), nullable=False, index=True)
    days_added = Column(Integer, nullable=False)
    previous_expires_at = Column(DateTime, nullable=True)
    new_expires_at = Column(DateTime, nullable=False)
    redeemed_at = Column(DateTime, default=datetime.datetime.utcnow)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "device_fingerprint", name="uq_user_device"),)

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_fingerprint = Column(String(255), nullable=False)
    device_name = Column(String(100), nullable=True)
    last_active_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_trusted = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="devices")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    owner_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(PortableUUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    storage_key = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=False)
    media_type = Column(String(50), nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    last_accessed_at = Column(DateTime, default=datetime.datetime.utcnow)
    retention_until = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="assets", foreign_keys=[owner_id])
    project = relationship("Project", back_populates="assets")


class RemoteJob(Base):
    __tablename__ = "remote_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_job_user_idempotency"),
        ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.owner_id"],
            name="fk_remote_job_project_owner",
            ondelete="CASCADE",
        ),
    )

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(PortableUUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    progress_percent = Column(Integer, nullable=False, default=0)
    progress_step = Column(String(100), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    worker_id = Column(String(50), nullable=True)
    lease_token = Column(PortableUUID(), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    heartbeat_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    idempotency_key = Column(String(64), nullable=True)
    input_manifest = Column(JSON, nullable=False, default=dict)
    result_asset_id = Column(PortableUUID(), ForeignKey("assets.id"), nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence_num", name="uq_job_event_sequence"),)

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    job_id = Column(PortableUUID(), ForeignKey("remote_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_num = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    payload_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WsTicket(Base):
    __tablename__ = "ws_tickets"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    ticket_hash = Column(String(255), nullable=False, unique=True)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(PortableUUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(PortableUUID(), primary_key=True, default=generate_uuid)
    admin_id = Column(PortableUUID(), ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    target_user_id = Column(PortableUUID(), ForeignKey("users.id"), nullable=True, index=True)
    details_json = Column(JSON, nullable=False, default=dict)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
