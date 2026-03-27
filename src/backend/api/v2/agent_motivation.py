from groq import Groq
from config import MODEL

client = Groq()

MOTIVATION_PROMPT = """
You are an Islamic motivational assistant.

Rules:
- Only use the provided Quran or Hadith sources.
- Never fabricate Islamic content.
- Be compassionate and encouraging.
"""


def stream_motivation_answer(query: str, sources: list):

    if not sources:
        yield {
            "type": "final",
            "answer_html": "No relevant Islamic sources found.",
            "sources": []
        }
        return

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
Surah: {payload.get("surah_name")}
Ayah: {payload.get("ayah")}

Arabic:
{payload.get("arabic")}

English:
{payload.get("english")}
"""

        else:

            block = f"""
Hadith
Collection: {payload.get("collection")}
Narrator: {payload.get("narrator")}

Arabic:
{payload.get("arabic")}

English:
{payload.get("english")}
"""

        source_blocks.append(block)

    sources_text = "\n\n".join(source_blocks)

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
        "sources": [s.payload for s in strong_hits]
    }