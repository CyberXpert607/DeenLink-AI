import json
import logging
from groq import Groq
from config import GROQ_API_KEY, MODEL

client = Groq(max_retries=3)

MEMORY_PROMPT = """
You are the memory manager for DeenLink AI.
Your job is to analyze the user's message and update their personal memories.

CORE GUIDELINES:
1. ONLY remember important facts: 
   - Current projects and priorities
   - Areas of interest, passions, or expertise
   - Challenges or obstacles they are facing
   - Bio/General information (name, location, family, profession)
2. DO NOT remember trivial preferences (e.g., "likes red bell peppers") unless explicitly instructed by the user.
3. DO NOT guess or infer information. If it's not explicitly stated, ignore it.
4. Keep memories highly concise. Use the Chain of Density approach to rewrite lengthy details into short, dense summaries.
5. If the user asks you to forget or delete a memory, identify which existing memory to delete.
6. If the user updates an existing fact (e.g., "I actually live in London now" instead of NY), identify the existing memory to update.

INPUT:
- User Message: The text to analyze.
- Existing Memories: A JSON list of the user's current memories with their IDs.

OUTPUT:
You must return a valid JSON object matching this schema:
{
    "action": "add" | "update" | "delete" | "none",
    "fact": "The concise fact to store (if add or update). Empty if delete or none.",
    "original_memory_id": "The ID of the existing memory to update or delete. Null if add or none.",
    "reason": "Brief reason for this action"
}

If multiple actions could apply, pick the most important one. If nothing is worth remembering, return "none".
"""

async def extract_memory_facts(query: str, existing_memories: list) -> dict:
    """
    existing_memories format: [{"id": "...", "fact": "..."}]
    Returns dict with action, fact, original_memory_id
    """
    try:
        memories_str = json.dumps(existing_memories, indent=2)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": MEMORY_PROMPT},
                {"role": "user", "content": f"Existing Memories:\n{memories_str}\n\nUser Message:\n{query}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        logging.error(f"Error in extract_memory_facts: {e}")
        return {"action": "none"}
