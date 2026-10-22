import pytest
from app.engineering.qa_qc import (
    create_qa_audit_certificate,
    generate_sha256_stamp,
    verify_civil_compliance,
)


def test_sha256_determinism():
    """Verify that identical payloads produce identical cryptographic SHA-256 signatures."""
    payload1 = {"member_id": "C12", "length": 4389.4, "status": "APPROVED"}
    payload2 = {"status": "APPROVED", "length": 4389.4, "member_id": "C12"}  # different key order
    assert generate_sha256_stamp(payload1) == generate_sha256_stamp(payload2)


def test_qa_audit_certificate_generation():
    """Verify certificate generation and compliance checklist for Column C12."""
    calc_data = {
        "cutting_length_mm": 4389.4,
        "cutting_length_m": 4.389,
        "total_weight_kg": 27.74,
    }

    cert = create_qa_audit_certificate(
        calculation_data=calc_data,
        engineer_name="Er. Shahzeb Khan",
        engineer_license="SE/2026/DL-09",
        project_id="Apex Tower",
        member_id="C12",
        member_type="COLUMN",
    )

    assert cert.certificate_id.startswith("QA-")
    assert len(cert.verification_hash) == 64  # SHA-256 is 64 hex characters
    assert cert.is_compliant is True
    assert cert.sign_off_status == "CERTIFIED"
    assert len(cert.compliance_checks) >= 4

    # Verify column specific rule exists
    assert any("26.2.5.1" in c.rule_code for c in cert.compliance_checks)


def test_qa_audit_certificate_flagging_on_invalid_data():
    """Verify that negative or zero cutting length triggers an audit failure."""
    invalid_data = {
        "cutting_length_mm": -100.0,
        "cutting_length_m": -0.1,
        "total_weight_kg": 0.0,
    }

    cert = create_qa_audit_certificate(
        calculation_data=invalid_data,
        member_id="BAD_COL",
        member_type="COLUMN",
    )

    assert cert.is_compliant is False
    assert cert.sign_off_status == "REJECTED_AUDIT_FAILURE"
    assert any(c.status == "FLAGGED" for c in cert.compliance_checks)
