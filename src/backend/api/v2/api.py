from fastapi import APIRouter
from pydantic import BaseModel

from v2.vectoreStore import search_similar
from v2.agent import generate_rag_answer
from v2.prompts import RAG_SYSTEM_PROMPT

router = APIRouter(prefix="/api/v2", tags=["RAG v2"])

class AskRequest(BaseModel):
    message: str

@router.post("/ask")
async def ask_v2(payload: AskRequest):
    query = payload.message

    results = search_similar(query, limit=5)

    filtered = [r for r in results if r['score'] >= 0.30]

    if not filtered:
        return {
            "answer_html": "I could not find authentic sources that directly answer this question.",
            "sources": []
        }
    results = generate_rag_answer(query, filtered)

@router.get("/health")
async def get_health():
    return {
        "status": "okay"
    }