from groq import Groq
import logging
import json
import datetime
from urllib.parse import parse_qs, unquote, urlparse
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
    "wikipedia.org",
    "timeanddate.com",
    "bbc.com",
    "bbc.co.uk",
    "aljazeera.com",
    "reuters.com",
    "apnews.com",
    "arabnews.com",
    "spa.gov.sa",
    "saudigazette.com.sa",
    "aboutislam.net",
    "muslimnews.co.uk",
    "islamic-relief.org",
    "muslimmatters.org",
    "hajj.nusuk.sa",
}

FATWA_DOMAIN = "islamqa.info"
HTTP_HEADERS = {
    "User-Agent": "DeenLinkAI/1.0 (+https://deenlink.org; Islamic knowledge assistant)"
}


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _matches_domain(url: str, domain: str) -> bool:
    host = _domain_of(url)
    return host == domain or host.endswith("." + domain)


def _is_trusted(url: str, query: str = "") -> bool:
    if _matches_domain(url, "myislam.org"):
        keywords = ["allah", "prophet", "companion", "sahaba", "history", "seerah", "names of", "story of"]
        return bool(query and any(kw in query.lower() for kw in keywords))

    if _matches_domain(url, FATWA_DOMAIN):
        if "site:islamqa.info" in query.lower():
            return True
        keywords = ["fatwa", "ruling", "permissible", "halal", "haram", "can i", "is it", "ruling on"]
        return bool(query and any(kw in query.lower() for kw in keywords))

    return any(_matches_domain(url, td) for td in TRUSTED_DOMAINS)


def _fetch_page_text(url: str, max_chars: int = 3500) -> str:
    """Fetch a short readable extract so answers are not based only on snippets."""
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=12)
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return " ".join(soup.get_text(" ").split())[:max_chars]
    except Exception as exc:
        logger.warning(f"Could not fetch page text for {url}: {exc}")
        return ""


def _rewrite_query(user_query: str, context_summary: str = "") -> str:
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    context_clause = f"\nConversation context: {context_summary}" if context_summary else ""
    prompt = (
        f"Today is {today}.{context_clause}\n\n"
        "Rewrite the following user message into a concise, effective Islamic web-search query "
        "(max 10 words). Output ONLY the search query - no explanation, no quotes.\n\n"
        f"User message: {user_query}"
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=30,
        )
        rewritten = resp.choices[0].message.content.strip()
        return rewritten or user_query
    except Exception as exc:
        logger.warning(f"Query rewrite failed: {exc}")
        return user_query


def _search_duckduckgo(query: str, max_results: int, is_fatwa: bool) -> tuple[list, list]:
    trusted, others = [], []
    rows = _search_duckduckgo_html(query, max_results)

    for r in rows:
        entry = {
            "title": r.get("title", ""),
            "url": r.get("href", "") or r.get("url", ""),
            "body": r.get("body", ""),
        }
        if is_fatwa and not _matches_domain(entry["url"], FATWA_DOMAIN):
            continue
        if _is_trusted(entry["url"], query):
            trusted.append(entry)
        elif not is_fatwa:
            others.append(entry)
    return trusted, others


def _search_duckduckgo_html(query: str, max_results: int) -> list[dict]:
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HTTP_HEADERS,
            timeout=12,
            verify=False,
        )
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = []
        for result in soup.select(".result")[:max_results]:
            link = result.select_one(".result__a")
            snippet = result.select_one(".result__snippet")
            if not link:
                continue
            href = link.get("href", "")
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            final_url = unquote(qs.get("uddg", [href])[0])
            rows.append({
                "title": link.get_text(" ", strip=True),
                "href": final_url,
                "body": snippet.get_text(" ", strip=True) if snippet else "",
            })
        return rows
    except Exception as exc:
        logger.warning(f"DuckDuckGo HTML search failed: {type(exc).__name__}")
        return []


def _enrich_results(results: list) -> None:
    for entry in results[:3]:
        fetched_text = _fetch_page_text(entry["url"])
        if fetched_text:
            entry["body"] = f"{entry['body']}\n\nPage extract: {fetched_text}"


def perform_web_search(query: str, max_results: int = 8, is_fatwa: bool = False) -> tuple[list, list]:
    """
    Returns (trusted_results, fallback_results).
    Fatwa mode is intentionally restricted to islamqa.info only.
    """
    if is_fatwa and "site:islamqa.info" not in query.lower():
        query = f"site:islamqa.info {query}"

    try:
        if GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_SEARCH_ENGINE_ID,
                "q": query,
                "num": min(max_results, 10),
            }
            resp = requests.get(url, params=params, headers=HTTP_HEADERS, timeout=12)
            resp.raise_for_status()
            data = resp.json()

            trusted, others = [], []
            for item in data.get("items", []):
                entry = {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "body": item.get("snippet", ""),
                }
                if is_fatwa and not _matches_domain(entry["url"], FATWA_DOMAIN):
                    continue
                if _is_trusted(entry["url"], query):
                    trusted.append(entry)
                elif not is_fatwa:
                    others.append(entry)
        else:
            logger.warning("Google Custom Search is not configured; using DuckDuckGo fallback.")
            trusted, others = _search_duckduckgo(query, max_results, is_fatwa)

        if not is_fatwa and not trusted:
            targeted_query = f"{query} site:arabnews.com OR site:spa.gov.sa OR site:hajj.nusuk.sa"
            targeted_trusted, _ = _search_duckduckgo(targeted_query, max_results, False)
            if targeted_trusted:
                trusted = targeted_trusted

        _enrich_results(trusted)
        return (trusted, []) if is_fatwa else (trusted, others)
    except Exception as exc:
        logger.error(f"Search error via Google Custom Search: {type(exc).__name__}. Falling back to DuckDuckGo search.")
        try:
            trusted, others = _search_duckduckgo(query, max_results, is_fatwa)
            if not is_fatwa and not trusted:
                targeted_query = f"{query} site:arabnews.com OR site:spa.gov.sa OR site:hajj.nusuk.sa"
                targeted_trusted, _ = _search_duckduckgo(targeted_query, max_results, False)
                if targeted_trusted:
                    trusted = targeted_trusted
            _enrich_results(trusted)
            return (trusted, []) if is_fatwa else (trusted, others)
        except Exception as ddg_exc:
            logger.error(f"DuckDuckGo fallback search error: {ddg_exc}")
            return [], []


def _context_summary(context_history: list) -> str:
    if not context_history:
        return ""
    lines = []
    for m in context_history[-6:]:
        role = "User" if m.get("role") == "user" else "AI"
        lines.append(f"{role}: {str(m.get('content', ''))[:120]}")
    return "\n".join(lines)


def stream_web_search_answer(
    question: str,
    context_history: list = None,
    user_memories: list = None,
    is_fatwa: bool = False,
):
    context_history = context_history or []
    user_memories = user_memories or []

    today = datetime.datetime.now().strftime("%A, %d %B %Y")
    ctx_summary = _context_summary(context_history)
    search_query = _rewrite_query(question, ctx_summary)
    logger.info(f"Web search | original='{question}' | rewritten='{search_query}' | fatwa={is_fatwa}")

    trusted, fallback = perform_web_search(search_query, is_fatwa=is_fatwa)
    results = trusted[:3]
    if not is_fatwa and len(results) < 2:
        results += fallback[: (2 - len(results))]

    if not results:
        message = (
            "I could not find a relevant islamqa.info result for that fatwa question. "
            "Please rephrase it with the specific ruling you need."
            if is_fatwa
            else "I searched the web but could not find reliable Islamic/current sources for that question."
        )
        yield json.dumps({"type": "token", "content": message}) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"
        return

    sources_text = "\n\n".join(
        f"[Source {i+1}] {r['title']}\nURL: {r['url']}\nContent: {str(r['body'])[:4000]}"
        for i, r in enumerate(results)
    )

    memory_block = ""
    if user_memories:
        facts = "\n".join(f"- {m}" for m in user_memories)
        memory_block = f"\nKnown facts about the user (use only when relevant):\n{facts}\n"

    fatwa_rule = (
        "- This is a fatwa/ruling answer. Use ONLY islamqa.info sources in the search results.\n"
        if is_fatwa else
        "- This is a current-information answer. Keep it within Islamic topics and cite the provided sources.\n"
    )
    system_prompt = (
        f"You are DeenLink AI, a careful Islamic assistant.\n"
        f"Today's date is {today}.\n"
        f"{memory_block}\n"
        "Use the search results below to answer accurately and concisely.\n"
        "Rules:\n"
        "- Answer directly; no filler phrases.\n"
        "- Cite sources inline using [Source N] notation.\n"
        "- If the sources do not answer the question, say so clearly.\n"
        "- Do NOT make up information not present in the sources.\n"
        f"{fatwa_rule}"
        "- For Islamic questions, end with 'Wallahu A'lam'.\n\n"
        f"Search results:\n{sources_text}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for m in context_history[-6:]:
        if m.get("role") in ("user", "assistant"):
            messages.append({"role": m["role"], "content": str(m.get("content", ""))})
    messages.append({"role": "user", "content": question})

    try:
        stream = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield json.dumps({"type": "token", "content": delta}) + "\n\n"

        sources_data = []
        for r in results:
            hostname = _domain_of(r["url"])
            sources_data.append({
                "source_type": "web",
                "score": 1.0,
                "payload": {
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": str(r["body"])[:300],
                    "hostname": hostname,
                    "is_trusted": _is_trusted(r["url"], search_query),
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
            "content": "I found sources, but could not generate the answer right now. Please try again."
        }) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"
