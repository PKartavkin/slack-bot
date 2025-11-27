def contains(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)

def strip_command(text: str, keywords: list[str]) -> str:
    lowered = text.lower()
    for k in keywords:
        if k in lowered:
            idx = lowered.index(k)
            # remove the command phrase
            cleaned = text[:idx] + text[idx + len(k):]
            return cleaned.strip()
    return text.strip()
