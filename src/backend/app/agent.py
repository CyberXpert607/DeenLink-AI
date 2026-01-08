from groq import Groq
from config import GROQ_API_KEY, MODEL

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are a STRICT Islamic assistant.

RULES:
- You may ONLY answer using the provided evidence.
- If evidence is insufficient, say:
  "I cannot answer this based on the available sources."
- NEVER fabricate Quran verses or Hadith.
- Provide Arabic text first, then English translation.
- Cite references clearly.
"""

def generate_answer(question: str, evidence: list):
    if not evidence:
        return "I cannot answer this based on the available sources."

    context = "\n\n".join(
        f"Arabic: {e['text_ar']}\nEnglish: {e['text_en']}\nRef: {e['reference']}"
        for e in evidence
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nEvidence:\n{context}"}
        ]
    )

    return response.choices[0].message.content
