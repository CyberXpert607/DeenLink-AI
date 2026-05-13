import sys
import json
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from v2.vectoreStore import client, COLLECTION_NAME, ensure_collection
from v2.embeddings import embed_text

FILES_TO_INGEST = [
    API_DIR / "data" / "seera_general_QAs" / "prophets_full.json",
    API_DIR / "data" / "seera_general_QAs" / "rashidun_caliphs.json",
    API_DIR / "data" / "seera_general_QAs" / "names_of_allah.json"
]

BATCH_SIZE = 100

def ingest_file(file_path):
    print(f"Processing {file_path.name}...")
    if not file_path.exists():
        print(f"File {file_path} not found.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    points = []
    total_processed = 0

    for item in items:
        title = item.get("title", "")
        details = item.get("details", "")
        category = item.get("category", "article")
        
        text_for_embedding = f"Category: {category}. Title: {title}. Details: {details}"
        
        payload = {
            "source_type": category,
            "title": title,
            "details": details,
        }
        
        try:
            vector = embed_text(text_for_embedding)
            points.append({
                "id": str(uuid.uuid4()),
                "vector": vector,
                "payload": payload
            })
        except Exception as e:
            print(f"Error embedding {title}: {e}")
            continue
        
        if len(points) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            total_processed += len(points)
            print(f"Upserted {total_processed} items...")
            points = []
            
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        total_processed += len(points)
        
    print(f"Completed {file_path.name}. Total upserted: {total_processed}")

if __name__ == "__main__":
    ensure_collection()
    for file_path in FILES_TO_INGEST:
        ingest_file(file_path)
