from groq import Groq
from config import GROQ_API_KEY, MODEL

MAX_SOURCES = 2
MAX_CHARS_PER_FIELD = 350
MAX_OUTPUT_TOKENS = 400


client = Groq(api_key=GROQ_API_KEY)

CHAT_SYSTEM_PROMPT = """
You are a polite, concise Islamic assistant.

Rules:
- Do NOT greet with Salam or repeat greetings.
- Answer naturally and helpfully.
- Do NOT invent religious rulings or hadith.
- If the question is religious, keep the answer high-level.
"""

RELIGIOUS_SYSTEM_PROMPT = """
You are an Islamic knowledge assistant.

Rules:
- You may ONLY answer using the provided sources.
- You must NOT invent hadith, verses, or rulings.
- If sources do not clearly answer the question, say so.
- Every answer MUST cite its source.
"""

def truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    return text[:limit]


def generate_chat_response(user_question: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": user_question}
        ],
        temperature=0.7,
        max_tokens=300
    )

    return response.choices[0].message.content

def generate_knowledgeBase_answer(question: str, sources: list):
    if not sources:
        return {
            "answer": "I cannot answer this based on the available sources.",
            "sources": []
        }
    
    limited_sources = sources[:MAX_SOURCES]

    sources_text = "\n".join(
        f"Source {i+1}:\n"
        f"Collection: {s.get('collection', 'Unknown')}\n"
        f"Narrator: {s.get('narrator', 'Unknown')}\n"
        f"Text (English): {truncate(s.get('english', ''), MAX_CHARS_PER_FIELD)}"
        for i, s in enumerate(limited_sources)
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": RELIGIOUS_SYSTEM_PROMPT},
            {
                "role": "user", "content": f"Question:\n{question}\n\nSources:\n{sources_text}"
                        }
                    ],
                    temperature=0.0,
                    max_tokens=MAX_OUTPUT_TOKENS
                )

    return {
        "answer": response.choices[0].message.content,
        "sources": limited_sources
    }