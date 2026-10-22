import pytest
from app.ingestion.tabular import parse_tabular_schedule


def test_parse_csv_bar_schedule():
    """Verify parsing CSV bar schedule into chunks with member entity tags."""
    sample_csv = """Member,Bar Mark,Diameter,Spacing,Length,Steel
C15,Main Long,16,-,4200,Fe500
B8,Bottom Bar,20,150,5800,Fe500
F3,Mesh Rebar,12,150,2200,Fe500
"""

    result = parse_tabular_schedule(sample_csv, file_name="structural_schedule.csv")

    assert result.file_name == "structural_schedule.csv"
    assert len(result.chunks) == 3

    # Check first chunk for Column C15
    c1 = result.chunks[0]
    assert c1.entity_code == "C15"
    assert c1.entity_type == "COLUMN"
    assert "C15" in c1.content
    assert "structural_schedule.csv / Row 2" in c1.source_reference

    # Check second chunk for Beam B8
    c2 = result.chunks[1]
    assert c2.entity_code == "B8"
    assert c2.entity_type == "BEAM"

    # Check third chunk for Footing F3
    c3 = result.chunks[2]
    assert c3.entity_code == "F3"
    assert c3.entity_type == "FOOTING"


def test_parse_empty_csv():
    """Verify safe fallback on empty or whitespace CSV text."""
    result = parse_tabular_schedule("", file_name="empty.csv")
    assert len(result.chunks) == 0
    assert result.file_name == "empty.csv"
