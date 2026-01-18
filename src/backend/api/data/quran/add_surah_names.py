import json
from pathlib import Path

# ---------------------------------------------
# Paths
# ---------------------------------------------
BASE_DIR = Path(__file__).parent  # folder where this script is
NAMES_FILE = BASE_DIR / "names.txt"  # the file containing surah names
SURAH_FILES_DIR = BASE_DIR  # your surah JSON files are in the same folder

# ---------------------------------------------
# Load surah names from the text file
# ---------------------------------------------
def load_surah_names():
    if not NAMES_FILE.exists():
        raise FileNotFoundError(f"Cannot find names file: {NAMES_FILE}")
    with open(NAMES_FILE, "r", encoding="utf-8") as f:
        # strip lines and remove empty lines
        names = [line.strip() for line in f.readlines() if line.strip()]
    return names

# ---------------------------------------------
# Process each surah JSON file
# ---------------------------------------------
def process_surah_files():
    surah_names = load_surah_names()
    # Iterate over all surah JSON files
    for file_path in sorted(SURAH_FILES_DIR.glob("surah_*.json"), key=lambda p: int(p.stem.split("_")[1])):
        surah_number = int(file_path.stem.split("_")[1])
        if surah_number > len(surah_names):
            print(f"[WARNING] No name for surah number {surah_number}, skipping")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Add the surah_name field
        data["surah_name"] = surah_names[surah_number - 1]

        # Write back
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[UPDATED] {file_path.name} -> surah_name: {data['surah_name']}")

# ---------------------------------------------
# Main
# ---------------------------------------------
if __name__ == "__main__":
    process_surah_files()
    print("[DONE] All surah files updated with surah_name")
