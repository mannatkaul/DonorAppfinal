import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import MaterialStatus, PaymentStatus, PickupMethod, ReceiptKind


class DonorCreate(BaseModel):
    email: EmailStr
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
    password: Annotated[str, Field(min_length=12, max_length=128)]
    phone: Annotated[str | None, Field(max_length=32)] = None
    address: Annotated[str | None, Field(max_length=500)] = None


class DonorUpdate(BaseModel):
    full_name: Annotated[str | None, Field(min_length=2, max_length=160)] = None
    phone: Annotated[str | None, Field(max_length=32)] = None
    address: Annotated[str | None, Field(max_length=500)] = None


class DonorRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    address: str | None
    is_admin: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenRead(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    donor: DonorRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class DonationCreate(BaseModel):
    amount: Annotated[Decimal, Field(gt=0, le=1_000_000, max_digits=12, decimal_places=2)]
    cause: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
    note: Annotated[str | None, Field(max_length=1000)] = None
    is_anonymous: bool = False


class DonationRead(BaseModel):
    id: uuid.UUID
    donor_id: uuid.UUID
    amount: Decimal
    currency: str
    cause: str
    note: str | None
    is_anonymous: bool
    status: Literal["pending", "failed", "succeeded"]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckoutRead(BaseModel):
    donation_id: uuid.UUID
    payment_id: uuid.UUID
    key_id: str
    order_id: str
    amount: int
    currency: str


class PaymentVerify(BaseModel):
    razorpay_order_id: Annotated[str, Field(min_length=1, max_length=128)]
    razorpay_payment_id: Annotated[str, Field(min_length=1, max_length=128)]
    razorpay_signature: Annotated[str, Field(min_length=1, max_length=256)]


class PaymentFailure(BaseModel):
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    razorpay_payment_id: Annotated[str, Field(min_length=1, max_length=128)]


class PaymentRead(BaseModel):
    id: uuid.UUID
    donation_id: uuid.UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    gateway_order_id: str | None
    gateway_payment_id: str | None
    failure_reason: str | None
    verified_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaterialDonationCreate(BaseModel):
    item_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
    description: Annotated[str | None, Field(max_length=1000)] = None
    quantity: Annotated[int, Field(gt=0, le=100_000)]
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    pickup_method: PickupMethod
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
    preferred_date: AwareDatetime | None = None


class MaterialDonationRead(BaseModel):
    id: uuid.UUID
    donor_id: uuid.UUID
    item_name: str
    description: str | None
    quantity: int
    unit: str
    pickup_method: PickupMethod
    address: str
    preferred_date: datetime | None
    scheduled_for: datetime | None
    status: MaterialStatus
    admin_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaterialDecision(BaseModel):
    status: Literal["approved", "rejected"]
    admin_note: Annotated[str | None, Field(max_length=1000)] = None


class MaterialSchedule(BaseModel):
    scheduled_for: AwareDatetime
    admin_note: Annotated[str | None, Field(max_length=1000)] = None


class MaterialReceive(BaseModel):
    confirmation_note: Annotated[str | None, Field(max_length=1000)] = None


class ReceiptRead(BaseModel):
    id: uuid.UUID
    receipt_number: str
    kind: ReceiptKind
    donor_id: uuid.UUID
    donation_id: uuid.UUID | None
    material_donation_id: uuid.UUID | None
    issued_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardStats(BaseModel):
    donor_count: int
    monetary_donation_count: int
    verified_monetary_total: Decimal
    material_donation_count: int
    pending_material_count: int
