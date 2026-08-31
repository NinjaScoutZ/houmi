import argparse
import sys
import uuid
from pathlib import Path

# Add parent dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import SessionLocal
from app.models.all_models import User
from app.security.tokens import hash_password

def main():
    parser = argparse.ArgumentParser(description="Create or seed an Administrator account for Houmi Studio Host.")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", required=True, help="Admin password")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing = db.query(User).filter((User.username == args.username) | (User.email == args.email)).first()
        if existing:
            print(f"[EXISTS] Account '{existing.username}' already exists. Updating role to 'admin'...")
            existing.role = "admin"
            existing.status = "active"
            existing.password_hash = hash_password(args.password)
            db.commit()
            print(f"✅ Account '{existing.username}' updated to Administrator successfully.")
            return

        admin_user = User(
            id=str(uuid.uuid4()),
            username=args.username,
            email=args.email,
            password_hash=hash_password(args.password),
            role="admin",
            status="active"
        )
        db.add(admin_user)
        db.commit()
        print(f"✅ Administrator account '{args.username}' created successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    main()
