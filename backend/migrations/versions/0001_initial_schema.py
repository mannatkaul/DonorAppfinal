"""Create donor, donation, payment, material, and receipt tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

payment_status = sa.Enum("created", "failed", "succeeded", name="payment_status")
material_status = sa.Enum(
    "pending_approval", "approved", "rejected", "scheduled", "received", name="material_status"
)
pickup_method = sa.Enum("pickup", "dropoff", name="pickup_method")
receipt_kind = sa.Enum("monetary", "material", name="receipt_kind")


def upgrade() -> None:
    op.create_table(
        "donors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_donors_full_name", "donors", ["full_name"])

    op.create_table(
        "donations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("donor_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("cause", sa.String(length=160), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_donations_amount_positive"),
        sa.CheckConstraint("currency = 'INR'", name="ck_donations_currency_inr"),
        sa.ForeignKeyConstraint(["donor_id"], ["donors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_donations_donor_id", "donations", ["donor_id"])
    op.create_index("ix_donations_donor_created", "donations", ["donor_id", "created_at"])

    op.create_table(
        "material_donations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("donor_id", sa.Uuid(), nullable=False),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("pickup_method", pickup_method, nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("preferred_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", material_status, nullable=False),
        sa.Column("admin_note", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_material_donations_quantity_positive"),
        sa.ForeignKeyConstraint(["donor_id"], ["donors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_material_donations_donor_id", "material_donations", ["donor_id"])
    op.create_index(
        "ix_material_donations_donor_created", "material_donations", ["donor_id", "created_at"]
    )
    op.create_index(
        "ix_material_donations_status_created", "material_donations", ["status", "created_at"]
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("donation_id", sa.Uuid(), nullable=False),
        sa.Column("donor_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("gateway_order_id", sa.String(length=128), nullable=True),
        sa.Column("gateway_payment_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.ForeignKeyConstraint(["donation_id"], ["donations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["donor_id"], ["donors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("donor_id", "idempotency_key", name="uq_payments_donor_idempotency"),
        sa.UniqueConstraint("gateway_order_id"),
        sa.UniqueConstraint("gateway_payment_id", name="uq_payments_gateway_payment_id"),
    )
    op.create_index("ix_payments_donation_id", "payments", ["donation_id"])
    op.create_index("ix_payments_donor_id", "payments", ["donor_id"])
    op.create_index("ix_payments_status_created", "payments", ["status", "created_at"])

    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_number", sa.String(length=40), nullable=False),
        sa.Column("kind", receipt_kind, nullable=False),
        sa.Column("donor_id", sa.Uuid(), nullable=False),
        sa.Column("donation_id", sa.Uuid(), nullable=True),
        sa.Column("material_donation_id", sa.Uuid(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(donation_id IS NOT NULL AND material_donation_id IS NULL) OR "
            "(donation_id IS NULL AND material_donation_id IS NOT NULL)",
            name="ck_receipts_exactly_one_donation",
        ),
        sa.ForeignKeyConstraint(["donor_id"], ["donors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["donation_id"], ["donations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["material_donation_id"], ["material_donations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("donation_id", name="uq_receipts_donation_id"),
        sa.UniqueConstraint("material_donation_id", name="uq_receipts_material_donation_id"),
        sa.UniqueConstraint("receipt_number"),
    )
    op.create_index("ix_receipts_donor_id", "receipts", ["donor_id"])


def downgrade() -> None:
    op.drop_index("ix_receipts_donor_id", table_name="receipts")
    op.drop_table("receipts")
    op.drop_index("ix_payments_status_created", table_name="payments")
    op.drop_index("ix_payments_donor_id", table_name="payments")
    op.drop_index("ix_payments_donation_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_material_donations_status_created", table_name="material_donations")
    op.drop_index("ix_material_donations_donor_created", table_name="material_donations")
    op.drop_index("ix_material_donations_donor_id", table_name="material_donations")
    op.drop_table("material_donations")
    op.drop_index("ix_donations_donor_created", table_name="donations")
    op.drop_index("ix_donations_donor_id", table_name="donations")
    op.drop_table("donations")
    op.drop_index("ix_donors_full_name", table_name="donors")
    op.drop_table("donors")
    op.execute("DROP TYPE receipt_kind")
    op.execute("DROP TYPE payment_status")
    op.execute("DROP TYPE material_status")
    op.execute("DROP TYPE pickup_method")
