from groq import Groq
import logging
from config import MODEL
from v2.prompts import RAG_SYSTEM_PROMPT

client = Groq()

def stream_rag_answer(question: str, retrieved_docs: list):
    try:
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
            payload = doc.payload
            if payload.get("source_type") == "hadith":
                sources_blocks.append(f"""
    Collection: {payload.get('collection', 'Unknown')}
    Narrator: {payload.get('narrator', 'Unknown')}
    Arabic: {payload.get('arabic', 'Unknown')}
    English: {payload.get('english', 'Unknown')}
    """)
                
            elif payload.get("source_type") == "quran":
                sources_blocks.append(f"""
    Qur'an
    Surah: {payload.get('surah_name', 'Unknown')}
    Ayah: {payload.get('ayah', 'Unknown')}
    Arabic: {payload.get('arabic', 'Unknown')}
    English: {payload.get('english', 'Unknown')}
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
            delta = chunk.choices[0].delta.content
            if delta:
                yield {
                    "type": "token",
                    "content": delta
                }

        # After stream ends → send sources separately
        yield {
            "type": "sources",
            "sources": [
        {
            "content": d.content,
            "score": d.score,
            "source_type": d.source_type,
            "payload": d.payload
        } 
        for d in strong_hits
    ]
}
    except Exception as e:
        logging.error(f"Error in RAG answer generation: {e}")
        yield {
            "type": "final",
            "answer_html": "Unable to generate response. Please try again.",
            "sources": []
        }
