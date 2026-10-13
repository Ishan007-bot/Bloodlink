"""initial schema: donors, hospitals, blood units, requests, allocations

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "donors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("blood_group", sa.String(3), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, server_default=""),
        sa.Column("city", sa.String(80), nullable=False, server_default=""),
        sa.Column("last_donation_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_donors_blood_group", "donors", ["blood_group"])

    op.create_table(
        "hospitals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("contact_phone", sa.String(20), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "blood_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("donor_id", sa.Integer(), sa.ForeignKey("donors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("blood_group", sa.String(3), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="AVAILABLE"),
    )
    op.create_index("ix_blood_units_blood_group", "blood_units", ["blood_group"])
    op.create_index("ix_blood_units_expires_at", "blood_units", ["expires_at"])
    op.create_index("ix_blood_units_status", "blood_units", ["status"])

    op.create_table(
        "blood_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "hospital_id", sa.Integer(), sa.ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("patient_ref", sa.String(60), nullable=False, server_default=""),
        sa.Column("blood_group", sa.String(3), nullable=False),
        sa.Column("units_needed", sa.Integer(), nullable=False),
        sa.Column("units_allocated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="ROUTINE"),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("fulfilled_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_blood_requests_status", "blood_requests", ["status"])

    op.create_table(
        "allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "request_id", sa.Integer(), sa.ForeignKey("blood_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("blood_units.id"), nullable=False, unique=True),
        sa.Column("match_type", sa.String(10), nullable=False),
        sa.Column("allocated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("allocations")
    op.drop_index("ix_blood_requests_status", table_name="blood_requests")
    op.drop_table("blood_requests")
    op.drop_index("ix_blood_units_status", table_name="blood_units")
    op.drop_index("ix_blood_units_expires_at", table_name="blood_units")
    op.drop_index("ix_blood_units_blood_group", table_name="blood_units")
    op.drop_table("blood_units")
    op.drop_table("hospitals")
    op.drop_index("ix_donors_blood_group", table_name="donors")
    op.drop_table("donors")
