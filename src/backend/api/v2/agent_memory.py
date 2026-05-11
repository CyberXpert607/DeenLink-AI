"""
agent_memory.py  —  Memory extraction agent for DeenLink AI.

Analyses a single user message and determines whether a personal fact
should be added, updated, or deleted from the user's persistent memory.
"""
import json
import logging
from groq import Groq
from config import GROQ_API_KEY, MODEL

logger = logging.getLogger(__name__)
client = Groq(max_retries=3)

MEMORY_PROMPT = """
You are the memory manager for DeenLink AI.
Your job is to analyse the user's message and update their personal memories.

══════════════════════════════════════════════════════
CORE GUIDELINES
══════════════════════════════════════════════════════
1. ONLY remember important personal facts:
   - Name (e.g. "My name is Ahmad")
   - Location / city / country (e.g. "I live in Lagos", "I'm from Kano", "I'm based in London")
   - Profession / occupation (e.g. "I work as a nurse", "I am a student")
   - Family status (e.g. "I am married", "I have two kids")
   - Areas of genuine interest or passion (e.g. "I love playing basketball", "I enjoy reading")
   - Challenges or goals (e.g. "I'm trying to memorise the Quran", "I struggle with fajr")
   - Religion / sect / madhab (e.g. "I follow the Maliki madhab")
   - Language preferences (e.g. "I prefer Arabic responses")

2. DO NOT remember:
   - Trivial one-off preferences unless the user explicitly wants them remembered
   - Conversational greetings or polite expressions
   - Questions the user is asking (those are not facts about them)

3. DO NOT guess or infer. If the information is not explicitly stated, return "none".

4. Keep facts concise (one sentence max). Use the Chain of Density approach.

5. UPDATE: if the new message contradicts an existing memory (e.g., moved city),
   identify the existing memory to update.

6. DELETE: if the user explicitly asks to forget something.

══════════════════════════════════════════════════════
TRIGGER PHRASES (examples — not exhaustive)
══════════════════════════════════════════════════════
- "I live in / I'm based in / I'm from / I moved to" → location
- "My name is / People call me / I go by" → name
- "I work as / I am a / My job is / I'm a student" → occupation
- "I love / I enjoy / I'm passionate about / I play" → interest/hobby
- "I am married / I have children / My wife / My husband" → family
- "I follow / I am / My madhab is" → religious identity
- "I want to / I'm trying to / My goal is" → personal goal
- "Forget that / Remove the memory about / Don't remember" → delete

══════════════════════════════════════════════════════
INPUT
══════════════════════════════════════════════════════
- User Message: the text to analyse
- Existing Memories: a JSON list of the user's current memories with their IDs

══════════════════════════════════════════════════════
OUTPUT (valid JSON only)
══════════════════════════════════════════════════════
{
    "action": "add" | "update" | "delete" | "none",
    "fact": "Concise fact to store (if add/update). Empty string if delete or none.",
    "original_memory_id": "ID of memory to update or delete. Null if add or none.",
    "reason": "Brief reason for this action (1 sentence)."
}

If multiple actions could apply, pick the most important one.
If nothing is worth remembering, return action: "none".
"""


async def extract_memory_facts(query: str, existing_memories: list) -> dict:
    """
    existing_memories format: [{"id": "...", "fact": "..."}]
    Returns dict with action, fact, original_memory_id, reason.
    """
    try:
        memories_str = json.dumps(existing_memories, indent=2)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": MEMORY_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Existing Memories:\n{memories_str}\n\n"
                        f"User Message:\n{query}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        result = json.loads(content)
        # Normalise
        if result.get("action") not in ("add", "update", "delete", "none"):
            result["action"] = "none"
        return result
    except Exception as exc:
        logger.error(f"Error in extract_memory_facts: {exc}")
        return {"action": "none"}
