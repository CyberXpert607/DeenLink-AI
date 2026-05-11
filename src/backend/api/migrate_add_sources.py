"""
Migration: add sources_json column to messages table.

Run on VPS:
    cd /path/to/deen-ai
    python src/backend/api/migrate_add_sources.py

Safe to run multiple times (checks for column existence first).
"""
import sys
import os

# Ensure the backend src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text, inspect
from v2.db.database import engine


def column_exists(conn, table: str, column: str) -> bool:
    """Check if a column already exists in the table."""
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def run():
    with engine.connect() as conn:
        if column_exists(conn, "messages", "sources_json"):
            print("✅  Column 'sources_json' already exists on 'messages'. Nothing to do.")
            return

        print("⏳  Adding 'sources_json' column to 'messages' table...")
        conn.execute(text("ALTER TABLE messages ADD COLUMN sources_json TEXT NULL"))
        conn.commit()
        print("✅  Migration complete: 'sources_json' column added.")


if __name__ == "__main__":
    run()
