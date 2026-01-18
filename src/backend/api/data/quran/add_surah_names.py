import json
from pathlib import Path

QURAN_DIR = Path("quran")
NAMES_FILE = QURAN_DIR / "names.txt"

def load_surah_names():
    with open(NAMES_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if len(lines) != 114:
        raise ValueError(f"Expected 114 surah names, got {len(lines)}")

    #index 0 = surah 1
    return {i + 1: name for i, name in enumerate(lines)}

def process_surah_files():
    surah_names = load_surah_names()

    for json_file in QURAN_DIR.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        surah_number = data.get("surah")

        if not isinstance(surah_number, int):
            print(f"Skipping {json_file.name}: invalid surah number")
            continue

        if surah_number not in surah_names:
            print(f"Skipping {json_file.name}: no name found")
            continue

        data["surah_name"] = surah_names[surah_number]

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Updated Surah {surah_number}: {data['surah_name']}")

if __name__ == "__main__":
    process_surah_files()
