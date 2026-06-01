from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

try:
	from ...config import DATABASE_URL
except ImportError:
	from config import DATABASE_URL


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()

def get_db():
	db = SessionLocal()
	try:
		yield db
	finally: 
		db.close()
