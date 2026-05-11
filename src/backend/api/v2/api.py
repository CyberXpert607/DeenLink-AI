import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse
import os
from sqlalchemy.orm import Session
from pydantic import BaseModel
from logging import getLogger
import json
import uuid

from v2.db.database import get_db, SessionLocal
from v2.auth import verify_jwt
from v2.db.models import Conversation, Message, Feedback, UserMemory
from v2.db.memory import build_prompt_with_memory
from v2.llm_classify import classify_query_llm
from v2.agent import stream_chat_response
from v2.agent_stream import stream_rag_answer
from v2.agent_motivation import stream_motivation_answer
from v2.vectoreStore import search_similar
from v2.prompts import CHAT_SYSTEM_PROMPT
from v2.agent_search import stream_web_search_answer
import datetime


router = APIRouter(prefix="/api/v2", tags=["DeenLink AI v2"])
logging = getLogger(__name__)

class AskRequest(BaseModel):
    conversation_id: str
    message: str
    mode: str = "auto"
    client_datetime: str = ""    # e.g. "Sunday, 11 May 2026, 01:32:00 AM"
    client_timezone: str = ""    # e.g. "Africa/Lagos" or "WAT (UTC+1)"

class EditMessageRequest(BaseModel):
    message_id: str
    message: str

def format_source_display(payload: dict) -> str:
    if payload.get("source_type") == "hadith":
        parts = []
        
        collection = payload.get("collection", "")
        if collection:
            parts.append(collection)
        
        hadith_ref = payload.get("hadith_number_display")
        if hadith_ref:
            parts.append(hadith_ref)
        
        chapter = payload.get("chapter_name_en") or payload.get("chapter_name_ar")
        if chapter:
            parts.append(chapter[:40])
        
        grade = payload.get("grade")
        if grade and grade != "Unknown":
            parts.append(grade)
        
        return " · ".join(parts) if parts else "Hadith"
    
    elif payload.get("source_type") == "quran":
        surah = payload.get("surah_name", "")
        ayah = payload.get("ayah", "")
        if surah and ayah:
            return f"Qur'an {surah}:{ayah}"
        return "Qur'an"
    
    return "Islamic Source"

def save_messages_sync(
    conversation_id: str,
    user_id: str,
    query: str,
    response: str,
    tokens: int = 0,
    title_update: str = None,
    sources_json: str = None,
):

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
            tokens=0
        )
        db.add(user_msg)
        
        assistant_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=response,
            tokens=tokens,
            sources_json=sources_json,
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


import time

RATE_LIMIT_STORE = {}
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 10

def check_rate_limit(user_id: str):
    now = time.time()
    if user_id not in RATE_LIMIT_STORE:
        RATE_LIMIT_STORE[user_id] = []
    
    RATE_LIMIT_STORE[user_id] = [ts for ts in RATE_LIMIT_STORE[user_id] if now - ts < RATE_LIMIT_WINDOW]
    
    if len(RATE_LIMIT_STORE[user_id]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
        
    RATE_LIMIT_STORE[user_id].append(now)

@router.post("/ask/stream")
async def ask_stream(
    payload: AskRequest,
    background_tasks: BackgroundTasks,
    user=Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    user_id = user["user_id"]
    check_rate_limit(user_id)
    
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

    # ── Client datetime (sent by browser so we always have the user's real local time) ──
    client_datetime = payload.client_datetime.strip()
    client_timezone = payload.client_timezone.strip()

    # ── Fast path: time/date questions — no web search needed ───────────────────────────
    # Detect if this is purely a time/date/day query
    _q = query.lower()
    _datetime_keywords = [
        "what time", "what's the time", "what is the time", "current time",
        "what day", "what's today", "what is today", "today's date", "today date",
        "what date", "current date", "what year", "what month",
        "day is it", "time is it", "date is it", "tell me the time",
    ]
    _is_datetime_query = any(kw in _q for kw in _datetime_keywords)

    if payload.mode == "chat":
        intent = "chat"
    elif payload.mode == "rag":
        intent = "rag_all"
    elif _is_datetime_query and client_datetime:
        # Answer directly from client time — no search needed
        intent = "datetime_direct"
    else:
        # Default to Auto — check keyword shortcuts first (cheap), then LLM classifier
        if any(kw in query.lower() for kw in ["quran", "ayah", "surah", "verse"]):
            intent = "rag_quran"
        elif any(kw in query.lower() for kw in ["hadith", "bukhari", "muslim", "tirmidhi"]):
            intent = "rag_hadith"
        elif any(kw in query.lower() for kw in ["motivate", "inspire", "encourage"]):
            intent = "motivation"
        else:
            # Fetch memories first so classifier can use them
            memories_for_classifier = [
                {"id": m.id, "fact": m.fact}
                for m in db.query(UserMemory).filter(UserMemory.user_id == user_id).all()
            ]
            classification = await classify_query_llm(query, memories_for_classifier)
            intent = classification.get("intent")
    memory_messages = None
    conversation_history = []
    user_memories_list = []  # flat list of {id, fact} for passing to classifier/search
    
    if intent not in {"rag_quran", "rag_hadith", "rag_all", "motivation"}:
        memory_messages = build_prompt_with_memory(db, convo)

        if memory_messages is None:
            memory_messages = []
        
        # Fetch user memories for classifier / search agent
        user_memories_list = [
            {"id": m.id, "fact": m.fact}
            for m in db.query(UserMemory).filter(UserMemory.user_id == user_id).all()
        ]
        
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
    current_user_memories = user_memories_list  # pass to closure
    current_client_datetime = client_datetime
    current_client_timezone = client_timezone
    
    async def event_stream_async():
        full_response = ""
        disconnected = False
        completed = False
        has_sent_any_token = False
        collectedSources = None  # will be populated by 'sources' SSE event
        
        local_memory_messages = memory_messages  
        
        # Launch memory extraction concurrently
        user_history = []
        if local_memory_messages:
            user_history = [{"id": m.id, "fact": m.fact} for m in db.query(UserMemory).filter(UserMemory.user_id == current_user_id).all()]
        
        memory_task = None
        if current_intent in {"chat", "web_search", "ambiguous", "datetime_direct"}:
            from v2.agent_memory import extract_memory_facts
            memory_task = asyncio.create_task(extract_memory_facts(current_query, user_history))
            
        try:
            if current_intent in {"rag_quran", "rag_hadith", "rag_all"}:
                yield f"data: {json.dumps({'type': 'search_start'})}\n\n"
            elif current_intent == "motivation":
                yield f"data: {json.dumps({'type': 'search_start'})}\n\n"
            elif current_intent == "web_search":
                yield f"data: {json.dumps({'type': 'web_search_start'})}\n\n"
            elif current_intent == "datetime_direct":
                yield f"data: {json.dumps({'type': 'chat_start'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'chat_start'})}\n\n"
        
            await asyncio.sleep(0.1)

            if current_intent in {"rag_quran", "rag_hadith", "rag_all"}:
                source_filter = None
                if current_intent == "rag_quran":
                    source_filter = "quran"
                elif current_intent == "rag_hadith":
                    source_filter = "hadith"
                
                results = search_similar(current_query, 10, source_type=source_filter)
                filtered = [r for r in results if r.score >= 0.30]
                
                if not filtered and source_filter:
                    results = search_similar(current_query, 10)
                    filtered = [r for r in results if r.score >= 0.30]
                    if current_intent == "rag_quran":
                        filtered = [r for r in filtered if r.source_type == "quran"]
                    elif current_intent == "rag_hadith":
                        filtered = [r for r in filtered if r.source_type == "hadith"]

                if not filtered:
                    fallback_msg = "No relevant information found in the knowledge base. Please try rephrasing your question."
                    full_response += fallback_msg
                    yield f"data: {json.dumps({'type': 'token', 'content': fallback_msg})}\n\n"
                    has_sent_any_token = True
                else:
                    sources_data = [
                        {
                            "source_type": r.source_type,
                            "score": r.score,
                            "payload": r.payload,
                            "display_reference": format_source_display(r.payload)
                        }
                        for r in filtered
                    ]
                    
                    collectedSources = sources_data  # persist for later save
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
                    
                    rag_context = {
                        "conversation_history": conversation_history[-3:] if conversation_history else [],
                        "intent": current_intent
                    }
                    
                    for chunk in stream_rag_answer(current_query, filtered, rag_context):
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
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"


            elif current_intent == "motivation":
                results = search_similar(current_query, 5)
                filtered = [r for r in results if r.score >= 0.3]

                if not filtered:
                    fallback_msg = "No relevant motivational content found. Here's a general motivational response instead."
                    full_response += fallback_msg
                    yield f"data: {json.dumps({'type': 'token', 'content': fallback_msg})}\n\n"
                    has_sent_any_token = True
                else:
                    sources_data = [{
                        "source_type": r.source_type,
                        "score": r.score,
                        "payload": r.payload,
                        "display_reference": format_source_display(r.payload)
                    } for r in filtered]
                    
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
                    
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

            elif current_intent == "web_search":
                # Pass user memories so the search agent can add them to LLM context
                mem_facts = [m["fact"] for m in current_user_memories] if current_user_memories else []
                for chunk in stream_web_search_answer(current_query, conversation_history, mem_facts):
                    if disconnected:
                        break
                    try:
                        parsed = json.loads(chunk.strip())
                        chunk_type = parsed.get("type")
                        if chunk_type == "token":
                            content = parsed.get("content", "")
                            full_response += content
                            yield f"data: {chunk}\n\n"
                            has_sent_any_token = True
                        elif chunk_type == "sources":
                            collectedSources = parsed.get("sources", [])
                            yield f"data: {chunk}\n\n"
                        elif chunk_type == "done":
                            yield f"data: {chunk}\n\n"
                    except:
                        pass
                        

            elif current_intent == "datetime_direct":
                # Answer instantly using the client's real local time — zero web search
                location_fact = ""
                for m in user_history:
                    fact_lower = m.get("fact", "").lower()
                    if any(kw in fact_lower for kw in ["live in", "based in", "from", "located in"]):
                        location_fact = m["fact"]
                        break

                tz_clause = f" [{current_client_timezone}]" if current_client_timezone else ""
                loc_clause = f"\nThe user's location: {location_fact}." if location_fact else ""

                datetime_system = (
                    f"You are DeenLink AI. Answer the user's time/date question directly.\n"
                    f"The user's exact current local date and time is: {current_client_datetime}{tz_clause}.{loc_clause}\n"
                    f"Reply in 1-2 sentences. State the time and date clearly. No filler words."
                )
                dt_messages = [
                    {"role": "system", "content": datetime_system},
                    {"role": "user", "content": current_query},
                ]
                for token in stream_chat_response(dt_messages):
                    if disconnected:
                        break
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                    has_sent_any_token = True

            else:
                current_date = datetime.datetime.now().strftime("%Y-%m-%d")
                dynamic_system_prompt = f"{CHAT_SYSTEM_PROMPT}\n\nCurrent Date: {current_date}"
                
                if not local_memory_messages or len(local_memory_messages) == 0:
                    local_memory_messages = [
                        {"role": "system", "content": dynamic_system_prompt},
                        {"role": "user", "content": current_query}
                    ]
                    logging.warning(f"memory_messages was empty, created fallback with {len(local_memory_messages)} messages")
                else:
                    # Update system prompt if it exists
                    if local_memory_messages[0]["role"] == "system":
                        local_memory_messages[0]["content"] = dynamic_system_prompt
                
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
                if memory_task:
                    try:
                        mem_result = await memory_task
                        if mem_result and mem_result.get("action") in ["add", "update", "delete"]:
                            action = mem_result["action"]
                            fact = mem_result.get("fact", "")
                            orig_id = mem_result.get("original_memory_id")
                            
                            db_updated = False
                            if action == "add" and fact:
                                new_mem = UserMemory(id=str(uuid.uuid4()), user_id=current_user_id, fact=fact)
                                db.add(new_mem)
                                db_updated = True
                            elif action == "update" and fact and orig_id:
                                existing_mem = db.query(UserMemory).filter(UserMemory.id == orig_id, UserMemory.user_id == current_user_id).first()
                                if existing_mem:
                                    existing_mem.fact = fact
                                    db_updated = True
                            elif action == "delete" and orig_id:
                                existing_mem = db.query(UserMemory).filter(UserMemory.id == orig_id, UserMemory.user_id == current_user_id).first()
                                if existing_mem:
                                    db.delete(existing_mem)
                                    db_updated = True
                            
                            if db_updated:
                                db.commit()
                                yield f"data: {json.dumps({'type': 'memory_updated', 'action': action, 'fact': fact})}\n\n"
                    except Exception as e:
                        logging.error(f"Memory extraction failed: {e}")
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
                estimated_tokens = len(full_response) // 4
                
                # Serialise collected sources for persistence
                saved_sources_json = None
                if collectedSources:
                    try:
                        saved_sources_json = json.dumps(collectedSources)
                    except Exception:
                        pass
                
                background_tasks.add_task(
                    save_messages_sync,
                    conversation_id=current_convo.id,
                    user_id=current_user_id,
                    query=current_query,
                    response=full_response,
                    tokens=estimated_tokens,
                    title_update=title_update,
                    sources_json=saved_sources_json,
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

@router.get("/user/me")
def get_user_profile(user=Depends(verify_jwt)):
    return {
        "user_id": user["user_id"],
        "username": user.get("username", "Guest")
    }

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
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "sources": json.loads(m.sources_json) if m.sources_json else None,
            }
            for m in messages
        ],
    }

@router.post("/conversations/{conversation_id}/edit")
def edit_conversation_from_message(
    conversation_id: str,
    payload: EditMessageRequest,
    user=Depends(verify_jwt),
    db: Session = Depends(get_db),
):
    updated_text = payload.message.strip()
    if not updated_text:
        raise HTTPException(status_code=400, detail="Edited message cannot be empty")

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

    target_msg = (
        db.query(Message)
        .filter(
            Message.id == payload.message_id,
            Message.conversation_id == conversation_id,
            Message.role == "user",
        )
        .first()
    )
    if not target_msg:
        raise HTTPException(status_code=404, detail="User message not found")

    deleted_count = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.created_at >= target_msg.created_at,
        )
        .delete(synchronize_session=False)
    )
    db.commit()

    return {
        "success": True,
        "conversation_id": conversation_id,
        "deleted_messages": deleted_count,
        "edited_message": updated_text,
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

from typing import Optional

class FeedbackRequest(BaseModel):
    conversationId: Optional[str] = None
    type: str
    prompt: str = ""
    response: str = ""
    timestamp: Optional[str] = None
    url: Optional[str] = None
    reason: Optional[str] = None

@router.post("/feedback")
def submit_feedback(payload: FeedbackRequest, user=Depends(verify_jwt), db: Session = Depends(get_db)):
    try:
        from v2.db.models import Feedback
        fb = Feedback(
            id=str(uuid.uuid4()),
            conversation_id=payload.conversationId,
            user_id=user["user_id"],
            type=payload.type,
            prompt=payload.prompt,
            response=payload.response,
            reason=payload.reason,
            severity="High" if payload.reason else "Low"
        )
        db.add(fb)
        db.commit()
        return {"success": True}
    except Exception as e:
        logging.error(f"Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")

@router.get("/admin/dashboard/ui")
def get_dashboard_ui():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dashboard UI not found")

@router.get("/admin/dashboard/data")
def get_dashboard_metrics(user=Depends(verify_jwt), db: Session = Depends(get_db)):
    if user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from v2.db.models import Feedback
    from sqlalchemy import func, text, distinct, or_
    from datetime import datetime, timedelta
    
    from metrics import SYSTEM_METRICS, START_TIME
    import time
    
    #System Health
    total_reqs = SYSTEM_METRICS["total_requests"]
    avg_latency = round(SYSTEM_METRICS["total_latency_ms"] / total_reqs, 1) if total_reqs > 0 else 0
    err_rate = round((SYSTEM_METRICS["total_errors"] / total_reqs) * 100, 2) if total_reqs > 0 else 0
    uptime_seconds = time.time() - START_TIME
    uptime_hours = round(uptime_seconds / 3600, 1)

    system_health = {
        "response_latency_ms": avg_latency,
        "error_rate": err_rate,
        "uptime": uptime_hours
    }
    
    # Avg Messages per Session
    total_convos = db.query(Conversation).count()
    total_msgs = db.query(Message).count()
    avg_msgs_per_session = round(total_msgs / total_convos, 1) if total_convos > 0 else 0
    
    #Active Users (Last 7 Days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_users_7d = db.query(func.count(distinct(Message.conversation_id))).filter(Message.created_at >= seven_days_ago).scalar() or 0
    
    #Token Cost Tracker (Today and Month)
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    first_of_month = today.replace(day=1)
    
    tokens_today = db.query(func.sum(Message.tokens)).filter(Message.created_at >= today).scalar() or 0
    tokens_month = db.query(func.sum(Message.tokens)).filter(Message.created_at >= first_of_month).scalar() or 0
    total_tokens = db.query(func.sum(Message.tokens)).scalar() or 0
    total_feedbacks = db.query(Feedback).count()
    
    #Topic Category Breakdown (Parsing last 500 user messages)
    recent_user_msgs = db.query(Message.content).filter(Message.role == 'user').order_by(Message.created_at.desc()).limit(500).all()
    topics = {"Quran": 0, "Hadith": 0, "Fiqh": 0, "Salah": 0, "Duas": 0, "General": 0}
    for (msg_content,) in recent_user_msgs:
        content_lower = msg_content.lower()
        if any(kw in content_lower for kw in ["quran", "ayah", "surah", "verse"]):
            topics["Quran"] += 1
        elif any(kw in content_lower for kw in ["hadith", "prophet", "bukhari", "muslim", "sunnah"]):
            topics["Hadith"] += 1
        elif any(kw in content_lower for kw in ["fiqh", "fatwa", "halal", "haram", "ruling"]):
            topics["Fiqh"] += 1
        elif any(kw in content_lower for kw in ["salah", "prayer", "wudu", "fajr", "dhuhr", "asr", "maghrib", "isha"]):
            topics["Salah"] += 1
        elif any(kw in content_lower for kw in ["dua", "supplication", "pray for", "forgive"]):
            topics["Duas"] += 1
        else:
            topics["General"] += 1
            
    # Feedback Score Trend (Last 30 Days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    trend_data = {}
    try:
        feedback_trend_query = db.query(
            func.date_trunc('day', Feedback.created_at).label('day'),
            Feedback.type,
            func.count(Feedback.id).label('count')
        ).filter(Feedback.created_at >= thirty_days_ago)\
         .group_by('day', Feedback.type)\
         .order_by('day').all()
         
        for day, fb_type, count in feedback_trend_query:
            day_str = day.strftime('%Y-%m-%d') if isinstance(day, datetime) else str(day)[:10]
            if day_str not in trend_data:
                trend_data[day_str] = {"Successful": 0, "Needs Improvement": 0}
            if fb_type == 'like':
                trend_data[day_str]["Successful"] += count
            else:
                trend_data[day_str]["Needs Improvement"] += count
    except Exception as e:
        logging.error(f"Error executing date_trunc: {e}")
        
    #Popular Queries Panel
    popular_queries_raw = db.query(
        Message.content,
        func.count(Message.id).label('count')
    ).filter(Message.role == 'user')\
     .group_by(Message.content)\
     .order_by(text('count DESC'))\
     .limit(5).all()
     
    popular_queries = [{"query": row[0][:100], "count": row[1]} for row in popular_queries_raw if row[0]]
    
    # Unanswered / Refused Queries
    refusal_phrases = ["I'm sorry, I couldn't generate a response", "No relevant information found", "fallback"]
    refusal_filters = [Message.content.ilike(f"%{phrase}%") for phrase in refusal_phrases]
    
    unanswered_raw = db.query(Message).filter(Message.role == 'assistant', or_(*refusal_filters)).order_by(Message.created_at.desc()).limit(10).all()
    unanswered_queries = []
    for msg in unanswered_raw:
        user_msg = db.query(Message).filter(
            Message.conversation_id == msg.conversation_id,
            Message.role == 'user',
            Message.created_at <= msg.created_at
        ).order_by(Message.created_at.desc()).first()
        
        if user_msg:
            reason = "No relevant knowledge found" if "No relevant information" in msg.content else "Generation failed/Refused"
            unanswered_queries.append({
                "timestamp": msg.created_at.isoformat(),
                "prompt": user_msg.content,
                "reason": reason
            })
            
    #Peak Usage Heatmap (7-day x 24-hour grid)
    heatmap_data = []
    try:
        heatmap_query = db.query(
            func.extract('isodow', Message.created_at).label('day_of_week'),
            func.extract('hour', Message.created_at).label('hour_of_day'),
            func.count(Message.id).label('count')
        ).filter(Message.created_at >= seven_days_ago)\
         .group_by('day_of_week', 'hour_of_day').all()
         
        for dow, hod, count in heatmap_query:
            heatmap_data.append({"day": int(dow), "hour": int(hod), "count": count})
    except Exception as e:
        logging.error(f"Error executing extract: {e}")

    # Feedback tables
    recent_likes = db.query(Feedback).filter(Feedback.type == 'like').order_by(Feedback.created_at.desc()).limit(20).all()
    recent_dislikes = db.query(Feedback).filter(Feedback.type == 'dislike').order_by(Feedback.created_at.desc()).limit(20).all()
    
    def format_fb(fb_list):
        return [
            {
                "id": fb.id,
                "prompt": fb.prompt,
                "response": fb.response,
                "reason": getattr(fb, 'reason', None),
                "severity": getattr(fb, 'severity', 'Low'),
                "resolved": getattr(fb, 'resolved', False),
                "created_at": fb.created_at.isoformat() if fb.created_at else None
            } for fb in fb_list
        ]
    
    return {
        "system_health": system_health,
        "metrics": {
            "avg_messages_per_session": avg_msgs_per_session,
            "active_users_7d": active_users_7d,
            "tokens_today": tokens_today,
            "tokens_month": tokens_month,
            "tokens_total": total_tokens,
            "total_feedbacks": total_feedbacks
        },
        "topic_breakdown": topics,
        "feedback_trend": trend_data,
        "popular_queries": popular_queries,
        "unanswered_queries": unanswered_queries,
        "peak_usage": heatmap_data,
        "recent_likes": format_fb(recent_likes),
        "recent_dislikes": format_fb(recent_dislikes)
    }

class FeedbackUpdateRequest(BaseModel):
    severity: str = None
    resolved: bool = None

@router.patch("/admin/feedback/{feedback_id}")
def update_feedback(feedback_id: str, payload: FeedbackUpdateRequest, user=Depends(verify_jwt), db: Session = Depends(get_db)):
    if user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
        
    from v2.db.models import Feedback
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
        
    if payload.severity is not None:
        fb.severity = payload.severity
    if payload.resolved is not None:
        fb.resolved = payload.resolved
        
    db.commit()
    return {"success": True}

@router.get("/user/memories")
def get_user_memories(user=Depends(verify_jwt), db: Session = Depends(get_db)):
    user_id = str(user.get("user_id"))
    memories = db.query(UserMemory).filter(UserMemory.user_id == user_id).order_by(UserMemory.created_at.desc()).all()
    return [{"id": m.id, "fact": m.fact, "created_at": m.created_at.isoformat()} for m in memories]

@router.delete("/user/memories/{memory_id}")
def delete_user_memory(memory_id: str, user=Depends(verify_jwt), db: Session = Depends(get_db)):
    user_id = str(user.get("user_id"))
    mem = db.query(UserMemory).filter(UserMemory.id == memory_id, UserMemory.user_id == user_id).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(mem)
    db.commit()
    return {"success": True}

@router.delete("/user/memories")
def clear_user_memories(user=Depends(verify_jwt), db: Session = Depends(get_db)):
    user_id = str(user.get("user_id"))
    db.query(UserMemory).filter(UserMemory.user_id == user_id).delete()
    db.commit()
    return {"success": True}