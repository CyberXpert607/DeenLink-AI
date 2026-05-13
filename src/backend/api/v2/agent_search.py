from duckduckgo_search import DDGS
from groq import Groq
import logging
import json
import datetime
from urllib.parse import urlparse
from config import MODEL, GOOGLE_API_KEY, GOOGLE_SEARCH_ENGINE_ID
import requests

logger = logging.getLogger(__name__)
client = Groq(timeout=120.0)

TRUSTED_DOMAINS = {
    "islamqa.info",
    "islamweb.net",
    "seekersguidance.org",
    "quran.com",
    "daruliftaa.com",
    "muftionline.co.za",
    "islamicfinder.org",
    # General fact / news
    "wikipedia.org",
    "timeanddate.com",
    "bbc.com",
    "bbc.co.uk",
    "aljazeera.com",
    "reuters.com",
    "apnews.com",
}


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        # handle subdomains — keep last two parts
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def _is_trusted(url: str) -> bool:
    dom = _domain_of(url)
    return any(dom == td or dom.endswith("." + td) for td in TRUSTED_DOMAINS)

# Query rewriter

def _rewrite_query(user_query: str, context_summary: str = "") -> str:
    """
    Ask the LLM to turn the raw user message into a focused search query.
    Falls back to the original query on any error.
    """
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    context_clause = f"\nConversation context: {context_summary}" if context_summary else ""
    prompt = (
        f"Today is {today}.{context_clause}\n\n"
        "Rewrite the following user message into a concise, effective web-search query "
        "(max 10 words). Output ONLY the search query — no explanation, no quotes.\n\n"
        f"User message: {user_query}"
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=30,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning(f"Query rewrite failed: {exc}")
        return user_query


# Search helper
def perform_web_search(query: str, max_results: int = 8) -> tuple[list, list]:
    """
    Returns (trusted_results, fallback_results).
    trusted_results — from TRUSTED_DOMAINS
    fallback_results — everything else (used only if trusted is thin)
    """
    if GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID:
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_SEARCH_ENGINE_ID,
                "q": query,
                "num": min(max_results, 10),
            }
            resp = requests.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            trusted, others = [], []
            for item in data.get("items", []):
                entry = {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "body": item.get("snippet", ""),
                }
                if _is_trusted(entry["url"]):
                    trusted.append(entry)
                else:
                    others.append(entry)
            return trusted, others
        except Exception as exc:
            logger.error(f"Google Custom Search error: {exc}. Falling back to DuckDuckGo.")

    try:
        trusted, others = [], []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                entry = {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "body": r.get("body", ""),
                }
                if _is_trusted(entry["url"]):
                    trusted.append(entry)
                else:
                    others.append(entry)
        return trusted, others
    except Exception as exc:
        logger.error(f"DuckDuckGo search error: {exc}")
        return [], []


# Context summariser (extract recent user facts from history)
def _context_summary(context_history: list) -> str:
    """Build a short human-readable summary of recent conversation turns."""
    if not context_history:
        return ""
    lines = []
    for m in context_history[-6:]:  # last 3 pairs
        role = "User" if m.get("role") == "user" else "AI"
        lines.append(f"{role}: {str(m.get('content', ''))[:120]}")
    return "\n".join(lines)



# Main streaming function

def stream_web_search_answer(
    question: str,
    context_history: list = None,
    user_memories: list = None,
):
    """
    Generator that yields JSON-encoded SSE data strings.
    """
    context_history = context_history or []
    user_memories = user_memories or []

    today = datetime.datetime.now().strftime("%A, %d %B %Y")

    # Build a context summary for query rewriting
    ctx_summary = _context_summary(context_history)

    # Rewrite the user's query for better search results
    search_query = _rewrite_query(question, ctx_summary)
    logger.info(f"Web search | original='{question}' | rewritten='{search_query}'")

    # Perform search
    trusted, fallback = perform_web_search(search_query)

    # Prefer trusted; pad with fallback only if we have fewer than 2 trusted hits
    results = trusted[:3]
    if len(results) < 2:
        results += fallback[: (2 - len(results))]

    if not results:
        yield json.dumps({
            "type": "token",
            "content": "I searched the web but couldn't find any relevant results for your question."
        }) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"
        return

    # Format sources context for the LLM
    sources_text = "\n\n".join(
        f"[Source {i+1}] {r['title']}\nURL: {r['url']}\nSnippet: {r['body']}"
        for i, r in enumerate(results)
    )

    # Build memory block
    memory_block = ""
    if user_memories:
        facts = "\n".join(f"- {m}" for m in user_memories)
        memory_block = f"\nKnown facts about the user (use when relevant):\n{facts}\n"

    system_prompt = (
        f"You are DeenLink AI, a helpful and knowledgeable Islamic assistant.\n"
        f"Today's date is {today}.\n"
        f"{memory_block}\n"
        "You have performed a web search. Use the search results below to answer "
        "the user's question accurately and concisely.\n"
        "Rules:\n"
        "- Answer directly; no filler phrases.\n"
        "- Cite sources inline using [Source N] notation.\n"
        "- If search results don't answer the question, say so clearly.\n"
        "- For Islamic questions, always end with 'Wallahu A'lam'.\n"
        "- Do NOT make up information not present in the sources.\n\n"
        f"Search results:\n{sources_text}"
    )

    messages = [{"role": "system", "content": system_prompt}]

    # Include recent conversation history for context
    if context_history:
        for m in context_history[-6:]:
            if m.get("role") in ("user", "assistant"):
                messages.append({"role": m["role"], "content": str(m.get("content", ""))})

    messages.append({"role": "user", "content": question})

    try:
        stream = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield json.dumps({"type": "token", "content": delta}) + "\n\n"

        # Yield sources for UI rendering
        sources_data = []
        for r in results:
            hostname = _domain_of(r["url"])
            sources_data.append({
                "source_type": "web",
                "score": 1.0,
                "payload": {
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["body"][:300],
                    "hostname": hostname,
                    "is_trusted": _is_trusted(r["url"]),
                    "favicon_url": f"https://www.google.com/s2/favicons?domain={hostname}&sz=32",
                    "display_reference": r["title"],
                },
                "display_reference": r["title"],
            })

        yield json.dumps({"type": "sources", "sources": sources_data}) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"

    except Exception as exc:
        logger.error(f"Error streaming web search answer: {exc}")
        yield json.dumps({
            "type": "token",
            "content": "I encountered an error while processing the search results. Please try again."
        }) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"
