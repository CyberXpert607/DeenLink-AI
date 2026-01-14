from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from v1.api import router as router_v1
from v2.api import router as router_v2

app = FastAPI(title="DeenLink AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #this is just for dev, of course :0
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router_v1)
app.include_router(router_v2)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)