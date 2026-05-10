from duckduckgo_search import DDGS
from groq import Groq
import logging
import json
from config import MODEL

client = Groq(timeout=120.0)

def perform_web_search(query: str, max_results: int = 3) -> list:
    """Performs a web search using DuckDuckGo."""
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "body": r.get("body", "")
                })
        return results
    except Exception as e:
        logging.error(f"DuckDuckGo search error: {e}")
        return []

def stream_web_search_answer(question: str, context_history: list = None):
    """Streams a response using web search results."""
    # First, perform the search
    search_results = perform_web_search(question)
    
    if not search_results:
        yield json.dumps({"type": "token", "content": "I tried searching the web for this, but I couldn't find any relevant results."}) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"
        return
        
    # Format the sources
    sources_text = "\n\n".join([f"Source {i+1}: {r['title']}\nURL: {r['url']}\nSnippet: {r['body']}" for i, r in enumerate(search_results)])
    
    system_prompt = (
        "You are DeenLink AI, an intelligent assistant. You have just performed a web search to answer the user's question.\n"
        "Use the provided search results to answer the question accurately and concisely.\n"
        "Always cite your sources using inline links [Source Name](URL) at the end of relevant sentences.\n"
        "If the search results do not contain the answer, explicitly state that."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    if context_history:
        messages.extend(context_history)
        
    messages.append({
        "role": "user", 
        "content": f"Question: {question}\n\nSearch Results:\n{sources_text}"
    })
    
    try:
        stream = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            stream=True
        )
        
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield json.dumps({"type": "token", "content": delta}) + "\n\n"
                
        # Send sources as well so UI can display them
        # Convert DDG results to our source format
        sources_data = []
        for r in search_results:
            sources_data.append({
                "source_type": "web",
                "score": 1.0,
                "payload": {
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["body"],
                    "display_reference": r["title"]
                },
                "display_reference": r["title"]
            })
            
        yield json.dumps({"type": "sources", "sources": sources_data}) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"
        
    except Exception as e:
        logging.error(f"Error streaming web search answer: {e}")
        yield json.dumps({"type": "token", "content": "I encountered an error while processing the search results."}) + "\n\n"
        yield json.dumps({"type": "done"}) + "\n\n"
