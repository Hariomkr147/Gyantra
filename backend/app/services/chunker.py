"""
Chunking strategies for long documents.

Design goals:
 - Produce semantic chunks that respect heading boundaries.
 - Keep each chunk small enough to fit in free-model context windows.
 - Preserve source references (block IDs / page numbers) on every chunk.
 - Support the retrieval layer so later stages can request only relevant chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import settings
from app.models.enums import BlockType
from app.models.schemas import TextBlock


@dataclass
class Chunk:
    id: str
    text: str
    heading_path: str = ""  # "Section > Subsection" breadcrumb
    block_ids: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    summary: str = ""  # compact one-line summary (filled after LLM pass)
    concept_ids: list[str] = field(default_factory=list)

    @property
    def token_estimate(self) -> int:
        """Rough token count: ~4 chars per token for English."""
        return max(1, len(self.text) // 4)


def _block_text(block: TextBlock) -> str:
    """Renderable text for a block, including any caption."""
    if block.caption:
        return f"{block.content}\n[Caption: {block.caption}]"
    return block.content


@dataclass
class _Section:
    """One heading-delimited region of the document."""

    heading_path: str
    text: str = ""
    block_ids: list[str] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)

    @property
    def tokens(self) -> int:
        return max(1, len(self.text) // 4)


def _split_into_sections(blocks: list[TextBlock]) -> list[_Section]:
    """Group blocks into sections, starting a new one at every heading."""
    sections: list[_Section] = []
    heading_stack: list[str] = []
    current: _Section | None = None

    def path() -> str:
        return " > ".join(h for h in heading_stack if h)

    for block in blocks:
        if block.block_type == BlockType.HEADING:
            # Close the previous section before the stack changes.
            if current and current.text.strip():
                sections.append(current)

            level = max(1, block.level or 1)
            # Pop to the parent of this level, padding if levels were skipped.
            while len(heading_stack) >= level:
                heading_stack.pop()
            while len(heading_stack) < level - 1:
                heading_stack.append("")
            heading_stack.append(block.content.strip())

            current = _Section(heading_path=path())

        if current is None:
            # Content before the first heading (preamble).
            current = _Section(heading_path="")

        text = _block_text(block)
        current.text = f"{current.text}\n{text}" if current.text else text
        current.block_ids.append(block.id)
        if block.page:
            current.pages.add(block.page)

    if current and current.text.strip():
        sections.append(current)

    return sections


def _hard_wrap(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Split text with no line breaks at word boundaries.

    Needed because a single very long paragraph has no newline to split on, and
    an unsplit chunk would overflow the model's context window.
    """
    parts: list[str] = []
    buffer = ""
    for word in text.split(" "):
        projected = f"{buffer} {word}" if buffer else word
        if len(projected) > target_chars and buffer:
            parts.append(buffer)
            tail = buffer[-overlap_chars:] if overlap_chars and len(buffer) > overlap_chars else ""
            buffer = f"{tail} {word}".strip() if tail else word
        else:
            buffer = projected
    if buffer.strip():
        parts.append(buffer)
    return parts


def _split_oversized(section: _Section, target: int, overlap: int) -> list[_Section]:
    """Break a section that exceeds the token target into size-bounded parts."""
    target_chars = target * 4
    overlap_chars = overlap * 4

    if len(section.text) <= target_chars:
        return [section]

    def make(text: str) -> _Section:
        return _Section(
            heading_path=section.heading_path,
            text=text,
            block_ids=list(section.block_ids),
            pages=set(section.pages),
        )

    parts: list[_Section] = []
    buffer = ""

    for line in section.text.split("\n"):
        # A single line longer than the target must itself be wrapped.
        if len(line) > target_chars:
            if buffer.strip():
                parts.append(make(buffer))
                buffer = ""
            for piece in _hard_wrap(line, target_chars, overlap_chars):
                parts.append(make(piece))
            continue

        projected = f"{buffer}\n{line}" if buffer else line
        if len(projected) > target_chars and buffer:
            parts.append(make(buffer))
            tail = buffer[-overlap_chars:] if overlap_chars and len(buffer) > overlap_chars else ""
            buffer = f"{tail}\n{line}" if tail else line
        else:
            buffer = projected

    if buffer.strip():
        parts.append(make(buffer))

    return parts


def _merge_small(sections: list[_Section], min_tokens: int, target: int) -> list[_Section]:
    """Fold negligible sections into their neighbour.

    A lone chapter-title heading or a two-line stub is not worth its own LLM
    call, but a normal-sized section keeps its own chunk so extraction stays
    section-scoped and traceable.
    """
    merged: list[_Section] = []
    for section in sections:
        if (
            merged
            and section.tokens < min_tokens
            and merged[-1].tokens + section.tokens <= target
        ):
            prev = merged[-1]
            prev.text = f"{prev.text}\n{section.text}"
            prev.block_ids.extend(section.block_ids)
            prev.pages |= section.pages
            continue

        if (
            merged
            and merged[-1].tokens < min_tokens
            and merged[-1].tokens + section.tokens <= target
        ):
            # The *previous* section was the stub (e.g. a bare chapter title):
            # absorb it forward so its heading still leads the merged chunk.
            prev = merged.pop()
            section.text = f"{prev.text}\n{section.text}"
            section.block_ids = prev.block_ids + section.block_ids
            section.pages |= prev.pages
            section.heading_path = section.heading_path or prev.heading_path

        merged.append(section)

    return merged


def _cap_chunk_count(sections: list[_Section], max_chunks: int, target: int) -> list[_Section]:
    """Merge neighbours until the section count fits the budget.

    Guards against a document with hundreds of tiny headings turning into
    hundreds of LLM calls.
    """
    if len(sections) <= max_chunks:
        return sections

    # Allow chunks to grow past the target here; staying under the call budget
    # matters more than perfect section alignment on pathological inputs.
    limit = target * 2
    result: list[_Section] = []
    for section in sections:
        if result and result[-1].tokens + section.tokens <= limit:
            prev = result[-1]
            prev.text = f"{prev.text}\n{section.text}"
            prev.block_ids.extend(section.block_ids)
            prev.pages |= section.pages
        else:
            result.append(section)

    if len(result) > max_chunks:
        # Still over budget: take the largest-granularity pass available.
        buckets: list[_Section] = []
        per_bucket = (len(result) + max_chunks - 1) // max_chunks
        for i in range(0, len(result), per_bucket):
            group = result[i : i + per_bucket]
            head = group[0]
            for extra in group[1:]:
                head.text = f"{head.text}\n{extra.text}"
                head.block_ids.extend(extra.block_ids)
                head.pages |= extra.pages
            buckets.append(head)
        result = buckets

    return result


def chunk_by_headings(
    blocks: list[TextBlock],
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[Chunk]:
    """Split a block list into semantic chunks at heading boundaries.

    Three passes:
      1. Group blocks into sections, one per heading.
      2. Split any section that exceeds the token target.
      3. Merge negligible sections, then cap the total chunk count.

    The result respects document structure (so extraction stays section-scoped
    and citable) while keeping every chunk inside the token budget.
    """
    target = target_tokens or settings.chunk_target_tokens
    overlap = overlap_tokens or settings.chunk_overlap_tokens
    min_tokens = settings.min_chunk_tokens

    sections = _split_into_sections(blocks)
    if not sections:
        return []

    sized: list[_Section] = []
    for section in sections:
        sized.extend(_split_oversized(section, target, overlap))

    sized = _merge_small(sized, min_tokens, target)
    sized = _cap_chunk_count(sized, settings.max_chunks, target)

    return [
        Chunk(
            id=f"chunk-{i}",
            text=section.text.strip(),
            heading_path=section.heading_path,
            block_ids=section.block_ids,
            pages=sorted(section.pages),
        )
        for i, section in enumerate(sized)
        if section.text.strip()
    ]


def chunk_flat(
    text: str,
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[Chunk]:
    """Fallback splitting for documents without heading structure."""
    target = target_tokens or settings.chunk_target_tokens
    overlap = overlap_tokens or settings.chunk_overlap_tokens
    target_chars = target * 4

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Chunk] = []
    current = ""
    chunk_idx = 0

    for para in paragraphs:
        projected = current + "\n\n" + para if current else para
        if len(projected) > target_chars and current:
            chunks.append(Chunk(id=f"chunk-{chunk_idx}", text=current))
            chunk_idx += 1
            overlap_chars = overlap * 4
            tail = current[-overlap_chars:] if len(current) > overlap_chars else ""
            current = tail + "\n\n" + para if tail else para
        else:
            current = projected

    if current.strip():
        chunks.append(Chunk(id=f"chunk-{chunk_idx}", text=current))

    return chunks


class SectionIndex:
    """Lightweight retrieval index over chunks.

    Allows later stages to request only the chunks relevant to a particular
    concept, heading, or keyword — instead of re-feeding the entire document.
    """

    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._by_heading: dict[str, list[Chunk]] = {}
        self._by_concept: dict[str, list[Chunk]] = {}
        for c in chunks:
            h = c.heading_path.lower()
            self._by_heading.setdefault(h, []).append(c)

    def search(
        self,
        queries: list[str],
        max_results: int | None = None,
    ) -> list[Chunk]:
        """Keyword-based retrieval.  Simple but deterministic."""
        max_r = max_results or settings.max_source_snippets_per_stage
        scored: list[tuple[Chunk, int]] = []
        seen: set[str] = set()
        for q in queries:
            ql = q.lower()
            for ch in self._chunks:
                if ch.id in seen:
                    continue
                score = ch.text.lower().count(ql) * 2 + ch.heading_path.lower().count(ql) * 5
                if score:
                    scored.append((ch, score))
                    seen.add(ch.id)
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:max_r]]

    def chunk_by_id(self, chunk_id: str) -> Chunk | None:
        for c in self._chunks:
            if c.id == chunk_id:
                return c
        return None

    def get_for_concept(self, concept_name: str, max_results: int = 3) -> list[Chunk]:
        """Return chunks likely relevant to a concept."""
        return self.search([concept_name], max_results=max_results)

    def all_chunks(self) -> list[Chunk]:
        return list(self._chunks)
