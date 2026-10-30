import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaymentStatus(str, enum.Enum):
    created = "created"
    failed = "failed"
    succeeded = "succeeded"


class MaterialStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    scheduled = "scheduled"
    received = "received"


class PickupMethod(str, enum.Enum):
    pickup = "pickup"
    dropoff = "dropoff"


class ReceiptKind(str, enum.Enum):
    monetary = "monetary"
    material = "material"


class Donor(Base):
    __tablename__ = "donors"
    __table_args__ = (Index("ix_donors_full_name", "full_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(String(500))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    donations: Mapped[list["Donation"]] = relationship(back_populates="donor")
    material_donations: Mapped[list["MaterialDonation"]] = relationship(back_populates="donor")


class Donation(Base):
    __tablename__ = "donations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_donations_amount_positive"),
        CheckConstraint("currency = 'INR'", name="ck_donations_currency_inr"),
        Index("ix_donations_donor_created", "donor_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    cause: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    donor: Mapped[Donor] = relationship(back_populates="donations")
    payments: Mapped[list["Payment"]] = relationship(back_populates="donation")
    receipt: Mapped["Receipt | None"] = relationship(back_populates="donation", uselist=False)

    @property
    def status(self) -> str:
        if self.receipt is not None:
            return "succeeded"
        if any(payment.status == PaymentStatus.created for payment in self.payments):
            return "pending"
        if self.payments and all(payment.status == PaymentStatus.failed for payment in self.payments):
            return "failed"
        return "pending"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        UniqueConstraint("gateway_payment_id", name="uq_payments_gateway_payment_id"),
        UniqueConstraint("donor_id", "idempotency_key", name="uq_payments_donor_idempotency"),
        Index("ix_payments_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.created, nullable=False
    )
    gateway_order_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    donation: Mapped[Donation] = relationship(back_populates="payments")


class MaterialDonation(Base):
    __tablename__ = "material_donations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_material_donations_quantity_positive"),
        Index("ix_material_donations_donor_created", "donor_id", "created_at"),
        Index("ix_material_donations_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    pickup_method: Mapped[PickupMethod] = mapped_column(
        Enum(PickupMethod, name="pickup_method"), nullable=False
    )
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    preferred_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[MaterialStatus] = mapped_column(
        Enum(MaterialStatus, name="material_status"),
        default=MaterialStatus.pending_approval,
        nullable=False,
    )
    admin_note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    donor: Mapped[Donor] = relationship(back_populates="material_donations")
    receipt: Mapped["Receipt | None"] = relationship(back_populates="material_donation", uselist=False)


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("donation_id", name="uq_receipts_donation_id"),
        UniqueConstraint("material_donation_id", name="uq_receipts_material_donation_id"),
        CheckConstraint(
            "(donation_id IS NOT NULL AND material_donation_id IS NULL) OR "
            "(donation_id IS NULL AND material_donation_id IS NOT NULL)",
            name="ck_receipts_exactly_one_donation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    kind: Mapped[ReceiptKind] = mapped_column(Enum(ReceiptKind, name="receipt_kind"), nullable=False)
    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    donation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("donations.id", ondelete="RESTRICT")
    )
    material_donation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_donations.id", ondelete="RESTRICT")
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    donation: Mapped[Donation | None] = relationship(back_populates="receipt")
    material_donation: Mapped[MaterialDonation | None] = relationship(back_populates="receipt")
    donor: Mapped[Donor] = relationship()
