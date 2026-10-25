"""Tests for Gemini Multimodal Document & Drawing Extraction."""

import json
from unittest.mock import MagicMock, patch

from app.ingestion.gemini import (
    _parse_gemini_json_response,
    extract_with_gemini,
    is_gemini_available,
)
from app.routers.drawings import extract_drawing
from fastapi import UploadFile
import pytest


def test_gemini_availability_reflects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert not is_gemini_available()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    assert is_gemini_available()


def test_parse_gemini_json_response_structures_members_and_chunks() -> None:
    sample_response = {
        "page_count": 2,
        "chunks": [
            {
                "content": "Column C12 detail: 4-T16 bars, clear height 3200mm, M25 concrete, Fe500 steel.",
                "page_number": 1,
                "source_reference": "drawing:sample.pdf#page=1",
                "entity_code": "C12",
                "entity_type": "column",
            }
        ],
        "extracted_members": [
            {
                "member_id": "C12",
                "member_type": "column",
                "dimensions": {
                    "width_mm": 400.0,
                    "depth_mm": 600.0,
                    "storey_height_mm": 3200.0,
                    "footing_embedment_mm": 500.0,
                },
                "main_bar_diameter_mm": 16.0,
                "secondary_bar_diameter_mm": 8.0,
                "spacing_mm": 150.0,
                "concrete_grade": "M25",
                "steel_grade": "FE500",
                "reinforcement_summary": "4-T16 longitudinal bars, 8mm ties @ 150 c/c",
                "confidence": 0.99,
                "citations": ["Page 1: Column Schedule"],
                "notes": ["Clear cover 40mm"],
            }
        ],
    }

    raw_text = json.dumps(sample_response)
    result = _parse_gemini_json_response(raw_text, "structural_drawings.pdf")

    assert result.file_name == "structural_drawings.pdf"
    assert result.page_count == 2
    assert len(result.chunks) == 1
    assert result.chunks[0].entity_code == "C12"

    assert len(result.extracted_members) == 1
    m = result.extracted_members[0]
    assert m.member_id == "C12"
    assert m.member_type == "column"
    assert m.main_bar_diameter_mm == 16.0
    assert m.secondary_bar_diameter_mm == 8.0
    assert m.spacing_mm == 150.0
    assert m.concrete_grade == "M25"
    assert m.steel_grade == "FE500"
    assert m.dimensions["width_mm"] == 400.0
    assert m.dimensions["depth_mm"] == 600.0
    assert m.confidence == 0.99


def test_parse_gemini_json_handles_markdown_fences() -> None:
    sample_json = {
        "page_count": 1,
        "chunks": [{"content": "Beam B4: 3-T20 top, 3-T25 bottom", "page_number": 1}],
        "extracted_members": [
            {
                "member_id": "B4",
                "member_type": "beam",
                "dimensions": {"width_mm": 300.0, "depth_mm": 500.0, "length_mm": 4500.0},
                "main_bar_diameter_mm": 25.0,
                "secondary_bar_diameter_mm": 8.0,
                "spacing_mm": 175.0,
                "concrete_grade": "M30",
                "steel_grade": "FE500",
            }
        ],
    }
    raw_text = f"```json\n{json.dumps(sample_json)}\n```"
    result = _parse_gemini_json_response(raw_text, "beam_schedule.pdf")
    assert len(result.extracted_members) == 1
    assert result.extracted_members[0].member_id == "B4"
    assert result.extracted_members[0].concrete_grade == "M30"
