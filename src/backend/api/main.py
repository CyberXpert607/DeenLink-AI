from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import uvicorn
import time
from fastapi.responses import FileResponse
import sys
from pathlib import Path
# Add the directory containing config.py to sys.path (absolute path)
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
from config import ALLOWED_ORIGINS
from v2.db.database import engine
from v2.db.models import Base
from fastapi.middleware.cors import CORSMiddleware
from v2.api import router as router_v2
from metrics import SYSTEM_METRICS

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="DeenLink AI", lifespan=lifespan)

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

@app.get("/admin/dashboard")
async def serve_dashboard():
    return FileResponse("src/backend/api/static/dashboard.html")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
