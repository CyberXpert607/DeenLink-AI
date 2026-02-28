from groq import Groq
from config import MODEL
from v2.prompts import RAG_SYSTEM_PROMPT

client = Groq()

def stream_rag_answer(question: str, retrieved_docs: list):
    strong_hits = [d for d in retrieved_docs if d.score >= 0.30]

    if not strong_hits:
        yield {
            "type": "final",
            "answer_html": (
                "The available sources do not directly answer this question."
            ),
            "sources": []
        }
        return

    strong_hits = strong_hits[:3]

    sources_blocks = []

    for doc in strong_hits:
        if doc.source_type == "hadith":
            sources_blocks.append(f"""
Collection: {doc.collection or 'Unknown'}
Narrator: {doc.narrator or 'Unknown'}
Arabic: {doc.arabic}
English: {doc.english}
""")
            
        elif doc.source_type == "quran":
            sources_blocks.append(f"""
Qur'an
Surah: {doc.surah_name}
Ayah: {doc.ayah}
Arabic: {doc.arabic}
English: {doc.english}
""")

    sources_text = "\n\n".join(sources_blocks)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\nSources:\n{sources_text}"}
        ],
        temperature=0.0,
        stream=True
    )

    # Stream tokens
    for chunk in stream:
        delta_obj = chunk.choices[0].delta.content
        if hasattr(delta_obj, "content") and delta_obj.content:
            yield {
                "type": "token",
                "content": delta_obj.content
            }

    # After stream ends → send sources separately
    yield {
        "type": "sources",
        "sources": [d.model_dump() for d in strong_hits]
    }
