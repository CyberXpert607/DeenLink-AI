from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
import uvicorn
import time
import os
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
