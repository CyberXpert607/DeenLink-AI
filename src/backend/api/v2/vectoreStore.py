from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from .embeddings import embed_text

COLLECTION_NAME = "islamic_sources"

client = QdrantClient(
    url="http://localhost:6333"
)

def ensure_collection():
    """
    Create collection if it does not exist.
    """
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
    """
    Insert documents into Qdrant.
    """
    ensure_collection()

    points = []
    for idx, doc in enumerate(docs):
        text_blob = f"{doc['arabic']} {doc['english']}"

        points.append({
            "id": idx,
            "vector": embed_text(text_blob),
            "payload": doc
        })

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )


def search_similar(query: str, limit: int = 5):
    """
    Semantic search in Qdrant.
    """
    vector = embed_text(query)

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        limit=limit,
        with_payload=True
    )

    return [
        {
            **hit.payload,
            "score": hit.score
        }
        for hit in results
    ]
