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

def generate_answer(user_question: str, evidence: None, mode="knowledge") -> str:
    
    if mode == "chat":
        prompt = f"""
        You are Usman a friendly DeenLink Islamic APP assistant.
        You may engage in casual conversation.
        Do not issue religious rulings.
        Keep responses short and polite.

        User: {user_question}
        Assistant:
        """
    else:
        sources_text = "\n\n".join(
            f"- {e['arabic']} ({e.get('translation', '')})"
            for e in evidence
        )

        prompt = f"""
        Answer ONLY using the provided sources.
        Do not add external information.

        Question:
        {user_question}

        Sources:
        {sources_text}

        Answer with:
        • Arabic evidence
        • English translation
        • Clear explanation
        """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3 if mode == "knowledge" else 0.7,
    )
    return response.choices[0].message.content.strip()