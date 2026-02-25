from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json
import uuid

from v2.db.database import get_db
from v2.auth import verify_jwt
from v2.db.models import Conversation, Message
from v2.db.memory import build_prompt_with_memory
from v2.llm_classify import classify_query_llm
from v2.agent import stream_chat_response
from v2.agent_stream import stream_rag_answer
from v2.agent_motivation import stream_motivation_answer
from v2.vectoreStore import search_similar


router = APIRouter(prefix="/api/v2", tags=["DeenLink AI v2"])


class AskRequest(BaseModel):
    conversation_id: str
    message: str

@router.post("/ask/stream")
async def ask_stream(
    payload: AskRequest,
    user=Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    user_id = user["user_id"]
    query = payload.message.strip()

    convo = (
        db.query(Conversation)
        .filter(
            Conversation.id == payload.conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save user message
    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=convo.id,
        role="user",
        content=query,
    )
    db.add(user_msg)
    db.commit()

    classification = await classify_query_llm(query)
    intent = classification["intent"]

    def event_stream():
        full_response = ""


        # RAG (Quran and Hadith)

        if intent in {"rag_quran", "rag_hadith"}:
            results = search_similar(query, 5)

            filtered = [
                r for r in results
                if r.score >= 0.30 and
                (intent != "rag_quran" or r.source_type == "quran") and
                (intent != "rag_hadith" or r.source_type == "hadith")
            ]

            for chunk in stream_rag_answer(query, filtered):
                full_response += chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
                yield f"data: {json.dumps(chunk)}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        # MOTIVATION

        elif intent == "motivation":

            results = search_similar(query, 5)  # same as RAG
            filtered = [r for r in results if r.score >= 0.3]


            for token in stream_motivation_answer(query, filtered):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"


        # CHAT (default)

        else:
            messages = build_prompt_with_memory(db, convo)

            for token in stream_chat_response(messages):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        # Save assistant message
        assistant_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=convo.id,
            role="assistant",
            content=full_response,
        )
        db.add(assistant_msg)

        # Generate title if first message
        if convo.title == "New Chat":
           new_title = full_response.strip()[:40]
           convo.title = new_title
           db.commit()

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )


#list conversations.

@router.get("/conversations")
def list_conversations(
    user=Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    user_id = user["user_id"]

    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .all()
    )

    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at,
        }
        for c in conversations
    ]

# GET CONVERSATION MESSAGES

@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    user=Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    convo = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user["user_id"],
        )
        .first()
    )

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == convo.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return {
        "id": convo.id,
        "title": convo.title,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }

@router.post("/conversations/new")
def create_new_conversation(user=Depends(verify_jwt), db: Session = Depends(get_db)):
    user_id = user["user_id"]
    conv_id = str(uuid.uuid4())  # generate UUID for the new conversation

    convo = Conversation(
        id=conv_id,
        user_id=user_id,
        title="New Chat" # temporary title
    )
    db.add(convo)
    db.commit()

    return {"conversation_id": conv_id, "title": convo.title}

# DELETE CONVERSATION

@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user=Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    convo = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user["user_id"],
        )
        .first()
    )

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(convo)
    db.commit()

    return {"success": True}