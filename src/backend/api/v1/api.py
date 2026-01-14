from fastapi import APIRouter
from v1.classifier import classify_topic
from pydantic import BaseModel
from v1.retrieval import retrieve_evidence
from v1.agent import generate_knowledgeBase_answer, generate_chat_response

router = APIRouter(prefix="/api/v1", tags=["Deenlink v1"])


class AskRequest(BaseModel):
    message: str

@router.post("/ask")
async def ask(payload: AskRequest):
    message = payload.message
    topic = classify_topic(message)

    if topic == "chat":
        answer = generate_chat_response(message)
        return {
            "answer_html": answer,
            "sources": []
        }
    

    MAX_EVIDENCE = 2

    evidence, confidence = retrieve_evidence(topic, message)

    evidence = evidence[:MAX_EVIDENCE]
    
    if confidence < 0.65:
        return {
            "answer_html": "I couldn’t find a reliable source that answers this question.",
            "sources": []
        }

    result = generate_knowledgeBase_answer(message, evidence)

    return {
        "answer_html": result["answer"],
        "sources": result["sources"]
    }

@router.get("/health")
def check_health():
    return {
        "status" : "okay"
    }