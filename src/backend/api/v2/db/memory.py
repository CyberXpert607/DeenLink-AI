from v2.db.models import Message
from v2.prompts import CHAT_SYSTEM_PROMPT

MAX_RECENT = 12

def build_prompt_with_memory(db, conversation):

    messages = []


    messages.append({
        "role": "system",
        "content": CHAT_SYSTEM_PROMPT
    })

    from v2.db.models import UserMemory
    user_memories = db.query(UserMemory).filter(UserMemory.user_id == conversation.user_id).order_by(UserMemory.created_at.asc()).all()
    if user_memories:
        facts = "\n".join([f"- {m.fact}" for m in user_memories])
        memory_content = f"Information about the user based on previous interactions:\n{facts}\n\nUse this information naturally when relevant, but do not state that you are reading from memory."
        messages.append({
            "role": "system",
            "content": memory_content
        })


    if conversation.summary:
        messages.append({
            "role": "system",
            "content": f"Conversation summary:\n{conversation.summary}"
        })

    # recent messages
    recent = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(MAX_RECENT)
        .all()
    )

    for msg in reversed(recent):
        messages.append({
            "role": msg.role,
            "content": msg.content
        })

    return messages
