import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "openai/gpt-oss-120b"
AI_JWT_ISS= os.getenv("AI_JWT_ISS")
AI_JWT_AUD = os.getenv("AI_JWT_AUD")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://deenlink.org").split(",")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_JWT_SECRET = os.getenv("ADMIN_JWT_SECRET")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "islamic_sources")

STELLAR_PAYMENTS_ENABLED = os.getenv("STELLAR_PAYMENTS_ENABLED", "false").lower() == "true"
STELLAR_NETWORK = os.getenv("STELLAR_NETWORK", "testnet")
STELLAR_PLATFORM_PUBLIC_KEY = os.getenv("STELLAR_PLATFORM_PUBLIC_KEY")

key_path = Path(__file__).parent / "v2" / "keys" / "public.pem"
with open(key_path, "r") as f:
    AI_JWT_PUBLIC_KEY = f.read()
