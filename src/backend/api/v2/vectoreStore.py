from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from v2.embeddings import embed_text
from v2.vectore_types import VectorSearchResult
from typing import List
import uuid

COLLECTION_NAME = "islamic_sources"

client = QdrantClient(
    url="http://localhost:6333"
)

def ensure_collection():
    #create collection if it doesn't exist with the name as the value in COLLECTION_NAME variable on the top!
    collections = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=384,
                distance=Distance.COSINE
            )
        )


def upsert_documents(docs: list[dict]):
    #Insert documents into Qdrant(json docs in /data directory)
    ensure_collection()

    points = []
    for doc in docs:
        text_blob = f"{doc['arabic']} {doc['english']}"

        points.append({
            "id": str(uuid.uuid4()),
            "vector": embed_text(text_blob),
            "payload": doc
        })

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )


def search_similar(query: str, limit: int = 5, min_score: float = 0.35) -> List[VectorSearchResult]:

    vector = embed_text(query)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit,
        with_payload=True
    )

    final_results = []
    for p in results.points:
        score = p.score if p.score else 0
        if score < min_score:
            continue
        payload = p.payload
        if "arabic" in payload and "english" in payload:
            content_text = f"{payload.get('arabic', '')} {payload.get('english', '')}"
        else:
            content_text = str(payload)
        
        final_results.append(VectorSearchResult(
            content=content_text,
            score=float(score),
            source_type = payload.get("source_type", "unknown"),
            payload = payload
        ))
    return final_results