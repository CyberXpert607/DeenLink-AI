import json
from pathlib import Path
from v2.vectoreStore import upsert_documents

BASE_DIR =Path(__file__).resolve().parent
API_DIR =BASE_DIR.parent
DATA_DIR = API_DIR / "data"

print("[INGEST] Scanning:", DATA_DIR)
print("[INGEST] Exists:", DATA_DIR.exists())
print("[INGEST] Files:", list(DATA_DIR.glob("*.json")))

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
    print(f"[INGEST] Loaded {len(documents)} documents")
    upsert_documents(documents)
    print(f"Ingested {len(documents)} documents into Qdrant.")
