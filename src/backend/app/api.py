from fastapi import APIRouter
from classifier import classify_topic
from retrieval import retrieve_evidence
from agent import generate_answer
from inngest import log_event

router = APIRouter()

@router.post("/ask")
async def ask(payload: dict):
    message = payload.get("message", "")

    topic = classify_topic(message)

    if topic == "unknown":
        return {
            "answer_html": "Hello! How can I help you today?"
        }

    evidence = retrieve_evidence(topic, message)
    answer = generate_answer(message, evidence)

    log_event({
        "topic": topic,
        "question": message
    })

    return {
        "answer_html": answer,
        "topic": topic
    }
