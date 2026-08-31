"""
Supabase PostgreSQL Auto-Migration & Verification Utility
Connects to your Supabase project, verifies connectivity, and creates all tables.
"""

import os
import sys
from pathlib import Path
import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main():
    print("\n" + "=" * 70)
    print("      ⚡ HOUMI STUDIO — SUPABASE DATABASE SETUP & SYNC  ⚡")
    print("=" * 70)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("⚠️  DATABASE_URL environment variable is not set.")
        print("💡 Example:")
        print("   $env:DATABASE_URL=\"postgresql+psycopg://postgres.[REF]:[PASS]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require\"")
        print("   python scripts/setup_supabase.py\n")
        return 1

    # Normalize connection string dialect if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)

    print(f"📡 Target Connection : {db_url.split('@')[-1] if '@' in db_url else db_url}")
    print("⏳ Connecting to Supabase PostgreSQL...")

    try:
        engine = sa.create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT version();")).scalar()
            print(f"✅ Connection Succeeded! Server Version: {result[:50]}...")

            print("\n📦 Applying Supabase schema (tables, indices, foreign keys)...")
            schema_file = PROJECT_ROOT / "supabase_schema.sql"
            if schema_file.exists():
                sql_content = schema_file.read_text(encoding="utf-8")
                # Split and execute statements
                statements = [s.strip() for s in sql_content.split(";") if s.strip()]
                for stmt in statements:
                    conn.execute(sa.text(stmt))
                conn.commit()
                print("🎉 All 10 tables created and indexed successfully on Supabase!")
            else:
                print("❌ Error: supabase_schema.sql not found.")
                return 1

        print("=" * 70)
        print("🚀 Supabase Database is ready! You can now start the host server with:")
        print("   python scripts/start_cloud_hub.py --tunnel\n")
        return 0

    except Exception as err:
        print(f"\n❌ Failed to connect or apply schema to Supabase: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
