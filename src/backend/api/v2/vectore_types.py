from dataclasses import dataclass

@dataclass
class VectorSearchResult:
    content: str
    score: float
    source_type: str
    payload: dict