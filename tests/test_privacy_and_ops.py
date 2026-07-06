from pathlib import Path

from app.audit import safe_changed_fields
from app.security import mask_chart_number, mask_name


def test_privacy_masking_helpers():
    assert mask_name("홍길동") == "홍*동"
    assert mask_chart_number("C20260001") == "C2*****01"


def test_audit_log_masks_sensitive_fields():
    result = safe_changed_fields({"patient_name": "홍길동", "status": "예약", "phone_last4": "1234"})

    assert result["patient_name"] == "[masked]"
    assert result["phone_last4"] == "[masked]"
    assert result["status"] == "예약"


def test_backup_restore_scripts_exist_and_avoid_patient_names():
    root = Path(__file__).resolve().parents[1]
    backup = root / "scripts" / "backup_postgres.sh"
    restore = root / "scripts" / "restore_postgres.sh"

    assert backup.exists()
    assert restore.exists()
    assert "patient" not in backup.read_text(encoding="utf-8").lower()

