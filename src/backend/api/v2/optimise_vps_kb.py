import json
import uuid
import gc
import time
import collections
from pathlib import Path
from itertools import islice

from vectoreStore import client, COLLECTION_NAME
from embeddings import embed_text

BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR.parent
DATA_DIR = API_DIR / "data" / "hadith"

BATCH_SIZE = 64          
EMBED_CHUNK_SIZE = 16    
CHECKPOINT_FILE = Path("checkpoint_vps.json")
FAILED_EMBEDS_LOG = Path("failed_embeds_vps.log")
FAILED_UPSERTS_LOG = Path("failed_upserts_vps.log")

def batched(iterable, size):
    it = iter(iterable)
    while batch := list(islice(it, size)):
        yield batch

def generate_hadith_reference(item: dict, chapter_counter: dict, collection_name: str, idx: int) -> dict:
    chapter_num = item.get("chapter_number")
    chapter_name_obj = item.get("chapter_name", {})
    
    if isinstance(chapter_name_obj, dict):
        chapter_en = chapter_name_obj.get("english", "")
        chapter_ar = chapter_name_obj.get("arabic", "")
    else:
        chapter_en = str(chapter_name_obj) if chapter_name_obj else ""
        chapter_ar = ""
    
    if chapter_num:
        chapter_key = f"{collection_name}_{chapter_num}"
        chapter_counter[chapter_key] = chapter_counter.get(chapter_key, 0) + 1
        position = chapter_counter[chapter_key]
        return {
            "reference_string": f"{chapter_num}.{position}",
            "hadith_number_display": f"Ch.{chapter_num}·#{position}",
            "sort_order": chapter_num * 1000 + position,
        }
    elif chapter_en or chapter_ar:
        chapter_name_short = (chapter_en or chapter_ar)[:30]
        chapter_key = f"{collection_name}_{chapter_name_short}"
        chapter_counter[chapter_key] = chapter_counter.get(chapter_key, 0) + 1
        position = chapter_counter[chapter_key]
        return {
            "reference_string": f"{collection_name}_{position}",
            "hadith_number_display": f"#{position}",
            "sort_order": position,
        }
    else:
        global_pos = idx + 1
        return {
            "reference_string": f"{collection_name}_{global_pos}",
            "hadith_number_display": f"#{global_pos}",
            "sort_order": global_pos,
        }

def extract_chapter_info(item: dict) -> dict:
    chapter_name_obj = item.get("chapter_name", {})
    if isinstance(chapter_name_obj, dict):
        return {
            "chapter_number": item.get("chapter_number") or chapter_name_obj.get("id"),
            "chapter_name_en": chapter_name_obj.get("english", ""),
            "chapter_name_ar": chapter_name_obj.get("arabic", ""),
            "book_id": chapter_name_obj.get("bookId"),
        }
    return {
        "chapter_number": item.get("chapter_number"),
        "chapter_name_en": str(chapter_name_obj) if chapter_name_obj else "",
        "chapter_name_ar": "",
        "book_id": None,
    }

def extract_english_data(item: dict) -> tuple:
    english_data = item.get("english", {})
    if isinstance(english_data, dict):
        return english_data.get("text", ""), english_data.get("narrator", "")
    return str(english_data) if english_data else "", item.get("narrator", "")

def extract_collection_name(item: dict, filename: str) -> str:
    collection = item.get("collection")
    return collection.title() if collection else Path(filename).stem.replace("_", " ").replace("-", " ").title()

def get_total_documents() -> int:
    total = 0
    for file in DATA_DIR.glob("*.json"):
        try:
            with open(file, encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = [data]
                for item in data:
                    arabic_text = item.get("arabic", "")
                    english_text, _ = extract_english_data(item)
                    if arabic_text or english_text:
                        total += 1
        except Exception:
            pass
    return total

def load_and_prepare_documents():
    chapter_counter = {}
    json_files = list(DATA_DIR.glob("*.json"))
    
    global_doc_idx = 0
    
    for file in json_files:
        with open(file, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[SKIP] Failed to parse {file.name}: {e}")
                continue
        
        if not isinstance(data, list):
            data = [data]
        
        collection_name = extract_collection_name(data[0] if data else {}, file.name)
        
        for idx, item in enumerate(data):
            arabic_text = item.get("arabic", "")
            english_text, narrator = extract_english_data(item)
            
            if not arabic_text and not english_text:
                continue
            
            chapter_info = extract_chapter_info(item)
            ref_data = generate_hadith_reference(item, chapter_counter, collection_name, idx)
            
            grade = item.get("grade", "Unknown")
            if grade == "Unknown" and "sahih" in str(english_text).lower():
                grade = "Sahih"
            
            # Use a truncated text length to save CPU and RAM for embedding
            text_for_embedding = (
                f"Hadith from {collection_name}. {ref_data['hadith_number_display']}. "
                f"Chapter: {chapter_info['chapter_name_en'] or chapter_info['chapter_name_ar'] or 'General'}. "
                f"Narrated by: {narrator}. "
                f"Arabic: {arabic_text[:300]} English: {english_text[:300]}"
            )
            
            doc = {
                "text_for_embedding": text_for_embedding,
                "payload": {
                    "collection": collection_name,
                    "arabic": arabic_text,
                    "english": english_text,
                    "narrator": narrator,
                    "grade": grade,
                    "source_type": "hadith",
                    "hadith_number": ref_data["reference_string"],
                    "hadith_number_display": ref_data["hadith_number_display"],
                    "hadith_sort_order": ref_data["sort_order"],
                    "chapter_number": chapter_info["chapter_number"],
                    "chapter_name_en": chapter_info["chapter_name_en"],
                    "chapter_name_ar": chapter_info["chapter_name_ar"],
                    "book_id": chapter_info["book_id"],
                    "collection_source": file.stem,
                }
            }
            yield global_doc_idx, doc
            global_doc_idx += 1

        # Memory cleanup after processing an entire file's JSON list
        del data
        gc.collect()

def format_eta(seconds: float) -> str:
    if seconds < 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def process_embed_chunk(docs_batch):
    texts = [d[1]["text_for_embedding"] for d in docs_batch]
    vectors = None
    
    for attempt, delay in enumerate([2, 5, 10]):  # Longer delays for VPS
        try:
            vectors = embed_text(texts)
            break
        except Exception as e:
            print(f"    [!] Embedding failed (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(delay)
    
    points = []
    if vectors:
        for (doc_idx, doc), vector in zip(docs_batch, vectors):
            points.append({
                "id": str(uuid.uuid4()),
                "vector": vector,
                "payload": doc["payload"],
                "_doc_idx": doc_idx
            })
    else:
        with open(FAILED_EMBEDS_LOG, "a") as f:
            for doc_idx, _ in docs_batch:
                f.write(f"{doc_idx}\n")
    return points

def upsert_batch(batch, total_upserted, total_docs, speed_history, start_total):
    t0_upsert = time.time()
    upsert_success = False
    
    qdrant_points = [
        {"id": p["id"], "vector": p["vector"], "payload": p["payload"]}
        for p in batch
    ]
    
    for attempt, delay in enumerate([2, 5, 10]):
        try:
            # Force wait=True on VPS to prevent queue overflow
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=qdrant_points,
                wait=True
            )
            upsert_success = True
            break
        except Exception as e:
            print(f"    [!] Upsert failed (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(delay)
                
    if upsert_success:
        num_upserted = len(batch)
        total_upserted += num_upserted
        
        max_idx_in_batch = max(p["_doc_idx"] for p in batch)
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump({"last_processed_idx": max_idx_in_batch + 1}, f)
        
        # Clear out payload memory explicitly
        del qdrant_points
        gc.collect()

        # Update speed history
        elapsed = time.time() - t0_upsert
        # Calculate speed for printing
        avg_speed = sum(speed_history) / len(speed_history) if speed_history else 0
        remaining_docs = total_docs - total_upserted
        eta_seconds = remaining_docs / avg_speed if avg_speed > 0 else 0
        pct = (total_upserted / total_docs * 100) if total_docs > 0 else 0
        
        print(f"    [VPS] Ingested | {total_upserted:,} / {total_docs:,} | {pct:.1f}% | ETA: {format_eta(eta_seconds)}")
    else:
        with open(FAILED_UPSERTS_LOG, "a") as f:
            for p in batch:
                f.write(f"{p['id']}\n")
                
    return total_upserted

def ingest_vps():
    start_total = time.time()
    
    print("=" * 60)
    print("HADITH INGESTION (VPS OPTIMIZED: 2GB RAM / 1 vCPU)")
    print("=" * 60)
    
    skip_count = 0
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                checkpoint_data = json.load(f)
                skip_count = checkpoint_data.get("last_processed_idx", 0)
                if skip_count > 0:
                    print(f"[RESUME] Skipping first {skip_count} documents")
        except Exception as e:
            print(f"[WARNING] Failed to read checkpoint: {e}")

    print("\n[1/3] Calculating total documents for ETA...")
    t0 = time.time()
    total_docs = get_total_documents()
    print(f"    Total documents: {total_docs} (Counted in {time.time()-t0:.1f}s)")

    if total_docs == 0:
        print("[ERROR] No documents to ingest")
        return

    speed_history = collections.deque(maxlen=500)
    
    print(f"\n[2/3] Embedding & Upserting (chunk={EMBED_CHUNK_SIZE}, batch={BATCH_SIZE})...")
    
    doc_generator = load_and_prepare_documents()
    
    if skip_count > 0:
        for _ in range(skip_count):
            try:
                next(doc_generator)
            except StopIteration:
                break
                
    docs_batch = []
    points_to_upsert = []
    total_upserted = skip_count
    
    try:
        batch_start_time = time.time()
        for doc_idx, doc in doc_generator:
            docs_batch.append((doc_idx, doc))
            
            if len(docs_batch) >= EMBED_CHUNK_SIZE:
                points = process_embed_chunk(docs_batch)
                points_to_upsert.extend(points)
                docs_batch = []
                # Force GC after embedding
                gc.collect()
                
                while len(points_to_upsert) >= BATCH_SIZE:
                    batch_to_upsert = points_to_upsert[:BATCH_SIZE]
                    points_to_upsert = points_to_upsert[BATCH_SIZE:]
                    
                    elapsed_batch = time.time() - batch_start_time
                    speed = BATCH_SIZE / elapsed_batch if elapsed_batch > 0 else 0
                    for _ in range(BATCH_SIZE):
                        speed_history.append(speed)

                    total_upserted = upsert_batch(
                        batch_to_upsert, 
                        total_upserted,
                        total_docs,
                        speed_history,
                        start_total
                    )
                    batch_start_time = time.time()
        
        if docs_batch:
            points = process_embed_chunk(docs_batch)
            points_to_upsert.extend(points)
            
        if points_to_upsert:
            elapsed_batch = time.time() - batch_start_time
            speed = len(points_to_upsert) / elapsed_batch if elapsed_batch > 0 else 0
            for _ in range(len(points_to_upsert)):
                speed_history.append(speed)

            total_upserted = upsert_batch(
                points_to_upsert, 
                total_upserted,
                total_docs,
                speed_history,
                start_total
            )

        print("\n" + "=" * 60)
        print("✅ INGESTION COMPLETE")
        print(f"   Total hadith processed: {total_upserted}")
        print(f"   Total time: {time.time() - start_total:.1f}s")
        print("=" * 60)
        
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
            
    except KeyboardInterrupt:
        print("\n[!] Ingestion interrupted by user.")
    except Exception as e:
        print(f"\n[!] Fatal error during ingestion: {e}")

if __name__ == "__main__":
    ingest_vps()