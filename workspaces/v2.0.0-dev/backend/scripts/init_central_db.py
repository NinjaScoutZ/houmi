"""Initialize the Central Server PostgreSQL database.

Creates all tables (users, redeem_codes, license_entitlements, etc.)
and seeds a default admin user.

Usage:
    set DATABASE_URL=postgresql+psycopg://houmi:houmi_secure_password_2026@localhost:5432/houmi_production
    set HOUMI_RUNTIME_MODE=host
    set HOUMI_JWT_SECRET=change_me_super_secret_jwt_key_2026
    set HOUMI_WORKER_SHARED_SECRET=change_me_worker_secret_2026
    python -m scripts.init_central_db
"""
from __future__ import annotations

import os
import sys

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars if not already set
os.environ.setdefault("HOUMI_RUNTIME_MODE", "host")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://houmi:houmi_secure_password_2026@localhost:5432/houmi_production",
)
os.environ.setdefault("HOUMI_JWT_SECRET", "change_me_super_secret_jwt_key_2026")
os.environ.setdefault("HOUMI_WORKER_SHARED_SECRET", "change_me_worker_secret_2026")

from app.database import Base, engine, SessionLocal
from app.models.all_models import User, RedeemCode, generate_uuid
from app.security.tokens import hash_password, hash_opaque_token

import datetime


def main():
    print("=" * 60)
    print("  Houmi Central Server — PostgreSQL Database Initializer")
    print("=" * 60)
    print(f"  DATABASE_URL: {os.environ.get('DATABASE_URL', 'not set')}")
    print(f"  RUNTIME_MODE: {os.environ.get('HOUMI_RUNTIME_MODE', 'not set')}")
    print()

    # Create all tables
    print("[1/3] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("  ✅ Tables created successfully")

    db = SessionLocal()
    try:
        # Create admin user if not exists
        print("[2/3] Seeding admin user...")
        admin = db.query(User).filter(User.username == "admin").first()
        if admin:
            print(f"  ⏭️  Admin user already exists (id={admin.id})")
        else:
            admin = User(
                username="admin",
                email="admin@houmi.click",
                password_hash=hash_password("admin1234"),
                role="admin",
                status="active",
                approved_at=datetime.datetime.utcnow(),
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"  ✅ Admin user created (id={admin.id})")
            print(f"     username: admin")
            print(f"     password: admin1234")

        # Create a test redeem code
        print("[3/3] Seeding test redeem code...")
        test_code = "HOUMI-TEST-1234"
        code_hash = hash_opaque_token(test_code)
        existing = db.query(RedeemCode).filter(RedeemCode.code_hash == code_hash).first()
        if existing:
            print(f"  ⏭️  Test redeem code already exists (id={existing.id})")
        else:
            code = RedeemCode(
                id=generate_uuid(),
                code_hash=code_hash,
                code_prefix="HOUMI-TEST",
                duration_days=30,
                max_redemptions=100,
                redeemed_count=0,
            )
            db.add(code)
            db.commit()
            print(f"  ✅ Test redeem code created: {test_code}")
            print(f"     Duration: 30 days, Max redemptions: 100")

    finally:
        db.close()

    print()
    print("=" * 60)
    print("  ✅ Database initialization complete!")
    print("  Start the Central Server with:")
    print("    python -m uvicorn app.main:app --host 0.0.0.0 --port 4000")
    print("=" * 60)


if __name__ == "__main__":
    main()
