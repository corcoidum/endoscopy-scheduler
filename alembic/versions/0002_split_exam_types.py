"""split endoscopy and ultrasound exam fields

Revision ID: 0002_split_exam_types
Revises: 0001_initial
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from alembic import op


revision = "0002_split_exam_types"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("endoscopy_appointments", sa.Column("endoscopy_type", sa.String(length=40), nullable=False, server_default="위내시경"))
    op.add_column("endoscopy_appointments", sa.Column("ultrasound_abdomen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("endoscopy_appointments", sa.Column("ultrasound_thyroid", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("endoscopy_appointments", sa.Column("ultrasound_carotid", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("endoscopy_appointments", sa.Column("ultrasound_cardiac", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_endoscopy_appointments_endoscopy_type", "endoscopy_appointments", ["endoscopy_type"])


def downgrade() -> None:
    op.drop_index("ix_endoscopy_appointments_endoscopy_type", table_name="endoscopy_appointments")
    op.drop_column("endoscopy_appointments", "ultrasound_cardiac")
    op.drop_column("endoscopy_appointments", "ultrasound_carotid")
    op.drop_column("endoscopy_appointments", "ultrasound_thyroid")
    op.drop_column("endoscopy_appointments", "ultrasound_abdomen")
    op.drop_column("endoscopy_appointments", "endoscopy_type")
