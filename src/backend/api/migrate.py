import asyncio
from sqlalchemy import text
from v2.db.database import SessionLocal, engine

def upgrade_feedbacks_table():
    print("Upgrading database schema...")
    db = SessionLocal()
    try:
        # Check if columns exist
        db.execute(text("ALTER TABLE feedbacks ADD COLUMN severity VARCHAR DEFAULT 'Low';"))
        db.execute(text("ALTER TABLE feedbacks ADD COLUMN resolved BOOLEAN DEFAULT FALSE;"))
        db.commit()
        print("Successfully added severity and resolved columns to feedbacks table!")
    except Exception as e:
        print(f"Error (columns might already exist): {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    upgrade_feedbacks_table()
