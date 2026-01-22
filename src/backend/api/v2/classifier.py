
def classify_query(text: str) -> bool:
    text = text.lower().strip()

    hadith_triggers = [
        "hadith", "narrated",
        "charity", "taqwa", "reported by", "muslim", "ibn majah", "bukhari",
        "abu dawud", "tirmidhi"
    ]
    quran_triggers = ["quran", "verse", "ayah", "surah", "where in the quran", "which ayah", "which surah"]

    general_islmaic_knowledge= ["prophet", "muhammad", "islam", "iman", "zakat", "salah"]

    if any(t in text for t in quran_triggers):
        return "quran"
    if any(t in text for t in hadith_triggers):
        return "hadith"
    if any(t in text for t in general_islmaic_knowledge):
        return "general_chat"
    return "chat"