"""
Idempotent database migration helper.

Run on the VPS after pulling code and before restarting the service:
    .venv/bin/python -m src.backend.api.migrate
"""
from sqlalchemy import inspect, text

from .v2.db.database import engine
from .v2.db.models import Base


def column_exists(conn, table: str, column: str) -> bool:
    inspector = inspect(conn)
    return column in [c["name"] for c in inspector.get_columns(table)]


def add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    if column_exists(conn, table, column):
        print(f"OK: {table}.{column} already exists")
        return
    print(f"Adding {table}.{column}...")
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    print(f"OK: added {table}.{column}")


def run() -> None:
    print("Ensuring database tables exist...")
    Base.metadata.create_all(bind=engine)

    print("Applying additive schema updates...")
    with engine.begin() as conn:
        add_column_if_missing(conn, "messages", "sources_json", "sources_json TEXT NULL")
        add_column_if_missing(conn, "feedbacks", "severity", "severity VARCHAR DEFAULT 'Low'")
        add_column_if_missing(conn, "feedbacks", "resolved", "resolved BOOLEAN DEFAULT FALSE")
        add_column_if_missing(conn, "feedbacks", "reason", "reason TEXT NULL")

    print("Database migration complete.")


if __name__ == "__main__":
    run()
