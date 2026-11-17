import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    text: str
    start: int
    end: int


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> list[Chunk]:
    """Prefer paragraph/sentence boundaries, retain overlap and exact source offsets."""
    if not 0 <= overlap < size or size < 32:
        raise ValueError("Chunk size must exceed overlap and be at least 32 characters.")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start + size // 2 : end]
            boundaries = list(re.finditer(r"\n\n|[.!?]\s|\s", window))
            paragraphs = [match for match in boundaries if match.group() == "\n\n"]
            sentences = [match for match in boundaries if match.group()[0] in ".!?"]
            best = paragraphs or sentences or boundaries
            if best:
                end = start + size // 2 + best[-1].end()
        # Keep offsets in the original text even when trimming surrounding whitespace.
        raw = text[start:end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        if right > left:
            chunks.append(Chunk(raw[left:right], start + left, start + right))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks
