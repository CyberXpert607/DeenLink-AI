from dataclasses import dataclass

@dataclass
class VectorSearchResult:
    content: str
    score: float
    source_type: str
    metadata: dict | None = None