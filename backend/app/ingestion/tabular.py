"""Tabular and CSV Structural Bar Schedule Ingestion Service.

Parses structural bar bending schedules from CSV / TSV text files, identifies
structural member codes (e.g. C12, B4, F1, S1), reinforcement details, and
generates page-cited ExtractedChunk models for the hybrid retrieval engine.
"""

import csv
import io
import re
from typing import Any
from app.ingestion.models import ExtractedChunk, ExtractionResult


MEMBER_PATTERN = re.compile(r"\b([A-Z]{1,3}\d{1,3}[A-Z]?)\b")


def parse_tabular_schedule(
    csv_text: str,
    file_name: str = "schedule.csv",
) -> ExtractionResult:
    """Parse CSV / TSV bar schedule into document chunks with structural entity tags.

    Args:
        csv_text: Raw string contents of CSV or TSV file.
        file_name: Original uploaded file name.

    Returns:
        ExtractionResult with chunk models suitable for hybrid retrieval.
    """
    reader = csv.reader(io.StringIO(csv_text.strip()))
    rows = list(reader)

    if not rows:
        return ExtractionResult(
            file_name=file_name,
            page_count=1,
            chunks=[],
            full_text="",
        )

    header = [h.strip().lower() for h in rows[0]]
    chunks: list[ExtractedChunk] = []
    full_lines: list[str] = [", ".join(rows[0])]

    for row_idx, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue

        row_dict = {}
        for col_idx, cell in enumerate(row):
            col_name = header[col_idx] if col_idx < len(header) else f"col_{col_idx}"
            row_dict[col_name] = cell.strip()

        line_str = ", ".join(f"{k}: {v}" for k, v in row_dict.items() if v)
        full_lines.append(line_str)

        # Detect member code
        entity_code = None
        for val in row_dict.values():
            m = MEMBER_PATTERN.search(val)
            if m:
                entity_code = m.group(1).upper()
                break

        # If not in values, check if member is specified in headers or first column
        if not entity_code and len(row) > 0:
            first_val = row[0].strip().upper()
            if MEMBER_PATTERN.match(first_val):
                entity_code = first_val

        # Classify entity type
        entity_type = "GENERAL"
        if entity_code:
            if entity_code.startswith("C"):
                entity_type = "COLUMN"
            elif entity_code.startswith("B"):
                entity_type = "BEAM"
            elif entity_code.startswith("F") or entity_code.startswith("RF") or "RAFT" in entity_code:
                entity_type = "FOOTING"
            elif entity_code.startswith("S"):
                entity_type = "SLAB"
            elif entity_code.startswith("P") and not entity_code.startswith("PC") and not entity_code.startswith("PR"):
                entity_type = "PILE"
            elif entity_code.startswith("PC"):
                entity_type = "PILE_CAP"
            elif entity_code.startswith("ST"):
                entity_type = "STAIRCASE"
            elif entity_code.startswith("PR"):
                entity_type = "PIER"
            elif entity_code.startswith("RW"):
                entity_type = "RETAINING_WALL"

        chunk_content = (
            f"TABULAR SCHEDULE ROW (File: {file_name}, Line {row_idx}): "
            + "; ".join(f"{k} = {v}" for k, v in row_dict.items() if v)
        )

        chunk = ExtractedChunk(
            content=chunk_content,
            page_number=1,
            chunk_index=row_idx,
            entity_code=entity_code,
            entity_type=entity_type,
            source_reference=f"{file_name} / Row {row_idx}",
            embedding=None,
        )
        chunks.append(chunk)

    return ExtractionResult(
        file_name=file_name,
        page_count=1,
        chunks=chunks,
        full_text="\n".join(full_lines),
    )
