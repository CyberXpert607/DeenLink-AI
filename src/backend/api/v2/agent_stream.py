from groq import Groq
import logging
from config import MODEL
from v2.prompts import RAG_SYSTEM_PROMPT

client = Groq(timeout=120.0)

def stream_rag_answer(question: str, retrieved_docs: list, context: dict = None):
    try:
        strong_hits = [d for d in retrieved_docs if d.score >= 0.30]

        if not strong_hits:
            yield {
                "type": "final",
                "answer_html": (
                    "<div class='rag-answer'>"
                    "<p class='rag-explanation'>The available sources do not directly answer this question.</p>"
                    "</div>"
                ),
                "sources": []
            }
            return

        strong_hits = strong_hits[:3]
        sources_blocks = []

        for doc in strong_hits:
            payload = doc.payload
            
            if payload.get("source_type") == "hadith":
                collection = payload.get('collection', 'Unknown Collection')
                hadith_ref = payload.get('hadith_number_display', '')
                chapter = payload.get('chapter_name_en') or payload.get('chapter_name_ar') or ''
                chapter_num = payload.get('chapter_number')
                grade = payload.get('grade', 'Unknown')
                narrator = payload.get('narrator', '')
                
                # Build reference line
                ref_parts = [collection]
                if hadith_ref:
                    ref_parts.append(hadith_ref)
                if chapter_num and chapter:
                    ref_parts.append(f"Ch.{chapter_num}: {chapter[:50]}")
                elif chapter:
                    ref_parts.append(chapter[:50])
                
                reference_line = " · ".join(ref_parts)
                
                sources_blocks.append(f"""
{reference_line}
Narrator: {narrator if narrator else 'Not specified'}
Grade: {grade}

Arabic: {payload.get('arabic', 'N/A')[:400]}...

English: {payload.get('english', 'N/A')[:500]}...
""")
                
            elif payload.get("source_type") == "quran":
                sources_blocks.append(f"""
Qur'an
Surah: {payload.get('surah_name', 'Unknown')}
Ayah: {payload.get('ayah', 'Unknown')}
Arabic: {payload.get('arabic', 'Unknown')}
English: {payload.get('english', 'Unknown')}
""")

        sources_text = "\n\n---\n\n".join(sources_blocks)
        
        # Add context if available
        context_prompt = ""
        if context and context.get("conversation_history"):
            context_prompt = "\nPrevious conversation:\n"
            for msg in context["conversation_history"][-2:]:
                context_prompt += f"{msg['role']}: {msg['content']}\n"

        full_prompt = f"Question: {question}{context_prompt}\n\nSources:\n{sources_text}"

        stream = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": RAG_SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt}
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

        # Send sources after streaming
        yield {
            "type": "sources",
            "sources": [
                {
                    "content": d.content,
                    "score": d.score,
                    "source_type": d.source_type,
                    "payload": {
                        **d.payload,
                        "display_reference": f"{d.payload.get('collection', '')} {d.payload.get('hadith_number_display', '')}"
                    }
                } 
                for d in strong_hits
            ]
        }

    except Exception as e:
        logging.error(f"Error in RAG answer generation: {e}")
        yield {
            "type": "final",
            "answer_html": "<div class='rag-answer'><p>Unable to generate response. Please try again.</p></div>",
            "sources": []
        }