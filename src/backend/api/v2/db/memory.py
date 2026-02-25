from v2.db.models import Message

MAX_RECENT = 12

def build_prompt_with_memory(db, conversation):

    messages = []


    messages.append({
        "role": "system",
        "content": "You are DeenLink AI assistant."
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
