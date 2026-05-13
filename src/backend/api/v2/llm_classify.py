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
- motivation -> wants encouragement, life advice, patience, hope, reassurance USING Islamic sources
- web_search -> wants latest information, current events, real-time dates, news, or facts that CANNOT be answered from memory or conversation
- ambiguous -> unclear intent, needs clarification

Rules for Hadith Detection:
- User mentions: hadith, sunnah, prophetic tradition, narrated by, collection names (Bukhari, Muslim, Tirmidhi, Nawawi, Shamail, etc.)
- User asks about Prophet Muhammad's sayings, actions, or approvals
- User mentions narrator names (Abu Hurairah, Ibn Umar, Aisha, etc.)
- User asks for specific hadith numbers or chapters

Rules for Quran Detection:
- User mentions: Quran, Qur'an, surah, ayah, verse, recitation
- User asks about specific chapters or verses

Rules for Motivation:
- User asks "What does Islam say about X?" where X is a life situation
- User expresses distress, sadness, anxiety, or seeks hope
- User asks for encouragement, patience (sabr), trust in Allah (tawakkul)
- User expresses struggle with worship, consistency, habits, or religious duties (e.g., "I struggle with Fajr")

Rules for Web Search:
- ONLY use web_search if the answer genuinely requires current/live internet data
- Do NOT use web_search if the answer is already known from the user's memory facts below
- Do NOT use web_search for follow-up questions about previously shared personal info (e.g. "where do I live?" when location is in memory)
- Examples that ARE web_search: "who won the Champions League?", "what is today's date?", "latest news on X"
- Examples that are NOT web_search: "where do I live?" (answer from memory), "what is my name?" (answer from memory)

Rules for Chat:
- General conversation, greetings, personal questions that can be answered from the user's stored memories
- Follow-up questions about things the user has already told the AI

{memory_block}

Respond ONLY in JSON format.
Do not include markdown, comments, or extra text.

Schema:
{
"intent": "chat | rag_quran | rag_hadith | motivation | web_search | ambiguous",
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

    user_memories: list of dicts [{"id": "...", "fact": "..."}] — when provided,
    injected into the classifier prompt so the LLM avoids routing to web_search
    for questions answerable from memory.
    """
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