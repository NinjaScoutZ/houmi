"""Create the clean Host PostgreSQL schema.

Revision ID: 0001_host_initial_schema
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_host_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            "The Host initial migration requires PostgreSQL; Local SQLite uses its desktop compatibility path"
        )

    _sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    _sql("""
    CREATE TABLE users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        approved_at TIMESTAMPTZ NULL,
        last_login_at TIMESTAMPTZ NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT users_role_check CHECK (role IN ('user', 'admin')),
        CONSTRAINT users_status_check CHECK (status IN ('active', 'suspended', 'deleted'))
    )
    """)

    _sql("""
    CREATE TABLE projects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR NOT NULL,
        source_lang VARCHAR NOT NULL DEFAULT 'ja',
        target_lang VARCHAR NOT NULL DEFAULT 'th',
        owner_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        settings JSONB NOT NULL DEFAULT '{}'::jsonb,
        CONSTRAINT uq_project_id_owner UNIQUE(id, owner_id)
    )
    """)
    _sql("CREATE INDEX idx_projects_owner ON projects(owner_id)")

    _sql("""
    CREATE TABLE pages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL,
        name VARCHAR NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        source_image_path VARCHAR NOT NULL,
        inpainted_image_path VARCHAR NULL,
        rendered_image_path VARCHAR NULL,
        status VARCHAR NOT NULL DEFAULT 'pending'
    )
    """)

    _sql("""
    CREATE TABLE text_blocks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
        block_index INTEGER NOT NULL,
        x DOUBLE PRECISION NOT NULL,
        y DOUBLE PRECISION NOT NULL,
        width DOUBLE PRECISION NOT NULL,
        height DOUBLE PRECISION NOT NULL,
        rotation_deg DOUBLE PRECISION NOT NULL DEFAULT 0,
        source_text VARCHAR NOT NULL DEFAULT '',
        translation VARCHAR NOT NULL DEFAULT '',
        font_family VARCHAR NOT NULL DEFAULT 'NotoSansThai',
        font_size DOUBLE PRECISION NOT NULL DEFAULT 20,
        color_hex VARCHAR NOT NULL DEFAULT '#000000',
        bold BOOLEAN NOT NULL DEFAULT FALSE,
        italic BOOLEAN NOT NULL DEFAULT FALSE,
        text_direction VARCHAR NOT NULL DEFAULT 'horizontal',
        text_align VARCHAR NOT NULL DEFAULT 'center',
        balloon_type VARCHAR NOT NULL DEFAULT 'bubble',
        confidence DOUBLE PRECISION NOT NULL DEFAULT 1,
        extra_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """)

    _sql("""
    CREATE TABLE translation_memory (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        source_text VARCHAR NOT NULL,
        translation VARCHAR NOT NULL,
        source_language VARCHAR NOT NULL DEFAULT 'ja',
        target_language VARCHAR NOT NULL DEFAULT 'th',
        project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
        frequency INTEGER NOT NULL DEFAULT 1,
        last_used_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    _sql("CREATE INDEX idx_translation_memory_source ON translation_memory(source_text)")

    _sql("""
    CREATE TABLE user_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        refresh_token_hash VARCHAR(255) UNIQUE NOT NULL,
        token_family_id UUID NOT NULL,
        device_info VARCHAR(255),
        ip_address VARCHAR(45),
        expires_at TIMESTAMPTZ NOT NULL,
        rotated_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ,
        replaced_by_session_id UUID REFERENCES user_sessions(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    _sql("CREATE INDEX idx_user_sessions_user ON user_sessions(user_id)")

    _sql("""
    CREATE TABLE redeem_codes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        code_hash VARCHAR(255) UNIQUE NOT NULL,
        code_prefix VARCHAR(10) NOT NULL,
        duration_days INTEGER NOT NULL CHECK (duration_days > 0),
        max_redemptions INTEGER NOT NULL DEFAULT 1 CHECK (max_redemptions > 0),
        redeemed_count INTEGER NOT NULL DEFAULT 0 CHECK (redeemed_count >= 0),
        expires_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ,
        created_by UUID REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    _sql("""
    CREATE TABLE license_entitlements (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        code_id UUID REFERENCES redeem_codes(id),
        starts_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        grace_period_days INTEGER NOT NULL DEFAULT 7 CHECK (grace_period_days >= 0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT license_status_check CHECK (status IN ('active', 'expired', 'revoked'))
    )
    """)
    _sql("CREATE INDEX idx_license_user_expiry ON license_entitlements(user_id, expires_at)")

    _sql("""
    CREATE TABLE redemptions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        code_id UUID NOT NULL REFERENCES redeem_codes(id),
        user_id UUID NOT NULL REFERENCES users(id),
        days_added INTEGER NOT NULL CHECK (days_added > 0),
        previous_expires_at TIMESTAMPTZ,
        new_expires_at TIMESTAMPTZ NOT NULL,
        redeemed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    _sql("""
    CREATE TABLE devices (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        device_fingerprint VARCHAR(255) NOT NULL,
        device_name VARCHAR(100),
        last_active_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        is_trusted BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_user_device UNIQUE(user_id, device_fingerprint)
    )
    """)

    _sql("""
    CREATE TABLE assets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
        storage_key VARCHAR(512) NOT NULL,
        original_filename VARCHAR(255) NOT NULL,
        media_type VARCHAR(50) NOT NULL,
        byte_size BIGINT NOT NULL CHECK (byte_size > 0),
        width INTEGER,
        height INTEGER,
        sha256 VARCHAR(64),
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        retention_until TIMESTAMPTZ,
        deleted_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT asset_status_check CHECK (status IN ('uploading', 'active', 'processing', 'orphan', 'deleted'))
    )
    """)
    _sql("CREATE INDEX idx_assets_owner ON assets(owner_id)")
    _sql("CREATE INDEX idx_assets_project ON assets(project_id)")

    _sql("""
    CREATE TABLE remote_jobs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        project_id UUID NOT NULL,
        job_type VARCHAR(50) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'queued',
        progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
        progress_step VARCHAR(100),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
        worker_id VARCHAR(50),
        lease_token UUID,
        lease_expires_at TIMESTAMPTZ,
        heartbeat_at TIMESTAMPTZ,
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ,
        cancelled_at TIMESTAMPTZ,
        cancel_reason TEXT,
        cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
        idempotency_key VARCHAR(64),
        input_manifest JSONB NOT NULL,
        result_asset_id UUID REFERENCES assets(id),
        error_code VARCHAR(50),
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_user_idempotency UNIQUE(user_id, idempotency_key),
        CONSTRAINT fk_remote_job_project_owner FOREIGN KEY(project_id, user_id)
            REFERENCES projects(id, owner_id) ON DELETE CASCADE,
        CONSTRAINT job_status_check CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
        CONSTRAINT job_type_check CHECK (job_type IN ('detect', 'inpaint', 'ocr', 'full_pipeline'))
    )
    """)
    _sql("CREATE INDEX idx_remote_jobs_status ON remote_jobs(status)")
    _sql("CREATE INDEX idx_remote_jobs_lease ON remote_jobs(lease_expires_at)")
    _sql("CREATE INDEX idx_remote_jobs_project ON remote_jobs(project_id)")

    _sql("""
    CREATE TABLE job_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        job_id UUID NOT NULL REFERENCES remote_jobs(id) ON DELETE CASCADE,
        sequence_num INTEGER NOT NULL CHECK (sequence_num >= 0),
        event_type VARCHAR(50) NOT NULL,
        payload_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_job_sequence UNIQUE(job_id, sequence_num)
    )
    """)
    _sql("CREATE INDEX idx_job_events_job ON job_events(job_id)")

    _sql("""
    CREATE TABLE ws_tickets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ticket_hash VARCHAR(255) UNIQUE NOT NULL,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        expires_at TIMESTAMPTZ NOT NULL,
        consumed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    _sql("CREATE INDEX idx_ws_tickets_expiry ON ws_tickets(expires_at)")

    _sql("""
    CREATE TABLE admin_audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        admin_id UUID NOT NULL REFERENCES users(id),
        action VARCHAR(50) NOT NULL,
        target_user_id UUID REFERENCES users(id),
        details_json JSONB NOT NULL,
        ip_address VARCHAR(45),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    _sql("""
    CREATE OR REPLACE FUNCTION houmi_set_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)
    _sql("""
    CREATE TRIGGER projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION houmi_set_updated_at()
    """)
    _sql("""
    CREATE TRIGGER remote_jobs_updated_at
    BEFORE UPDATE ON remote_jobs
    FOR EACH ROW EXECUTE FUNCTION houmi_set_updated_at()
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("The Host initial migration requires PostgreSQL")
    _sql("DROP TRIGGER IF EXISTS remote_jobs_updated_at ON remote_jobs")
    _sql("DROP TRIGGER IF EXISTS projects_updated_at ON projects")
    _sql("DROP FUNCTION IF EXISTS houmi_set_updated_at()")
    for table in (
        "admin_audit_logs",
        "ws_tickets",
        "job_events",
        "remote_jobs",
        "assets",
        "devices",
        "redemptions",
        "license_entitlements",
        "redeem_codes",
        "user_sessions",
        "translation_memory",
        "text_blocks",
        "pages",
        "projects",
        "users",
    ):
        _sql(f"DROP TABLE IF EXISTS {table} CASCADE")
