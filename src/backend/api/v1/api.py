from fastapi import APIRouter
from .classifier import classify_topic
from pydantic import BaseModel
from .retrieval import retrieve_evidence
from .agent import generate_knowledgeBase_answer, generate_chat_response
from .inngest import log_event

router = APIRouter(prefix="/api/v1", tags=["v1"])


class AskRequest(BaseModel):
    message: str

@router.post("/ask")
async def ask(payload: AskRequest):
    message = payload.message
    topic = classify_topic(message)

    if topic == "chat":
        answer = generate_chat_response(message)

        log_event({
            "event": "chat_response",
            "message": message
        })

        return {
            "answer_html": answer,
            "sources": []
        }
    
#Knowledge_restricted_mode:
    MAX_EVIDENCE = 2

    evidence, confidence = retrieve_evidence(topic, message)

    evidence = evidence[:MAX_EVIDENCE]
    
    if confidence < 0.65:
        log_event({
            "event": "low_confidence",
            "topic": topic,
            "confidence": confidence
        })

        return {
            "answer_html": "I couldn’t find a reliable source that answers this question.",
            "sources": []
        }

    result = generate_knowledgeBase_answer(message, evidence)

    log_event({
        "event": "answered",
        "topic": topic,
        "confidence": confidence
    })

    return {
        "answer_html": result["answer"],
        "sources": result["sources"]
    }

@router.get("/health")
def check_health():
    return {
        "status": "okay"
    }