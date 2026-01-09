import json
from pathlib import Path

DATA_DIR = Path("data")

def retrieve_evidence(topic: str, question: str):
    file_map = {
        "hadith": "40_hadith_nawawi.json",
        "fiqh": "imam_malik.json",
        #"quran": "quran.json", TO DO: update later!
    }

    file_name = file_map.get(topic)
    if not file_name:
        return []

    path = DATA_DIR / file_name
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    results = []

    for item in raw_items:
        arabic = item.get("arabic")
        english_text = item.get("english", {}).get("text")

        if not arabic or not english_text:
            continue

        results.append({
            "arabic": arabic.strip(),
            "english": english_text.strip(),
            "source": item.get("collection", "unknown"),
        })

    return results[:3]  # hard limit for safety
