import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from logging import getLogger
import json
import uuid

from v2.db.database import get_db, SessionLocal
from v2.auth import verify_jwt
from v2.db.models import Conversation, Message
from v2.db.memory import build_prompt_with_memory
from v2.llm_classify import classify_query_llm
from v2.agent import stream_chat_response
from v2.agent_stream import stream_rag_answer
from v2.agent_motivation import stream_motivation_answer
from v2.vectoreStore import search_similar


router = APIRouter(prefix="/api/v2", tags=["DeenLink AI v2"])
logging = getLogger(__name__)

class AskRequest(BaseModel):
    conversation_id: str
    message: str


def save_messages_sync(conversation_id: str, user_id: str, query: str, response: str, title_update: str = None):

    db = SessionLocal()
    try:
        convo = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        
        if not convo:
            logging.error(f"Conversation {conversation_id} not found for user {user_id}")
            return
        
        user_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="user",
            content=query,
        )
        db.add(user_msg)
        
        assistant_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=response,
        )
        db.add(assistant_msg)
        
        if title_update and convo.title == "New Chat":
            convo.title = title_update[:40]
        
        db.commit()
        logging.info(f"Successfully saved messages for conversation {conversation_id}")
        
    except Exception as e:
        db.rollback()
        logging.error(f"Error saving messages: {e}")
    finally:
        db.close()


@router.post("/ask/stream")
async def ask_stream(
    payload: AskRequest,
    background_tasks: BackgroundTasks,
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


    if any(kw in query.lower() for kw in ["quran", "ayah", "surah", "verse"]):
        intent = "rag_quran"
    elif any(kw in query.lower() for kw in ["hadith", "prophet", "bukhari", "muslim"]):
        intent = "rag_hadith"
    elif any(kw in query.lower() for kw in ["motivate", "inspire", "encourage"]):
        intent = "motivation"
    else:
        classification = await classify_query_llm(query)
        intent = classification.get("intent")

    memory_messages = None
    conversation_history = []
    
    if intent not in {"rag_quran", "rag_hadith", "motivation"}:
        memory_messages = build_prompt_with_memory(db, convo)

        if memory_messages is None:
            memory_messages = []
        
        memory_messages.append({"role": "user", "content": query})
        logging.info(f"Built memory for conversation {convo.id} with {len(memory_messages)} messages")
    else:
        recent_msgs = (
            db.query(Message)
            .filter(Message.conversation_id == convo.id)
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        conversation_history = [
            {"role": m.role, "content": m.content}
            for m in reversed(recent_msgs)
        ]
        
        conversation_history.append({"role": "user", "content": query})
        logging.info(f"Using conversation history for RAG with {len(conversation_history)} messages")
        
        memory_messages = conversation_history

    current_intent = intent
    current_convo = convo
    current_user_id = user_id
    current_query = query
    
    async def event_stream_async():
        full_response = ""
        disconnected = False
        completed = False
        has_sent_any_token = False
        
        local_memory_messages = memory_messages  
        try:
            # RAG (Quran and Hadith)
            if current_intent in {"rag_quran", "rag_hadith"}:
                results = search_similar(current_query, 10)
                filtered = [r for r in results if r.score >= 0.30]
                
                if current_intent == "rag_quran":
                    quran_hits = [r for r in filtered if r.source_type == "quran"]
                    if quran_hits:
                        filtered = quran_hits
                elif current_intent == "rag_hadith":
                    hadith_hits = [r for r in filtered if r.source_type == "hadith"]
                    if hadith_hits:
                        filtered = hadith_hits

                if not filtered:
                    fallback_msg = "No relevant information found in the knowledge base. Here's a general response instead."
                    full_response += fallback_msg
                    yield f"data: {json.dumps({'type': 'token', 'content': fallback_msg})}\n\n"
                    has_sent_any_token = True
                else:
                    for chunk in stream_rag_answer(current_query, filtered):
                        if disconnected:
                            break
                            
                        if not isinstance(chunk, dict):
                            chunk_str = str(chunk)
                            full_response += chunk_str
                            yield f"data: {json.dumps({'type': 'unknown', 'content': chunk_str})}\n\n"
                            has_sent_any_token = True
                            continue
                            
                        chunk_type = chunk.get("type")
                        if chunk_type == "token":
                            content = chunk.get("content", "")
                            full_response += content
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                            has_sent_any_token = True
                        elif chunk_type == "sources":
                            yield f"data: {json.dumps(chunk)}\n\n"
                        elif chunk_type == "final":
                            yield f"data: {json.dumps(chunk)}\n\n"

            elif current_intent == "motivation":
                results = search_similar(current_query, 5)
                filtered = [r for r in results if r.score >= 0.3]

                if not filtered:
                    fallback_msg = "No relevant motivational content found. Here's a general motivational response instead."
                    full_response += fallback_msg
                    yield f"data: {json.dumps({'type': 'token', 'content': fallback_msg})}\n\n"
                    has_sent_any_token = True
                else:
                    for chunk in stream_motivation_answer(current_query, filtered):
                        if disconnected:
                            break
                        if not isinstance(chunk, dict):
                            continue
                        chunk_type = chunk.get("type")
                        if chunk_type == "token":
                            content = chunk.get("content", "")
                            full_response += content
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                            has_sent_any_token = True
                        elif chunk_type == "sources":
                            yield f"data: {json.dumps(chunk)}\n\n"
                        elif chunk_type == "final":
                            yield f"data: {json.dumps(chunk)}\n\n"

            else:

                if not local_memory_messages or len(local_memory_messages) == 0:
                    local_memory_messages = [
                        {"role": "system", "content": "You are a helpful AI assistant."},
                        {"role": "user", "content": current_query}
                    ]
                    logging.warning(f"memory_messages was empty, created fallback with {len(local_memory_messages)} messages")
                
                logging.info(f"Streaming chat with {len(local_memory_messages)} messages")
                token_count = 0
                
                for token in stream_chat_response(local_memory_messages):
                    if disconnected:
                        break
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                    has_sent_any_token = True
                    token_count += 1
                
                logging.info(f"Streamed {token_count} tokens for query: {current_query[:50]}")

            if not has_sent_any_token:
                fallback_msg = "I'm sorry, I couldn't generate a response. Please try again."
                full_response = fallback_msg
                yield f"data: {json.dumps({'type': 'token', 'content': fallback_msg})}\n\n"

            if not disconnected:
                completed = True

        except asyncio.CancelledError:
            disconnected = True
            logging.info("Client disconnected from stream (CancelledError)")
            try:
                yield f"data: {json.dumps({'done': True})}\n\n"
            except:
                pass
            
        except Exception as e:
            logging.error(f"Error in stream: {e}", exc_info=True)
            if not disconnected:
                error_msg = f"An error occurred while processing your request: {str(e)}"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                full_response = error_msg
            
        finally:
            try:
                yield f"data: {json.dumps({'done': True})}\n\n"
            except:
                pass
            
            if completed and full_response.strip() and not disconnected:
                title_update = current_query if current_convo.title == "New Chat" else None
                
                background_tasks.add_task(
                    save_messages_sync,
                    conversation_id=current_convo.id,
                    user_id=current_user_id,
                    query=current_query,
                    response=full_response,
                    title_update=title_update
                )
                logging.info(f"Scheduled background save for conversation {current_convo.id}")
            else:
                logging.info(f"Not saving - completed: {completed}, has_content: {bool(full_response.strip())}, disconnected: {disconnected}")

    return StreamingResponse(
        event_stream_async(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

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
    conv_id = str(uuid.uuid4()) 

    convo = Conversation(
        id=conv_id,
        user_id=user_id,
        title="New Chat" # temporary title
    )
    db.add(convo)
    db.commit()

    return {"id": conv_id, "title": convo.title}


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