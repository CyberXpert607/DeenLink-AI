import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def load_source(topic: str):
    file = DATA_DIR / f"{topic}.json"
    if not file.exists():
        return []

    with open(file, encoding="utf-8") as f:
        return json.load(f)

def retrieve_evidence(topic: str, query: str):
    data = load_source(topic)

    matches = []
    for item in data:
        if query.lower() in item["text_en"].lower():
            matches.append(item)

    return matches[:3]  # MAX retries
