import datetime
import os
import shutil
import subprocess
from pathlib import Path

def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("backups") / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Starting Houmi Host Server Backup [{timestamp}] ===")

    # Database URL check
    db_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" in db_url:
        dump_file = backup_dir / "database_dump.sql"
        print(f"Creating PostgreSQL dump at {dump_file}...")
        try:
            subprocess.run(f"pg_dump {db_url} > {dump_file}", shell=True, check=True)
            print("✅ PostgreSQL dump completed.")
        except Exception as e:
            print(f"❌ PostgreSQL dump failed: {e}")
    else:
        sqlite_file = Path("data/houmi.db")
        if sqlite_file.exists():
            shutil.copy(sqlite_file, backup_dir / "houmi.db")
            print(f"✅ SQLite database backed up to {backup_dir / 'houmi.db'}.")

    # Asset Data directory check
    data_dir = Path("data")
    if data_dir.exists():
        archive_name = backup_dir / "assets_backup"
        print(f"Compressing assets folder to {archive_name}.zip...")
        shutil.make_archive(str(archive_name), 'zip', data_dir)
        print("✅ Asset data compressed successfully.")

    print(f"🎉 Backup completed! Output stored in: {backup_dir.resolve()}")

if __name__ == "__main__":
    main()
