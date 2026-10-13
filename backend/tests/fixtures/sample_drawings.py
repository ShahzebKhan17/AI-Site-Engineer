"""Sample civil structural drawing fixtures and PDF generator for testing."""

SAMPLE_COLUMN_SCHEDULE_PAGE_1 = (
    "PROJECT: G+8 RESIDENTIAL APARTMENTS (REV 03)\n"
    "GENERAL NOTES FOR COLUMNS:\n"
    "1. All dimensions are in mm unless otherwise specified.\n"
    "2. Grade of concrete for columns: M25 (IS 456 Table 2).\n"
    "3. Grade of steel: Fe500 TMT bars (IS 1786).\n"
    "4. Clear cover to longitudinal reinforcement = 40 mm.\n"
    "5. Lap length shall be calculated as per IS 456 Cl. 26.2.5.1."
)

SAMPLE_COLUMN_SCHEDULE_PAGE_2 = (
    "SCHEDULE OF COLUMNS (GROUND TO 1ST FLOOR):\n"
    "Column C10: Size 300x450 mm, 4-T16 + 2-T12, Storey height 3000 mm.\n"
    "Column C11: Size 300x500 mm, 6-T16 bars, Storey height 3000 mm.\n"
    "Column C12: Size 300x600 mm, 4-T16 longitudinal rebar, Storey height 3000 mm, Footing embedment 500 mm.\n"
    "Column C13: Size 300x600 mm, 6-T20 longitudinal rebar, Storey height 3000 mm, Footing embedment 600 mm."
)

SAMPLE_FOUNDATION_SCHEDULE_PAGE_3 = (
    "FOUNDATION & ISOLATED FOOTING DETAILS (REV 03):\n"
    "Footing F-12 (under Column C12): Depth D = 600 mm, Embedment depth = 500 mm.\n"
    "Column dowel horizontal leg in footing shall be minimum 300 mm (SP 34 Cl. 3.3 standard 90 deg bend).\n"
    "Cover to footing bottom rebar: 50 mm."
)


def generate_sample_drawing_pdf(pages: list[str] | None = None) -> bytes:
    """Generate a valid multi-page PDF byte buffer containing civil drawing text."""
    page_texts = pages or [
        SAMPLE_COLUMN_SCHEDULE_PAGE_1,
        SAMPLE_COLUMN_SCHEDULE_PAGE_2,
        SAMPLE_FOUNDATION_SCHEDULE_PAGE_3,
    ]

    font_id = 3 + len(page_texts) * 2
    page_ids = [3 + i * 2 for i in range(len(page_texts))]
    content_ids = [4 + i * 2 for i in range(len(page_texts))]

    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_obj = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_texts)} >>".encode("ascii")

    body: list[bytes] = [catalog, pages_obj]
    for i, p_text in enumerate(page_texts):
        cid = content_ids[i]
        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {cid} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode("ascii")

        # Clean text for PDF single-line string syntax
        clean_text = p_text.replace("\n", " ").replace("(", "\\(").replace(")", "\\)")
        stream_data = f"BT /F1 11 Tf 40 720 Td ({clean_text}) Tj ET".encode("latin1")
        stream_obj = (
            f"<< /Length {len(stream_data)} >>\nstream\n".encode("ascii")
            + stream_data
            + b"\nendstream"
        )
        body.append(page_dict)
        body.append(stream_obj)

    font_obj = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    body.append(font_obj)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for idx, obj in enumerate(body, 1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_offset = len(out)
    out.extend(f"xref\n0 {len(body) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(body) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii")
    )
    return bytes(out)
