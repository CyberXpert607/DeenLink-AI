from sentence_transformers import SentenceTransformer

# Load once, reuse everywhere
_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def embed_text(text: str) -> list[float]:
    """
    Convert text into a vector embedding.
    """
    return _model.encode(text, normalize_embeddings=True).tolist()
