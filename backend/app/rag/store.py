"""Thread-safe in-memory document chunk repository for uploaded drawings and active projects.

Enables instant hybrid retrieval, parameter extraction, and deterministic calculation
even when running locally without a remote Supabase pgvector instance.
"""

from typing import Any
import threading

from app.ingestion.models import ExtractedChunk

_LOCK = threading.Lock()

# Seed baseline structural drawing schedule (Sheet S-02 Rev 03)
DEFAULT_SEED_CHUNKS: list[dict[str, Any]] = [
    {
        "chunk_id": "seed-c12-sched",
        "drawing_id": "drawing-s02",
        "content": "COLUMN SCHEDULE (Sheet S-02, Rev 03): Column C12 (Grid 3-B): Storey clear height 3000 mm, main longitudinal reinforcement 4-T16 bars (Fe500 steel), development length into footing embedment 800 mm. Lateral ties 8 mm dia @ 150 mm c/c. Concrete grade M25, clear cover 40 mm. Standard 90 deg hook anchorage at foundation base.",
        "page_number": 1,
        "entity_code": "C12",
        "entity_type": "COLUMN",
        "metadata": {"source_reference": "Sheet S-02 / Page 1 / Grid 3-B"},
        "keyword_score": 0.9,
        "semantic_score": 0.85,
        "combined_score": 0.88,
        "source_reference": "Sheet S-02 / Page 1 / Grid 3-B",
    },
    {
        "chunk_id": "seed-b4-sched",
        "drawing_id": "drawing-s03",
        "content": "BEAM SCHEDULE (Sheet S-03, Rev 02): Beam B4 (Span 5000 mm): Clear span 5000 mm, support column width 300 mm. Bottom reinforcement 3-T20 bars (Fe500), top hanger bars 2-T12. Stirrups 8 mm 2-legged @ 125 mm c/c. Development length Ld = 50d anchored into column core per IS 456 Cl 26.2.1.",
        "page_number": 2,
        "entity_code": "B4",
        "entity_type": "BEAM",
        "metadata": {"source_reference": "Sheet S-03 / Page 2 / Beam Schedule"},
        "keyword_score": 0.85,
        "semantic_score": 0.8,
        "combined_score": 0.83,
        "source_reference": "Sheet S-03 / Page 2 / Beam Schedule",
    },
    {
        "chunk_id": "seed-f1-sched",
        "drawing_id": "drawing-s01",
        "content": "FOOTING SCHEDULE (Sheet S-01, Rev 01): Isolated Footing F1 (2000 mm x 2000 mm x 600 mm depth). Bottom reinforcement mesh: T12 @ 150 mm c/c both ways. Concrete grade M25, bottom cover 50 mm. End 90 deg U-hooks provided per SP 34 Section 4. Column C12 dowel embedment = 800 mm.",
        "page_number": 1,
        "entity_code": "F1",
        "entity_type": "FOOTING",
        "metadata": {"source_reference": "Sheet S-01 / Page 1 / Footing Detail"},
        "keyword_score": 0.85,
        "semantic_score": 0.8,
        "combined_score": 0.83,
        "source_reference": "Sheet S-01 / Page 1 / Footing Detail",
    },
    {
        "chunk_id": "seed-general-notes",
        "drawing_id": "drawing-s00",
        "content": "GENERAL STRUCTURAL SPECIFICATIONS (Sheet S-00): All reinforcement steel shall conform to IS 1786 High Yield Strength Deformed (HYSD) Fe 500. Concrete for all columns and footings shall be M25 minimum. Bar bending schedules must account for standard bend deductions per IS 2502: 1d for 45 deg, 2d for 90 deg, 3d for 135 deg.",
        "page_number": 1,
        "entity_code": "GENERAL",
        "entity_type": "SPECIFICATION",
        "metadata": {"source_reference": "Sheet S-00 / Page 1 / Notes"},
        "keyword_score": 0.7,
        "semantic_score": 0.75,
        "combined_score": 0.72,
        "source_reference": "Sheet S-00 / Page 1 / Notes",
    },
]

_STORE: list[dict[str, Any]] = list(DEFAULT_SEED_CHUNKS)


def add_chunks(chunks: list[ExtractedChunk], drawing_id: str = "uploaded-doc") -> None:
    """Store extracted PDF chunks into active memory store."""
    with _LOCK:
        for c in chunks:
            _STORE.append(
                {
                    "chunk_id": f"{drawing_id}-{c.chunk_index}",
                    "drawing_id": drawing_id,
                    "content": c.content,
                    "page_number": c.page_number,
                    "entity_code": c.entity_code,
                    "entity_type": c.entity_type,
                    "metadata": {"source_reference": c.source_reference},
                    "source_reference": c.source_reference,
                }
            )


def get_all_chunks() -> list[dict[str, Any]]:
    """Return all stored drawing chunks."""
    with _LOCK:
        return list(_STORE)


def clear_uploaded_chunks() -> None:
    """Reset store back to default seed chunks."""
    global _STORE
    with _LOCK:
        _STORE = list(DEFAULT_SEED_CHUNKS)
