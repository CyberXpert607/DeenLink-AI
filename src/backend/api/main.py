from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn
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
    allow_origins=["http://localhost:5500",
                   "http://127.0.0.1:5500"], 
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(router_v2)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
