from fastapi import APIRouter
from classifier import classify_topic
from pydantic import BaseModel
from retrieval import retrieve_evidence
from agent import generate_answer
from inngest import log_event

class AskRequest(BaseModel):
    message: str

router = APIRouter()

@router.post("/ask")
async def ask(payload: AskRequest):
    message = payload.message

    topic = classify_topic(message)

    if topic == "unknown":
        answer = generate_answer(
            user_question = message,
            evidence=None,
            mode="chat"
        )
        return {
            "answer_html": answer,
            "topic": "chat"
        }
    
#Knowledge restricted mode
    evidence = retrieve_evidence(topic, message)
    if not evidence:
        return {
            "answer_html": "I cannot answer this based on the available sources.",
            "topic": topic
        }
    answer = generate_answer(
        user_question = message,
        evidence= evidence,
        mode = "knowledge"
    )
    log_event({
        "topic": topic,
        "question": message,
        "evidence": len(evidence)
    })

    return {
        "answer_html": answer,
        "topic": topic
    }

@router.get("/health")
async def health():
    return {"status": "ok"}

