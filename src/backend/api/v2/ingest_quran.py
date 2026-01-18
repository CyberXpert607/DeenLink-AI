import json
import uuid
from pathlib import Path
from itertools import islice

from qdrant_client import QdrantClient
from embeddings import embed_text

QURAN_DIR = Path(__file__).parent.parent / "data" / "quran" # folder with 114 files
COLLECTION_NAME = "islamic_sources"
BATCH_SIZE = 256  # SAFE batch size

client = QdrantClient(
    host="localhost",
    port=6333,
    timeout=60,  # IMPORTANT for large ingests
)


def batched(iterable, size):
    """Yield lists of size `size` from iterable."""
    it = iter(iterable)
    while batch := list(islice(it, size)):
        yield batch


def surah_sort_key(path: Path) -> int:
    """
    Extract numeric surah index from filenames like:
    surah_1.json, surah_114.json
    """
    return int(path.stem.split("_")[1])

def ingest_quran():
    points = []

    surah_files = sorted(
        QURAN_DIR.glob("surah_*.json"),
        key=surah_sort_key
    )

    if not surah_files:
        print("No Quran data found. Check QURAN_DIR path.")
        return

    for surah_file in surah_files:
        with open(surah_file, "r", encoding="utf-8") as f:
            surah_data = json.load(f)

        surah_number = surah_data["surah"]
        surah_name = surah_data["surah_name"]

        for verse in surah_data["verses"]:
            ayah = verse["ayah"]

            text_for_embedding = (
                f"Quran Surah {surah_name}, Ayah {ayah}. "
                f"Arabic: {verse['arabic']} "
                f"English: {verse['english']}"
            )

            vector = embed_text(text_for_embedding)

            payload = {
                "source_type": "quran",
                "collection": "quran",
                "surah": surah_number,
                "surah_name": surah_name,
                "ayah": ayah,
                "arabic": verse["arabic"],
                "english": verse["english"],
            }

            points.append(
                {
                    "id": str(uuid.uuid4()),
                    "vector": vector,
                    "payload": payload,
                }
            )

        print(f"Loaded Surah {surah_number}: {surah_name}")

    print(f"\nTotal Quran ayahs prepared: {len(points)}")
    print("Starting batched upsert...\n")

    total_upserted = 0

    for batch in batched(points, BATCH_SIZE):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch,
            wait=True,
        )
        total_upserted += len(batch)
        print(f"Upserted {total_upserted}/{len(points)} ayahs")

    print("\nQuran ingestion completed successfully.")

if __name__ == "__main__":
    ingest_quran()
