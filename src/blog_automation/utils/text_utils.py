from __future__ import annotations

import re


def slugify(text: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


def extract_section_count(topic: str, default: int = 3) -> int:
    match = re.match(r"^\s*(\d+)\b", topic)
    if not match:
        return default
    return max(1, int(match.group(1)))


def word_count(text: str) -> int:
    return len([word for word in text.split() if word])