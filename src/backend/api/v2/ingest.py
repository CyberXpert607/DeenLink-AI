import json
from pathlib import Path
from .vectoreStore import upsert_documents

DATA_DIR = Path("data")

def load_all_documents():
    docs = []

    for file in DATA_DIR.glob("*.json"):
        with open(file, encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            docs.append({
                "collection": item.get("collection"),
                "arabic": item.get("arabic", ""),
                "english": item.get("english", {}).get("text", ""),
                "narrator": item.get("english", {}).get("narrator"),
                "grade": item.get("grade")
            })

    return docs


if __name__ == "__main__":
    documents = load_all_documents()
    upsert_documents(documents)
    print(f"Ingested {len(documents)} documents into Qdrant.")
