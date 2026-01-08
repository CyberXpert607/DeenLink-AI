def classify_topic(question: str) -> str:
    q = question.lower()

    if any(w in q for w in ["quran", "ayah", "surah"]):
        return "quran"
    if any(w in q for w in ["hadith", "prophet said", "narrated"]):
        return "hadith"
    if any(w in q for w in ["fiqh", "halal", "haram", "prayer", "salah", "zakat"]):
        return "fiqh"
    if any(w in q for w in ["aqeedah", "belief", "iman", "allah", "tawheed"]):
        return "aqeedah"

    return "unknown"
