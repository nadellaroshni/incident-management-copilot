"""Runbook loading, chunking and BM25 retrieval. Standard library only."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "of", "on", "or", "the", "to", "was", "were", "with", "while", "will",
}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    runbook_id: str
    failure_mode: str
    title: str
    heading: str
    text: str


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower())
            if t not in _STOPWORDS and (len(t) > 1 or t.isdigit())]


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.index("\n---\n", 4)
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, text[end + len("\n---\n"):]


def split_sections(meta: dict, body: str) -> list[Chunk]:
    """Split a runbook into one chunk per '## ' section, keeping its identity on each chunk."""
    chunks: list[Chunk] = []
    heading = "Overview"
    buffer: list[str] = []

    def flush():
        text = "\n".join(buffer).strip()
        if text:
            chunks.append(Chunk(
                chunk_id=f"{meta['runbook_id']}#{len(chunks)}",
                runbook_id=meta["runbook_id"],
                failure_mode=meta["failure_mode"],
                title=meta.get("title", ""),
                heading=heading,
                text=text,
            ))

    for line in body.splitlines():
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            buffer = []
        else:
            buffer.append(line)
    flush()
    return chunks


def load_runbooks(root: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(root.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        if "runbook_id" not in meta or "failure_mode" not in meta:
            raise ValueError(f"{path.name}: front matter needs runbook_id and failure_mode")
        chunks.extend(split_sections(meta, body))
    return chunks


class BM25Index:
    """Okapi BM25 over runbook chunks. Fast enough for tens of documents, with no dependencies."""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        if not chunks:
            raise ValueError("no chunks to index")
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.docs = [Counter(tokenize(f"{c.heading} {c.text}")) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths) or 1.0
        df: Counter = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - count + 0.5) / (count + 0.5)) for t, count in df.items()}

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        terms = set(tokenize(query))
        scored = []
        for i, doc in enumerate(self.docs):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_length)
            for term in terms:
                freq = doc.get(term, 0)
                if freq:
                    score += self.idf[term] * freq * (self.k1 + 1) / (freq + norm)
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        return [(self.chunks[i], round(score, 4)) for score, i in scored[:k]]
