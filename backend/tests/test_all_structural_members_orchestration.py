import pytest
from app.rag.orchestrator import AskQuestionRequest, orchestrate_drawing_question
from app.rag.store import get_all_chunks
from app.rag.supabase_client import SupabaseRAGClient


@pytest.mark.parametrize(
    "question,expected_member_id,expected_type",
    [
        ("What is the cutting length of slab S1 main reinforcement?", "S1", "SLAB"),
        ("Calculate the rebar BBS for bored pile P1?", "P1", "PILE"),
        ("What is the bar schedule for pile cap PC1?", "PC1", "PILE_CAP"),
        ("Generate cutting length and BBS for staircase flight ST1?", "ST1", "STAIRCASE"),
        ("What is the cutting length for bridge pier PR1 vertical reinforcement?", "PR1", "PIER"),
        ("Calculate the cutting length and BBS for retaining wall RW1?", "RW1", "RETAINING_WALL"),
        ("What is the cutting length for beam B4 longitudinal bars?", "B4", "BEAM"),
        ("Calculate the rebar mesh cutting length for footing F1?", "F1", "FOOTING"),
        ("What is the cutting length of column C12 main reinforcement?", "C12", "COLUMN"),
    ],
)
def test_all_structural_members_orchestrate_successfully(
    question: str, expected_member_id: str, expected_type: str
) -> None:
    client = SupabaseRAGClient(supabase_url="", supabase_key="")
    chunks = get_all_chunks()

    req = AskQuestionRequest(
        question=question,
        candidate_chunks_cache=chunks,
    )
    res = orchestrate_drawing_question(req, client=client)

    assert res.status == "completed"
    assert res.parsed_question.member_id == expected_member_id
    assert res.calculation is not None
    assert res.calculation.member_id == expected_member_id
    assert res.calculation.member_type == expected_type
    assert res.calculation.cutting_length_m > 0
    assert res.calculation.total_weight_kg > 0
    assert expected_member_id in res.answer
