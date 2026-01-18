
def is_religious_promt(text: str) -> bool:
    text = text.lower().strip()

    keywords = [
        "hadith", "figh", "verse", "narrated", "prophet", "Allah", "surah", "fasting", "zakat",
        "charity", "salah", "iman", "ayah", "taqwa", "reported by", "muslim", "ibn majah", "bukhari",
        "abu dawud", "tirmidhi", "islam", "muhammad"
    ]
    
    return any(trigger in text for trigger in keywords)