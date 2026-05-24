def format_source_display(payload: dict) -> str:
    source_type = payload.get("source_type")
    
    if source_type == "hadith":
        parts = []
        collection = payload.get("collection", "")
        if collection: parts.append(collection)
        hadith_ref = payload.get("hadith_number_display")
        if hadith_ref: parts.append(hadith_ref)
        chapter = payload.get("chapter_name_en") or payload.get("chapter_name_ar")
        if chapter: parts.append(chapter[:40])
        grade = payload.get("grade")
        if grade and grade != "Unknown": parts.append(grade)
        return " · ".join(parts) if parts else "Hadith"
    
    elif source_type == "quran":
        surah = payload.get("surah_name", "")
        ayah = payload.get("ayah", "")
        if surah and ayah: return f"Qur'an {surah}:{ayah}"
        return "Qur'an"
    
    elif source_type == "seerah":
        title = payload.get("title", "")
        hijri = payload.get("hijri_year", "")
        parts = ["Seerah"]
        if title: parts.append(title[:50])
        if hijri: parts.append(hijri)
        return " · ".join(parts)

    elif source_type == "qa":
        question = payload.get("question", "")
        if question: return f"islamqa.info · {question[:50]}"
        return "islamqa.info"
        
    elif source_type == "article":
        title = payload.get("title", "")
        if title: return f"Article · {title[:50]}"
        return "Islamic Article"

    elif source_type == "prophet":
        title = payload.get("title", "")
        if title: return f"Prophet Story · {title}"
        return "Prophet Story"

    elif source_type == "companion":
        title = payload.get("title", "")
        if title: return f"Companion · {title}"
        return "Companion Biography"

    elif source_type == "99_names":
        title = payload.get("title", "")
        if title: return f"99 Names of Allah · {title}"
        return "99 Names of Allah"

    return "Islamic Source"
