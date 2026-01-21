from groq import Groq
from config import GROQ_API_KEY, MODEL
from v2.prompts import CHAT_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT

client = Groq(api_key=GROQ_API_KEY)

def generate_chat_response(user_question: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": user_question}
        ],
        temperature=0.0
    )
    return response.choices[0].message.content


def generate_rag_answer(question: str, retrieved_docs: list):
    retrieved_docs = retrieved_docs[:3]

    if not retrieved_docs:
        return {
            "answer_html": "I could not find any authentic sources that directly answer this question.",
            "sources": []
        }

    sources_blocks = []

    for doc in retrieved_docs:
        if doc["source_type"] == "hadith":
            sources_blocks.append(f"""
            Collection: {doc['collection']}
            Narrator: {doc.get('narrator', 'Unknown')}
            Arabic: {doc['arabic']}
            English: {doc['english']}
            """)

        elif doc["source_type"] == "quran":
            sources_blocks.append(f"""
            Qur'an
            Surah: {doc['surah_name']}
            Ayah: {doc['ayah']}
            Arabic: {doc['arabic']}
            English: {doc['english']}
            """)

    sources_text = "\n\n".join(sources_blocks)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": f""" Question: {question} Sources: {sources_text}"""}
        ],
        temperature=0.0
    )

    return {
        "answer_html": response.choices[0].message.content,
        "sources": retrieved_docs
    }
