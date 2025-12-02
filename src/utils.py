import re


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


def strip_leading_mention(text: str) -> str:
    """
    Remove a leading Slack user mention like '<@U123ABC>' plus any following whitespace.
    This helps us reason about the actual user message length and content.
    """
    return re.sub(r"^<@[^>]+>\s*", "", text or "").strip()
