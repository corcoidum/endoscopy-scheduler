"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "patients_minimal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chart_number", sa.String(length=40), nullable=False),
        sa.Column("patient_name", sa.String(length=80), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(length=10), nullable=False),
        sa.Column("phone_last4", sa.String(length=4), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("chart_number", name="uq_patients_chart_number"),
    )
    op.create_index("ix_patients_minimal_chart_number", "patients_minimal", ["chart_number"])
    op.create_index("ix_patients_minimal_patient_name", "patients_minimal", ["patient_name"])

    op.create_table(
        "endoscopy_appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients_minimal.id"), nullable=False),
        sa.Column("appointment_date", sa.Date(), nullable=False),
        sa.Column("appointment_time", sa.Time(), nullable=False),
        sa.Column("procedure_type", sa.String(length=120), nullable=False),
        sa.Column("endoscopy_type", sa.String(length=40), nullable=False),
        sa.Column("ultrasound_abdomen", sa.Boolean(), nullable=False),
        sa.Column("ultrasound_thyroid", sa.Boolean(), nullable=False),
        sa.Column("ultrasound_carotid", sa.Boolean(), nullable=False),
        sa.Column("ultrasound_cardiac", sa.Boolean(), nullable=False),
        sa.Column("sedation", sa.Boolean(), nullable=False),
        sa.Column("preparation_status", sa.String(length=20), nullable=False),
        sa.Column("medication_check_required", sa.Boolean(), nullable=False),
        sa.Column("bowel_prep_type", sa.String(length=40), nullable=True),
        sa.Column("guardian_notice", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=255), nullable=True),
        sa.Column("override_reason", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_endoscopy_appointments_patient_id", "endoscopy_appointments", ["patient_id"])
    op.create_index("ix_endoscopy_appointments_appointment_date", "endoscopy_appointments", ["appointment_date"])
    op.create_index("ix_endoscopy_appointments_appointment_time", "endoscopy_appointments", ["appointment_time"])
    op.create_index("ix_endoscopy_appointments_status", "endoscopy_appointments", ["status"])

    op.create_table(
        "schedule_capacity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("max_capacity", sa.Integer(), nullable=False),
        sa.Column("procedure_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("changed_fields", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("holiday_date", sa.Date(), nullable=False, unique=True),
        sa.Column("description", sa.String(length=120), nullable=True),
        sa.Column("is_endoscopy_available", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "retention_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("completed_retention_days", sa.Integer(), nullable=False),
        sa.Column("anonymize_name", sa.Boolean(), nullable=False),
        sa.Column("anonymize_phone_last4", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("retention_policies")
    op.drop_table("holidays")
    op.drop_table("audit_logs")
    op.drop_table("schedule_capacity")
    op.drop_table("endoscopy_appointments")
    op.drop_table("patients_minimal")
    op.drop_table("users")
