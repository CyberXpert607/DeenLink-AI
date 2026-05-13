import asyncio
import sys
import os
from pathlib import Path

# Fix paths
current_dir = Path(__file__).resolve().parent
backend_api_dir = current_dir.parent / "src" / "backend" / "api"
sys.path.append(str(backend_api_dir))

# Mock or load env
os.environ["GROQ_API_KEY"] = "mock" # Not needed for search if we use local embedding? 
# Wait, embeddings uses OpenAI or something? 
# Let's check embeddings.py

from v2.llm_classify import classify_query_llm
from v2.vectoreStore import search_similar

async def test():
    query = "Tell me the story of Prophet Yusuf"
    print(f"Testing Query: {query}")
    
    try:
        # Test Search first (no LLM needed)
        results = search_similar(query, 5)
        print(f"\nSearch Results (Total: {len(results)}):")
        for i, r in enumerate(results):
            print(f"[{i+1}] Score: {r.score:.4f} | Type: {r.source_type} | Title: {r.payload.get('title')}")
    except Exception as e:
        print(f"Search failed: {e}")

    try:
        # Test classification (requires GROQ)
        classification = await classify_query_llm(query)
        print(f"\nClassification Intent: {classification.get('intent')}")
        print(f"Reason: {classification.get('reason')}")
    except Exception as e:
        print(f"Classification failed (likely no API key): {e}")

if __name__ == "__main__":
    asyncio.run(test())
