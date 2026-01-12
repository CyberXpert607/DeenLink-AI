from groq import Groq
from api.config import GROQ_API_KEY, MODEL
from .prompts import CHAT_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT

client = Groq(api_key=GROQ_API_KEY)

def generate_chat_response(user_question: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": user_question}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content


def generate_rag_answer(question: str, retrieved_docs: list):
    if not retrieved_docs:
        return {
            "answer": (
                "I could not find any authentic sources that directly answer this question."
            ),
            "sources": []
        }

    sources_text = "\n\n".join(
        f"""
Collection: {doc['collection']}
Narrator: {doc.get('narrator', 'Unknown')}
Arabic:
{doc['arabic']}

English:
{doc['english']}
"""
        for doc in retrieved_docs
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""
Question:
{question}

Sources:
{sources_text}
"""
            }
        ],
        temperature=0.0
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": retrieved_docs
    }
