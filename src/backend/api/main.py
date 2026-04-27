from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn
from fastapi.responses import FileResponse
from config import ALLOWED_ORIGINS
from v2.db.database import engine
from v2.db.models import Base
from fastapi.middleware.cors import CORSMiddleware
from v2.api import router as router_v2

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="DeenLink AI", lifespan=lifespan)

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
