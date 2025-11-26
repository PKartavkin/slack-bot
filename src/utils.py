def contains(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)
