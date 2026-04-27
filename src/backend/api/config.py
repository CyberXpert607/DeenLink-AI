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

with open(Path("v2/keys/public.pem"), "r") as f:
    AI_JWT_PUBLIC_KEY = f.read()