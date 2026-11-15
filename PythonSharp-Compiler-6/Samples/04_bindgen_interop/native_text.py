"""Native Python module providing text processing utilities."""

import re


def slugify(title: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"[-\s]+", "-", cleaned).strip("-")

def count_words(content: str) -> int:
    return len(content.split())
