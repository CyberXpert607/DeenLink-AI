import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
AI_JWT_ISS= os.getenv("AI_JWT_ISS")
AI_JWT_AUD = os.getenv("AI_JWT_AUD")
DATABASE_URL = os.getenv("DATABASE_URL")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://deenlink.org").split(",")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

key_path = Path(__file__).parent / "v2" / "keys" / "public.pem"
with open(key_path, "r") as f:
    AI_JWT_PUBLIC_KEY = f.read()