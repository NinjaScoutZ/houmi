-- ============================================================================
-- HOUMI / DOBKLE STUDIO — SUPABASE POSTGRESQL INITIAL SCHEMA
-- Run this SQL in your Supabase SQL Editor (https://supabase.com/dashboard)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
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
);

-- 2. Projects Table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL,
    source_lang VARCHAR NOT NULL DEFAULT 'ja',
    target_lang VARCHAR NOT NULL DEFAULT 'th',
    owner_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_project_id_owner UNIQUE(id, owner_id)
);
CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id);

-- 3. Pages Table
CREATE TABLE IF NOT EXISTS pages (
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
);
CREATE INDEX IF NOT EXISTS idx_pages_project ON pages(project_id);

-- 4. Text Blocks Table
CREATE TABLE IF NOT EXISTS text_blocks (
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
);
CREATE INDEX IF NOT EXISTS idx_blocks_page ON text_blocks(page_id);

-- 5. User Sessions Table (JWT Refresh & Family Rotation)
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(64) UNIQUE NOT NULL,
    token_family_id UUID NOT NULL,
    device_info VARCHAR(255) NULL,
    ip_address VARCHAR(45) NULL,
    revoked_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_revoked ON user_sessions(user_id, revoked_at);
CREATE INDEX IF NOT EXISTS idx_user_sessions_family ON user_sessions(token_family_id);

-- 6. Redeem Codes Table (License Activation Keys)
CREATE TABLE IF NOT EXISTS redeem_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code_hash VARCHAR(64) UNIQUE NOT NULL,
    label VARCHAR(100) NULL,
    duration_days INTEGER NOT NULL DEFAULT 30,
    max_redemptions INTEGER NOT NULL DEFAULT 1,
    redeemed_count INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_redeem_codes_hash ON redeem_codes(code_hash);

-- 7. Redemptions Table
CREATE TABLE IF NOT EXISTS redemptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code_id UUID NOT NULL REFERENCES redeem_codes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_redemptions_code_user UNIQUE(code_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_redemptions_user ON redemptions(user_id);

-- 8. License Entitlements Table
CREATE TABLE IF NOT EXISTS license_entitlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_id UUID NULL REFERENCES redeem_codes(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    granted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT entitlements_status_check CHECK (status IN ('active', 'expired', 'revoked'))
);
CREATE INDEX IF NOT EXISTS idx_entitlements_user_status ON license_entitlements(user_id, status);

-- 9. Remote Jobs Table
CREATE TABLE IF NOT EXISTS remote_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    page_id UUID NULL REFERENCES pages(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    current_step VARCHAR(100) NULL,
    error_message VARCHAR NULL,
    idempotency_key VARCHAR(100) NULL,
    worker_id VARCHAR(100) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_remote_jobs_user_idempotency UNIQUE(user_id, idempotency_key),
    CONSTRAINT remote_jobs_status_check CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled'))
);
CREATE INDEX IF NOT EXISTS idx_remote_jobs_user_status ON remote_jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_remote_jobs_status_created ON remote_jobs(status, created_at);

-- 10. User Storage Records
CREATE TABLE IF NOT EXISTS user_storage_records (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    storage_bytes_used BIGINT NOT NULL DEFAULT 0,
    last_reconciled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SEED INITIAL DATA: Default licensed customer & sample redeem code
-- ============================================================================
INSERT INTO users (id, username, email, password_hash, role, status, approved_at)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'licensed_customer',
    'customer@houmi.click',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'user',
    'active',
    CURRENT_TIMESTAMP
)
ON CONFLICT (username) DO NOTHING;

-- Seed Sample Redeem Code: HOUMI-DOBKLE-PRO-2026 (SHA256 hash)
-- Hash of 'HOUMI-DOBKLE-PRO-2026'
INSERT INTO redeem_codes (code_hash, label, duration_days, max_redemptions, redeemed_count, expires_at)
VALUES (
    encode(digest('HOUMI-DOBKLE-PRO-2026', 'sha256'), 'hex'),
    'DOBKLE VIP 365 Days Promo',
    365,
    1000,
    0,
    CURRENT_TIMESTAMP + INTERVAL '365 days'
)
ON CONFLICT (code_hash) DO NOTHING;
