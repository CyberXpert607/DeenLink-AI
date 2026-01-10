import json
from pathlib import Path
from typing import List, Tuple, Dict, Any

DATA_DIR = Path("data")

def retrieve_evidence(topic: str, query: str) -> Tuple[List[Dict[str, Any]], float]:
    results: List[Dict[str, Any]] = []
    score = 0

    query_words = query.lower().split()

    for file in DATA_DIR.glob("*.json"):
        try:
            with open(file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:

            continue

        if not isinstance(data, list):
            continue

        for item in data:
            if not isinstance(item, dict):
                continue

            arabic = item.get("arabic", "")
            english_obj = item.get("english", {})

            if not isinstance(english_obj, dict):
                english_obj = {}

            english_text = english_obj.get("text", "")
            narrator = english_obj.get("narrator")

            text_blob = f"{arabic} {english_text}".lower()

            matches = sum(1 for w in query_words if w in text_blob)

            if matches >= 2:
                score += matches
                results.append({
                    "collection": item.get("collection"),
                    "chapter": item.get("chapter_name", {}).get("english"),
                    "hadith_number": item.get("hadith_number"),
                    "arabic": arabic,
                    "english": english_text,
                    "narrator": narrator,
                    "grade": item.get("grade")
                })

    confidence = min(score / 10, 1.0)
    return results, confidence
