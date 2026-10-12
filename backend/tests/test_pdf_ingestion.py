from app.ingestion.pdf import chunk_text


def test_chunk_text_preserves_content_and_overlap() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    chunks = chunk_text(text, chunk_size=28, overlap=8)
    assert len(chunks) >= 2
    assert chunks[0].startswith("alpha")
    assert any("gamma" in chunk for chunk in chunks[1:])


def test_chunk_text_rejects_invalid_overlap() -> None:
    try:
        chunk_text("drawing text", chunk_size=100, overlap=100)
    except ValueError as error:
        assert "greater" in str(error)
    else:
        raise AssertionError("Expected a ValueError")
