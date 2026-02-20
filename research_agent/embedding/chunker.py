"""Recursive text chunker for large documents."""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken


@dataclass
class Chunk:
    text: str
    index: int
    parent_id: str


SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _count_tokens(text: str, encoding: tiktoken.Encoding) -> int:
    return len(encoding.encode(text))


def _recursive_split(
    text: str,
    max_tokens: int,
    encoding: tiktoken.Encoding,
    separators: list[str] | None = None,
) -> list[str]:
    if separators is None:
        separators = list(SEPARATORS)

    if _count_tokens(text, encoding) <= max_tokens:
        return [text]

    sep = separators[0] if separators else ""
    remaining_seps = separators[1:] if len(separators) > 1 else [""]

    if not sep:
        tokens = encoding.encode(text)
        return [encoding.decode(tokens[i : i + max_tokens]) for i in range(0, len(tokens), max_tokens)]

    parts = text.split(sep)
    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = f"{current}{sep}{part}" if current else part
        if _count_tokens(candidate, encoding) <= max_tokens:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if _count_tokens(part, encoding) > max_tokens:
                chunks.extend(_recursive_split(part, max_tokens, encoding, remaining_seps))
                current = ""
            else:
                current = part

    if current:
        chunks.append(current)

    return chunks


def chunk_text(
    text: str,
    parent_id: str,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
    model: str = "text-embedding-3-small",
) -> list[Chunk]:
    """Split text into overlapping chunks with parent_id linkage.

    Returns a single-element list if the text fits within max_tokens.
    """
    encoding = tiktoken.encoding_for_model(model)
    token_count = _count_tokens(text, encoding)

    if token_count <= max_tokens:
        return [Chunk(text=text, index=0, parent_id=parent_id)]

    raw_chunks = _recursive_split(text, max_tokens, encoding)

    if overlap_tokens > 0 and len(raw_chunks) > 1:
        overlapped: list[str] = [raw_chunks[0]]
        for i in range(1, len(raw_chunks)):
            prev_tokens = encoding.encode(raw_chunks[i - 1])
            overlap_text = encoding.decode(prev_tokens[-overlap_tokens:])
            overlapped.append(overlap_text + raw_chunks[i])
        raw_chunks = overlapped

    return [
        Chunk(text=chunk, index=i, parent_id=parent_id)
        for i, chunk in enumerate(raw_chunks)
        if chunk.strip()
    ]
