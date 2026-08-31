from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import DATABASE_URL

_is_sqlite = DATABASE_URL.lower().startswith("sqlite")

# Local desktop keeps SQLite's thread-safe/WAL configuration. Host and worker
# modes use PostgreSQL pooling; they must never silently inherit SQLite options.
if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 60},
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
    )

if _is_sqlite:
    # Open WAL mode and enforce foreign keys on local connections.
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=60000")  # Timeout 60s for SQLITE_BUSY
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_local_schema_compatibility() -> None:
    """Apply only safe additive fixes for existing Local SQLite databases.

    Local Desktop historically used ``create_all()``, which creates missing
    tables but does not add columns to an already existing table. Host schema
    changes remain Alembic-owned; this helper must never run for PostgreSQL.
    """
    if not _is_sqlite:
        return

    inspector = inspect(engine)
    if "projects" not in inspector.get_table_names():
        return

    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "owner_id" not in project_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE projects ADD COLUMN owner_id VARCHAR(36)"))

    # Additive migration for Smart Balloon columns on text_blocks
    if "text_blocks" in inspector.get_table_names():
        tb_cols = {column["name"] for column in inspector.get_columns("text_blocks")}
        with engine.begin() as connection:
            if "smart_x" not in tb_cols:
                connection.execute(text("ALTER TABLE text_blocks ADD COLUMN smart_x FLOAT"))
            if "smart_y" not in tb_cols:
                connection.execute(text("ALTER TABLE text_blocks ADD COLUMN smart_y FLOAT"))
            if "smart_width" not in tb_cols:
                connection.execute(text("ALTER TABLE text_blocks ADD COLUMN smart_width FLOAT"))
            if "smart_height" not in tb_cols:
                connection.execute(text("ALTER TABLE text_blocks ADD COLUMN smart_height FLOAT"))
            if "smart_mask_path" not in tb_cols:
                connection.execute(text("ALTER TABLE text_blocks ADD COLUMN smart_mask_path VARCHAR(512)"))

    # New composite RemoteJob ownership FKs need a matching unique key. This
    # additive index keeps older Local databases compatible with the model
    # without attempting a destructive table rebuild.
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_project_id_owner ON projects (id, owner_id)"
        ))

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
