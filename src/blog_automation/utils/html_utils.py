from __future__ import annotations


def normalize_paragraph(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("<p>") and cleaned.endswith("</p>"):
        cleaned = cleaned[3:-4].strip()
    return cleaned
