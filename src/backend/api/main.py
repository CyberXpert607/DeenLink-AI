import sys
import os

# Ensure current directory is in sys.path so sibling imports work when invoked from root
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
import uvicorn
import time
from fastapi.responses import FileResponse
import config
from config import ALLOWED_ORIGINS, STELLAR_PAYMENTS_ENABLED
from v2.db.database import engine
from v2.db.models import Base
from fastapi.middleware.cors import CORSMiddleware
from v2.api import router as router_v2
from v2.stellar.routes import router as stellar_router
from metrics import SYSTEM_METRICS

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="DeenLink AI", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

@app.middleware("http")
async def track_metrics(request: Request, call_next):
    SYSTEM_METRICS["total_requests"] += 1
    start_time = time.time()
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            SYSTEM_METRICS["total_errors"] += 1
        return response
    except Exception as e:
        SYSTEM_METRICS["total_errors"] += 1
        raise e
    finally:
        latency = (time.time() - start_time) * 1000
        SYSTEM_METRICS["total_latency_ms"] += latency


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS, 
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(router_v2)
app.include_router(router_v2, prefix="/api")

if STELLAR_PAYMENTS_ENABLED:
    app.include_router(stellar_router, prefix="/api")
    app.include_router(stellar_router, prefix="/api/v2")

@app.get("/api/config/features")
async def get_features():
    return {
        "stellar_payments": config.STELLAR_PAYMENTS_ENABLED
    }

@app.get("/.well-known/stellar.toml")
async def get_stellar_toml():
    from fastapi.responses import PlainTextResponse
    if not config.STELLAR_PAYMENTS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")
    
    toml_content = f"""
[[ACCOUNTS]]
SIGNING_KEY="{config.STELLAR_PLATFORM_PUBLIC_KEY}"
"""
    return PlainTextResponse(content=toml_content)

@app.get("/admin/dashboard")
async def serve_dashboard():
    return FileResponse("src/backend/api/static/dashboard.html")

# ---------------------------------------------------------------------------
# Local-dev token endpoint
# Mints a short-lived RS256 JWT using the same key pair as production so the
# frontend can authenticate against this FastAPI backend without needing the
# PHP token service.
# ONLY active when IS_LOCAL_DEV=true in .env — never enabled in production.
# ---------------------------------------------------------------------------
_IS_LOCAL_DEV = os.getenv("IS_LOCAL_DEV", "false").lower() == "true"

if _IS_LOCAL_DEV:
    from fastapi.responses import JSONResponse
    from pathlib import Path
    import jwt as _jwt
    from datetime import datetime, timedelta, timezone

    _DEV_PRIVATE_KEY_PATH = os.getenv("DEV_JWT_PRIVATE_KEY_PATH", "")

    @app.post("/api/auth/ai_token.php")
    async def dev_mint_token():
        """
        Mint a short-lived RS256 JWT for local development.
        Requires DEV_JWT_PRIVATE_KEY_PATH in .env pointing to the RSA private key.
        """
        if not _DEV_PRIVATE_KEY_PATH:
            raise HTTPException(
                status_code=503,
                detail="DEV_JWT_PRIVATE_KEY_PATH not set in .env"
            )
        key_path = Path(_DEV_PRIVATE_KEY_PATH)
        if not key_path.is_file():
            raise HTTPException(
                status_code=503,
                detail=f"Private key not found at: {_DEV_PRIVATE_KEY_PATH}"
            )
        private_key = key_path.read_text()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "local-dev-user",
            "username": "dev",
            "full_name": "Local Dev",
            "user_type": "admin",
            "iss": config.AI_JWT_ISS,
            "aud": config.AI_JWT_AUD,
            "iat": now,
            "exp": now + timedelta(minutes=30),
        }
        token = _jwt.encode(payload, private_key, algorithm="RS256")
        return JSONResponse({"ai_jwt": token})

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
