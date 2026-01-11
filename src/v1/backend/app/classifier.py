def classify_topic(question: str) -> str:
    q = question.lower()

    if any(w in q for w in ["quran", "ayah", "surah", "verse"]):
        return "quran"
    if any(w in q for w in ["hadith", "prophet said", "narrated", "prophet ﷺ", "bukhari",]):
        return "hadith"
    if any(w in q for w in ["fiqh", "halal", "haram", "prayer", "salah", "purification", "ruling"]):
        return "fiqh"

    return "chat"