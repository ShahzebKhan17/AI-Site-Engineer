"""Thread-safe in-memory document chunk repository for uploaded drawings and active projects.

Enables instant hybrid retrieval, parameter extraction, and deterministic calculation
even when running locally without a remote Supabase pgvector instance.
"""

from typing import Any
import threading

from app.ingestion.models import ExtractedChunk

_LOCK = threading.Lock()

# Standard baseline structural drawing schedule specifications (Sheets S-01 to S-09)
DEFAULT_SPECIFICATION_CHUNKS: list[dict[str, Any]] = [
    {
        "chunk_id": "spec-c12-sched",
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
        "chunk_id": "spec-b4-sched",
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
        "chunk_id": "spec-f1-sched",
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
        "chunk_id": "spec-s1-sched",
        "drawing_id": "drawing-s04",
        "content": "SLAB SCHEDULE (Sheet S-04, Rev 01): Two-Way Slab S1: Shorter clear span Lx = 3000 mm, longer clear span Ly = 4500 mm, slab thickness D = 150 mm. Support beam bearing = 230 mm. Main bottom reinforcement T10 @ 150 mm c/c with alternate cranked bars at 0.15Lx. Distribution reinforcement T8 @ 175 mm c/c. Clear cover 20 mm, concrete grade M25, steel Fe500.",
        "page_number": 1,
        "entity_code": "S1",
        "entity_type": "SLAB",
        "metadata": {"source_reference": "Sheet S-04 / Page 1 / Slab Detail"},
        "keyword_score": 0.88,
        "semantic_score": 0.85,
        "combined_score": 0.86,
        "source_reference": "Sheet S-04 / Page 1 / Slab Detail",
    },
    {
        "chunk_id": "spec-p1-sched",
        "drawing_id": "drawing-s05",
        "content": "PILE FOUNDATION SCHEDULE (Sheet S-05, Rev 02): Bored Cast-in-Situ RC Pile P1: Pile shaft diameter 600 mm, depth 12.0 m below cut-off level. Longitudinal cage reinforcement: 8-T20 bars (Fe500). Pile head dowel embedment into pile cap = 800 mm. Lateral reinforcement: continuous helical spiral 8 mm dia @ 150 mm pitch. Master stiffener rings 16 mm dia @ 2.0 m c/c. Clear cover 50 mm, concrete grade M25.",
        "page_number": 1,
        "entity_code": "P1",
        "entity_type": "PILE",
        "metadata": {"source_reference": "Sheet S-05 / Page 1 / Pile Detail"},
        "keyword_score": 0.88,
        "semantic_score": 0.85,
        "combined_score": 0.86,
        "source_reference": "Sheet S-05 / Page 1 / Pile Detail",
    },
    {
        "chunk_id": "spec-pc1-sched",
        "drawing_id": "drawing-s06",
        "content": "PILE CAP SCHEDULE (Sheet S-06, Rev 01): 4-Pile Cap PC1: Length 2400 mm, width 2400 mm, depth 1000 mm. Bottom tension rebar mesh: T20 @ 150 mm c/c both ways with vertical hook legs. Top nominal mesh: T12 @ 200 mm c/c. Column starter dowels: 8-T20 bars. Concrete grade M25, steel grade Fe500, clear cover 50 mm.",
        "page_number": 1,
        "entity_code": "PC1",
        "entity_type": "PILE_CAP",
        "metadata": {"source_reference": "Sheet S-06 / Page 1 / Pile Cap Schedule"},
        "keyword_score": 0.88,
        "semantic_score": 0.85,
        "combined_score": 0.86,
        "source_reference": "Sheet S-06 / Page 1 / Pile Cap Schedule",
    },
    {
        "chunk_id": "spec-st1-sched",
        "drawing_id": "drawing-s07",
        "content": "STAIRCASE SCHEDULE (Sheet S-07, Rev 01): Dog-Legged Staircase ST1: Flight width 1200 mm, waist slab thickness 150 mm. 10 risers @ 150 mm, 9 treads @ 250 mm. Top and bottom landing lengths 1200 mm. Main tensile waist reinforcement: T12 @ 150 mm c/c anchored Ld into landings. Distribution rebar: T8 @ 175 mm c/c. Concrete grade M25, steel Fe500, clear cover 20 mm.",
        "page_number": 1,
        "entity_code": "ST1",
        "entity_type": "STAIRCASE",
        "metadata": {"source_reference": "Sheet S-07 / Page 1 / Staircase Detail"},
        "keyword_score": 0.88,
        "semantic_score": 0.85,
        "combined_score": 0.86,
        "source_reference": "Sheet S-07 / Page 1 / Staircase Detail",
    },
    {
        "chunk_id": "spec-pr1-sched",
        "drawing_id": "drawing-s08",
        "content": "PIER & PEDESTAL SCHEDULE (Sheet S-08, Rev 01): Rectangular Bridge Pier PR1: Cross-section 800 mm x 800 mm, clear height 3000 mm. Main vertical reinforcement: 12-T25 bars (Fe500). Footing starter embedment 800 mm. Lateral confining ties: 10 mm dia @ 150 mm c/c with 135 deg seismic hooks (10d tails). Clear cover 40 mm, concrete grade M35.",
        "page_number": 1,
        "entity_code": "PR1",
        "entity_type": "PIER",
        "metadata": {"source_reference": "Sheet S-08 / Page 1 / Pier Detail"},
        "keyword_score": 0.88,
        "semantic_score": 0.85,
        "combined_score": 0.86,
        "source_reference": "Sheet S-08 / Page 1 / Pier Detail",
    },
    {
        "chunk_id": "spec-rw1-sched",
        "drawing_id": "drawing-s09",
        "content": "CANTILEVER RETAINING WALL (Sheet S-09, Rev 01): Retaining Wall RW1: Stem height 3500 mm, stem base thickness 400 mm, base slab width 2400 mm, thickness 400 mm, toe projection 600 mm. Main earth face vertical reinforcement: T16 @ 150 mm c/c with 90 deg L-anchor into heel slab; alternate bars curtailed at H/2. Horizontal distribution: T10 @ 200 mm c/c both faces. Concrete grade M25, steel Fe500, cover 50 mm.",
        "page_number": 1,
        "entity_code": "RW1",
        "entity_type": "RETAINING_WALL",
        "metadata": {"source_reference": "Sheet S-09 / Page 1 / Retaining Wall Detail"},
        "keyword_score": 0.88,
        "semantic_score": 0.85,
        "combined_score": 0.86,
        "source_reference": "Sheet S-09 / Page 1 / Retaining Wall Detail",
    },
    {
        "chunk_id": "spec-general-notes",
        "drawing_id": "drawing-s00",
        "content": "GENERAL STRUCTURAL SPECIFICATIONS (Sheet S-00): All reinforcement steel shall conform to IS 1786 High Yield Strength Deformed (HYSD) Fe 500. Concrete for all columns, beams, slabs, and footings shall be M25 minimum. Bar bending schedules must account for standard bend deductions per IS 2502: 1d for 45 deg, 2d for 90 deg, 3d for 135 deg.",
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

DEFAULT_SEED_CHUNKS = DEFAULT_SPECIFICATION_CHUNKS

_STORE: list[dict[str, Any]] = list(DEFAULT_SPECIFICATION_CHUNKS)


def add_chunks(chunks: list[ExtractedChunk], drawing_id: str = "uploaded-drawing") -> None:
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
    """Reset store back to default reference specification chunks."""
    global _STORE
    with _LOCK:
        _STORE = list(DEFAULT_SPECIFICATION_CHUNKS)


def delete_drawing_chunks(drawing_id: str) -> int:
    """Remove chunks associated with a specific drawing from active memory store."""
    global _STORE
    with _LOCK:
        initial_len = len(_STORE)
        _STORE = [
            c for c in _STORE
            if c.get("drawing_id") != drawing_id
            and not (c.get("source_reference", "").startswith(f"drawing:{drawing_id}") or c.get("source_reference", "").startswith(f"image:{drawing_id}") or drawing_id in c.get("source_reference", ""))
        ]
        return initial_len - len(_STORE)
