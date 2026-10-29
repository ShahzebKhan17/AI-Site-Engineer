from app.rag.question_parser import parse_drawing_question


def test_parses_column_cutting_length_question() -> None:
    parsed = parse_drawing_question("What is the cutting length of steel for column no C12?")
    assert parsed.member_type == "column"
    assert parsed.member_id == "C12"
    assert parsed.calculation_intent == "cutting_length"
    assert not parsed.needs_clarification


def test_marks_ambiguous_question_for_clarification() -> None:
    parsed = parse_drawing_question("Is this drawing approved?")
    assert parsed.needs_clarification
    assert parsed.member_id is None


def test_parses_raft_foundation_rebar_question() -> None:
    parsed = parse_drawing_question("What is the dia of steel in raft?")
    assert parsed.member_type == "footing"
    assert parsed.member_id == "RAFT"
    assert parsed.calculation_intent == "cutting_length"
    assert not parsed.needs_clarification


def test_parses_raft_numbered_foundation_question() -> None:
    parsed = parse_drawing_question("What is the reinforcement for raft foundation RF1?")
    assert parsed.member_type == "footing"
    assert parsed.member_id == "RF1"
    assert parsed.calculation_intent == "cutting_length"
    assert not parsed.needs_clarification


def test_parses_hyphenated_column_concrete_question() -> None:
    parsed = parse_drawing_question("what is the quantity of concrete required for the column C-01")
    assert parsed.member_type == "column"
    assert parsed.member_id == "C-01"
    assert parsed.calculation_intent == "concrete_volume"
    assert not parsed.needs_clarification


def test_parses_hyphenated_code_without_member_word() -> None:
    parsed = parse_drawing_question("what is the quantity of concrete required for the C-01")
    assert parsed.member_type == "column"
    assert parsed.member_id == "C-01"
    assert parsed.calculation_intent == "concrete_volume"
    assert not parsed.needs_clarification

