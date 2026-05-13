import sys
import json
import uuid
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from v2.vectoreStore import client, COLLECTION_NAME, ensure_collection
from v2.embeddings import embed_text

SEERA_FILE = API_DIR / "data" / "seera_general_QAs" / "seera_events_en.json"
QA_FILE = API_DIR / "data" / "seera_general_QAs" / "islamqa_multilingual_en.json"

BATCH_SIZE = 100

def process_seerah():
    print(f"Processing Seerah events from {SEERA_FILE}")
    if not SEERA_FILE.exists():
        print("Seerah file not found.")
        return

    with open(SEERA_FILE, "r", encoding="utf-8") as f:
        events = json.load(f)

    points = []
    total_processed = 0

    for event in events:
        title = event.get("title", "")
        details = event.get("details", "")
        hijri_year = event.get("hijri_year", "")
        url = event.get("source_url", "")
        
        text_for_embedding = f"Seerah Event: {title}. Year: {hijri_year}. Details: {details}"
        
        payload = {
            "source_type": "seerah",
            "title": title,
            "details": details,
            "hijri_year": hijri_year,
            "url": url
        }
        
        vector = embed_text(text_for_embedding)
        
        points.append({
            "id": str(uuid.uuid4()),
            "vector": vector,
            "payload": payload
        })
        
        if len(points) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            total_processed += len(points)
            print(f"Upserted {total_processed} Seerah events...")
            points = []
            
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        total_processed += len(points)
        
    print(f"Completed Seerah. Total upserted: {total_processed}")

def process_qa():
    print(f"Processing QA from {QA_FILE}")
    if not QA_FILE.exists():
        print("QA file not found.")
        return

    with open(QA_FILE, "r", encoding="utf-8") as f:
        qas = json.load(f)

    points = []
    total_processed = 0

    for qa in qas:
        conversations = qa.get("conversations", [])
        lang = qa.get("lang", "en")
        url = qa.get("url", "")
        
        question = ""
        answer = ""
        
        for msg in conversations:
            if msg.get("from") == "human":
                question = msg.get("value", "")
            elif msg.get("from") == "gpt":
                answer = msg.get("value", "")
                
        if not question or not answer:
            continue
            
        text_for_embedding = f"Question: {question}\n\nAnswer: {answer}"
        
        payload = {
            "source_type": "qa",
            "question": question[:200] + "..." if len(question) > 200 else question,
            "answer": answer,
            "url": url,
            "lang": lang
        }
        
        vector = embed_text(text_for_embedding)
        
        points.append({
            "id": str(uuid.uuid4()),
            "vector": vector,
            "payload": payload
        })
        
        if len(points) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            total_processed += len(points)
            print(f"Upserted {total_processed} QAs...")
            points = []
            time.sleep(1) # small delay to avoid rate limits on embedding API if applicable
            
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        total_processed += len(points)
        
    print(f"Completed QA. Total upserted: {total_processed}")

if __name__ == "__main__":
    ensure_collection()
    process_seerah()
    process_qa()
