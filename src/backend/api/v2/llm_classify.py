from groq import Groq
import json
import re
from config import GROQ_API_KEY, MODEL
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv

load_dotenv()

client = Groq(
    max_retries=3,
)

CLASSIFIER_PROMPT = """
You are an intent classifier for an Islamic AI system.

Classify the user's message into ONE of these labels:

- chat -> general conversation, personal/memory-based questions, no religious sourcing required
- rag_quran -> explicitly wants Quran verses
- rag_hadith -> explicitly wants hadith or prophetic traditions
- rag_all -> asks about Islamic history, prophets, companions, 99 names of Allah
- motivation -> wants encouragement, life advice, patience, hope, reassurance USING Islamic sources
- web_search -> asks for a FATWA, RULING, or PERMISSIBILITY (halal/haram), or needs current news/facts
- ambiguous -> unclear intent, needs clarification

Rules for Hadith Detection:
- User mentions: hadith, sunnah, prophetic tradition, narrated by, collection names (Bukhari, Muslim, Tirmidhi, Nawawi, Shamail, etc.)
- User asks about Prophet Muhammad's sayings, actions, or approvals
- User mentions narrator names (Abu Hurairah, Ibn Umar, Aisha, etc.)
- User asks for specific hadith numbers or chapters

Rules for Quran Detection:
- User mentions: Quran, Qur'an, surah, ayah, verse, recitation
- User asks about specific chapters or verses

Rules for History/Prophets/Expert Knowledge (rag_all):
- User asks about: Prophet names (Adam, Yusuf, Isa, etc.), Companions/Sahaba (Abu Bakr, Umar, etc.), 99 names of Allah
- User asks for stories of prophets or history of early Islam
- User asks for a general fatwa or scholarly ruling

Rules for Motivation:
- User asks "What does Islam say about X?" where X is a life situation
- User expresses distress, sadness, anxiety, or seeks hope
- User asks for encouragement, patience (sabr), trust in Allah (tawakkul)
- User expresses struggle with worship, consistency, habits, or religious duties (e.g., "I struggle with Fajr")

Rules for Web Search:
- User asks for a FATWA, RULING, or RULING on PERMISSIBILITY (e.g., "is it halal?", "can I eat X?")
- User asks "What is the ruling on X?" or "What do scholars say about Y?"
- User needs current/live internet data (dates, news, etc.)
- Do NOT use web_search if the answer is already known from memory

Rules for Chat:
- General conversation, greetings, personal questions that can be answered from the user's stored memories
- Follow-up questions about things the user has already told the AI

{memory_block}

Respond ONLY in JSON format.
Do not include markdown, comments, or extra text.

Schema:
{
"intent": "chat | rag_quran | rag_hadith | rag_all | motivation | web_search | ambiguous",
"confidence": number,
"reason": "string",
"detected_entities": {
    "collection": "string or null",
    "hadith_number": "string or null",
    "narrator": "string or null",
    "chapter": "string or null"
}
}
"""

ALLOWED_INTENTS = {
    "chat",
    "rag_quran",
    "rag_hadith",
    "rag_all",
    "motivation",
    "web_search",
    "ambiguous",
}

# Known hadith collections for local detection
KNOWN_COLLECTIONS = {
    'bukhari': 'Sahih Bukhari',
    'muslim': 'Sahih Muslim',
    'tirmidhi': 'Jami at-Tirmidhi',
    'nawawi': 'Nawawi 40',
    'shamail': 'Shamail Muhammadiyah',
    'abu dawud': 'Sunan Abi Dawud',
    'ibn majah': 'Sunan Ibn Majah',
    'nasai': 'Sunan an-Nasai',
    'riyad': 'Riyad as-Salihin',
    'mishkat': 'Mishkat al-Masabih',
}

def extract_hadith_entities_local(text: str) -> dict:
    """Local extraction of hadith entities without LLM call"""
    text_lower = text.lower()
    entities = {
        "collection": None,
        "hadith_number": None,
        "narrator": None,
        "chapter": None
    }
    
    # Check for collection mentions
    for key, value in KNOWN_COLLECTIONS.items():
        if key in text_lower:
            entities["collection"] = value
            break
    
    # Check for hadith number pattern
    hadith_patterns = [
        r'hadith\s*#?\s*(\d+)',
        r'#(\d+)',
        r'number\s*(\d+)',
        r'(\d+)(?:st|nd|rd|th)?\s+hadith'
    ]
    for pattern in hadith_patterns:
        match = re.search(pattern, text_lower)
        if match:
            entities["hadith_number"] = match.group(1)
            break
    
    # Check for narrator mentions
    narrators = ['abu hurairah', 'ibn umar', 'aisha', 'anas ibn malik', 'umar', 
                 'ibn abbas', 'jabir', 'abu said', 'muadh', 'ibn masud']
    for narrator in narrators:
        if narrator in text_lower:
            entities["narrator"] = narrator.title()
            break
    
    # Check for chapter mentions
    chapter_patterns = [
        r'chapter\s*(\d+)',
        r'book\s*(\d+)',
        r'kitab\s*(\d+)'
    ]
    for pattern in chapter_patterns:
        match = re.search(pattern, text_lower)
        if match:
            entities["chapter"] = match.group(1)
            break
    
    return entities

async def classify_query_llm(text: str, user_memories: list = None) -> dict:
    """
    Classify query intent with LLM and local entity extraction.
    Prioritizes explicit [TAGS] if present in the text.
    """
    text_lower = text.lower()
    
    # ─── Explicit Mode Overrides ──────────────────────────
    if "[fatwa]" in text_lower or "[jur]" in text_lower:
        return {"intent": "web_search", "confidence": 1.0, "reason": "Explicit fatwa mode selected"}
    if "[books]" in text_lower:
        return {"intent": "rag_all", "confidence": 1.0, "reason": "Explicit books mode selected"}
    if "[expert]" in text_lower:
        return {"intent": "rag_all", "confidence": 1.0, "reason": "Explicit expert mode selected"}
    if "[motivate]" in text_lower:
        return {"intent": "motivation", "confidence": 1.0, "reason": "Explicit motivation mode selected"}
    if "[chat]" in text_lower:
        return {"intent": "chat", "confidence": 1.0, "reason": "Explicit chat mode selected"}

    local_entities = extract_hadith_entities_local(text)

    # Build the memory block to inject into the prompt
    if user_memories:
        facts_lines = "\n".join(f"  - {m['fact']}" for m in user_memories)
        memory_block = (
            f"User's stored memory facts (use these to avoid unnecessary web searches):\n"
            f"{facts_lines}"
        )
    else:
        memory_block = "User's stored memory facts: (none)"

    prompt = CLASSIFIER_PROMPT.replace("{memory_block}", memory_block)

    def call_llm():
        return client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
        )

    try:
        response = await run_in_threadpool(call_llm)
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        # Merge local entities with LLM result
        if result.get("detected_entities"):
            if not result["detected_entities"].get("collection") and local_entities["collection"]:
                result["detected_entities"]["collection"] = local_entities["collection"]
            if not result["detected_entities"].get("hadith_number") and local_entities["hadith_number"]:
                result["detected_entities"]["hadith_number"] = local_entities["hadith_number"]
            if not result["detected_entities"].get("narrator") and local_entities["narrator"]:
                result["detected_entities"]["narrator"] = local_entities["narrator"]
        else:
            result["detected_entities"] = local_entities

    except Exception as exc:
        result = {
            "intent": "ambiguous",
            "confidence": 0.0,
            "reason": f"LLM error: {str(exc)}",
            "detected_entities": local_entities,
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