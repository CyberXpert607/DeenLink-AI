from groq import Groq
import json
from config import GROQ_API_KEY, MODEL
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv

load_dotenv()

client = Groq(
    max_retries=3,
)

CLASSIFIER_PROMPT = """
You are an intent classifier for an islamic AI system.

Classify the user's message into ONE of these labels:

-chat -> general conversation, no religious sourcing required
-rag_quran -> explicity wants Quran verses
-rag_hadith -> explicitly wants hadith
-motivation -> wants encouragement, life advice, patience, hope, reassurance USING islamic sources
-ambiguous -> unclear intent, needs clarification

Rules:
-If user asks "what dies islam say about X -> motivation
-If user mentions verse, ayah, surah -> rag_quran
-If user mentions hadith, narrator, Bukhari, Muslim -> rag_hadith
-If user is vague -> ambiguous

Respond ONLY in JSON ONLY.
Do not include maarkdown, comments, or extra text.

Schema:
{
"intent": "chat | rag_quran | rag_hadith | motivation | ambiguous",
"confidence": number,
"reason": "string"
}
"""

ALLOWED_INTENTS = {
    "chat",
    "rag_quran",
    "rag_hadith",
    "motivation",
    "ambiguous",
}

async def classify_query_llm(text: str) -> dict:

    def call_llm():
        return client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0
        )
    try:
        response = await run_in_threadpool(call_llm)
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

    except Exception:
        result = {
            "intent": "ambiguous",
            "confidence": 0.0,
            "reason": "LLM error or invalid JSON",
        }

    if result.get("intent") not in ALLOWED_INTENTS:
            result["intent"] = "ambiguous"
            result["confidence"] = 0.0
        
    try:
            result["confidence"] = float(result.get("confidence", 0))
            result["confidence"] = max(0.0, min(1.0, result["confidence"]))

    except Exception:
            result["confidence"] = 0.0

    return result
