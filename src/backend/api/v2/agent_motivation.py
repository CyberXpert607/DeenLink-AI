from groq import Groq
from config import MODEL

client = Groq(timeout=120.0)

MOTIVATION_PROMPT = """
You are an Islamic motivational assistant.

Rules:
- Only use the provided Quran or Hadith sources.
- Never fabricate Islamic content.
- Be compassionate and encouraging.
"""


def format_hadith_reference(payload: dict) -> str:
    """Format hadith reference for display"""
    parts = []
    
    collection = payload.get('collection', 'Hadith')
    parts.append(collection)
    
    hadith_ref = payload.get('hadith_number_display')
    if hadith_ref:
        parts.append(hadith_ref)
    
    # Add chapter info if available
    chapter = payload.get('chapter_name_en') or payload.get('chapter_name_ar')
    if chapter:
        parts.append(chapter[:50])
    
    # Add grade
    grade = payload.get('grade', '')
    if grade and grade != 'Unknown':
        parts.append(f"({grade})")
    
    return " · ".join(parts)


def stream_motivation_answer(query: str, sources: list):

    strong_hits = sorted(
        sources,
        key=lambda x: x.score,
        reverse=True
    )[:3]

    source_blocks = []

    for s in strong_hits:
        payload = s.payload

        if payload.get("source_type") == "quran":
            block = f"""
Qur'an
Surah: {payload.get('surah_name', 'Unknown')}
Ayah: {payload.get('ayah', 'Unknown')}

Arabic:
{payload.get('arabic', 'N/A')[:500]}...

English:
{payload.get('english', 'N/A')[:500]}...
"""
        else:  # Hadith
            reference = format_hadith_reference(payload)
            narrator = payload.get('narrator', 'Not specified')
            grade = payload.get('grade', 'Unknown')
            
            block = f"""
{reference}
Narrator: {narrator}
Grade: {grade}

Arabic:
{payload.get('arabic', 'N/A')[:500]}...

English:
{payload.get('english', 'N/A')[:500]}...
"""
        source_blocks.append(block)

    sources_text = "\n\n---\n\n".join(source_blocks)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": MOTIVATION_PROMPT},
            {
                "role": "user",
                "content": f"Question: {query}\n\nSources:\n{sources_text}"
            }
        ],
        temperature=0.2,
        stream=True
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield {
                "type": "token",
                "content": delta
            }

    yield {
        "type": "sources",
        "sources": [
            {
                "content": s.content,
                "score": s.score,
                "source_type": s.source_type,
                "payload": s.payload,
                "display_reference": format_hadith_reference(s.payload) if s.source_type == "hadith" else None
            } 
            for s in strong_hits
        ]
    }