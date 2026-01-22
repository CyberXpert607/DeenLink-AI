from fastapi import APIRouter
from pydantic import BaseModel, Field

from v2.vectoreStore import search_similar
from v2.agent import generate_rag_answer, generate_chat_response
from v2.classifier import classify_query

router = APIRouter(prefix="/api/v2", tags=["DeenLink AI v2"])

class AskRequest(BaseModel):
    message: str = Field(default=None, max_length=100, min_length=1) #adjust this depending on how much char users can send!

@router.post("/ask")
async def ask_v2(payload: AskRequest):
    query = payload.message
    try:

        print(f"[Ask V2 Query]: {query}")

        mode = classify_query(query)
        if mode in ("general_chat", "chat"):
            answer = generate_chat_response(query)
            print("[router chat mode]")

            return {
                "answer_html": answer,
                "sources": []
            }
        
        print("[Router RAG MODE]")
        if mode in ("quran", "hadith"):
            results = search_similar(query, limit=5)

            filtered = [r for r in results if r['score'] >= 0.30]

            if not filtered:
                return {
                    "answer_html": "I could not find authentic sources that directly answer this question.",
                    "sources": []
                }
            results = generate_rag_answer(query, filtered)
            return results
    except Exception as e:
        print("API ERROR:", e)
        return {
            "answer_html": "Something went wrong while processing your request.",
            "sources": []
        }

@router.get("/health")
async def get_health():
    return {
        "status": "okay"
    }