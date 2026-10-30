import json
from html import escape
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import payments
from app.database import get_db
from app.models import (
    Donation,
    Donor,
    MaterialDonation,
    MaterialStatus,
    Payment,
    PaymentStatus,
    Receipt,
    ReceiptKind,
)
from app.schemas import (
    CheckoutRead,
    DashboardStats,
    DonationCreate,
    DonationRead,
    DonorCreate,
    DonorRead,
    DonorUpdate,
    LoginRequest,
    MaterialDecision,
    MaterialDonationCreate,
    MaterialDonationRead,
    MaterialReceive,
    MaterialSchedule,
    PaymentFailure,
    PaymentRead,
    PaymentVerify,
    ReceiptRead,
    TokenRead,
)
from app.security import (
    create_access_token,
    get_current_donor,
    hash_password,
    require_admin,
    verify_password,
)
from app.settings import settings

router = APIRouter(prefix="/api")


def _new_receipt(
    db: Session,
    donor_id: uuid.UUID,
    kind: ReceiptKind,
    donation_id: uuid.UUID | None = None,
    material_donation_id: uuid.UUID | None = None,
) -> Receipt:
    receipt = Receipt(
        receipt_number=f"ASHA-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:12].upper()}",
        kind=kind,
        donor_id=donor_id,
        donation_id=donation_id,
        material_donation_id=material_donation_id,
    )
    db.add(receipt)
    return receipt


def _issue_payment_receipt(db: Session, payment: Payment) -> None:
    if payment.donation.receipt is None:
        _new_receipt(
            db,
            donor_id=payment.donor_id,
            kind=ReceiptKind.monetary,
            donation_id=payment.donation_id,
        )


def _validate_captured_payment(payment: Payment, provider_payment: dict) -> None:
    if (
        provider_payment.get("status") != "captured"
        or provider_payment.get("order_id") != payment.gateway_order_id
        or provider_payment.get("amount") != int(payment.amount * 100)
        or provider_payment.get("currency") != payment.currency
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The provider payment is not captured for this order and amount.",
        )


def _finalize_payment(db: Session, payment: Payment, provider_payment: dict) -> Payment:
    _validate_captured_payment(payment, provider_payment)
    provider_payment_id = provider_payment.get("id")
    if not provider_payment_id:
        raise HTTPException(status_code=400, detail="The provider did not return a payment ID.")

    existing = db.scalar(
        select(Payment).where(Payment.gateway_payment_id == provider_payment_id)
    )
    if existing is not None and existing.id != payment.id:
        raise HTTPException(status_code=409, detail="This provider transaction was already recorded.")
    if payment.status == PaymentStatus.succeeded:
        if payment.gateway_payment_id != provider_payment_id:
            raise HTTPException(status_code=409, detail="A different transaction completed this order.")
        return payment

    payment.gateway_payment_id = provider_payment_id
    payment.status = PaymentStatus.succeeded
    payment.failure_reason = None
    payment.verified_at = datetime.now(timezone.utc)
    _issue_payment_receipt(db, payment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This provider transaction was already recorded."
        ) from exc
    db.refresh(payment)
    return payment


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/register", response_model=TokenRead, status_code=status.HTTP_201_CREATED)
def register(payload: DonorCreate, db: Session = Depends(get_db)) -> TokenRead:
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(status_code=503, detail="JWT_SECRET_KEY is not configured.")
    donor = Donor(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        phone=payload.phone,
        address=payload.address,
    )
    db.add(donor)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    db.refresh(donor)
    access_token, expires_in = create_access_token(donor)
    return TokenRead(access_token=access_token, expires_in=expires_in, donor=donor)


@router.post("/donors", response_model=DonorRead, status_code=status.HTTP_201_CREATED)
def create_donor(
    payload: DonorCreate,
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Donor:
    donor = Donor(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        phone=payload.phone,
        address=payload.address,
    )
    db.add(donor)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    db.refresh(donor)
    return donor


@router.post("/auth/login", response_model=TokenRead)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenRead:
    donor = db.scalar(select(Donor).where(Donor.email == payload.email.lower()))
    if donor is None or not donor.is_active or not verify_password(
        payload.password, donor.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    access_token, expires_in = create_access_token(donor)
    return TokenRead(access_token=access_token, expires_in=expires_in, donor=donor)


@router.get("/donors/me", response_model=DonorRead)
def read_my_profile(donor: Donor = Depends(get_current_donor)) -> Donor:
    return donor


@router.patch("/donors/me", response_model=DonorRead)
def update_my_profile(
    payload: DonorUpdate,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> Donor:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(donor, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(donor)
    return donor


@router.get("/donors/me/donations", response_model=list[DonationRead])
def my_donations(
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> list[Donation]:
    return list(
        db.scalars(
            select(Donation)
            .where(Donation.donor_id == donor.id)
            .order_by(Donation.created_at.desc())
        )
    )


@router.get("/donors", response_model=list[DonorRead])
def list_donors(
    q: str | None = Query(default=None, max_length=160),
    active: bool | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Donor]:
    query = select(Donor)
    if q:
        term = f"%{q.strip()}%"
        query = query.where(Donor.full_name.ilike(term) | Donor.email.ilike(term))
    if active is not None:
        query = query.where(Donor.is_active == active)
    return list(db.scalars(query.order_by(Donor.created_at.desc()).offset(offset).limit(limit)))


@router.get("/donors/{donor_id}", response_model=DonorRead)
def read_donor(
    donor_id: uuid.UUID,
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Donor:
    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(status_code=404, detail="Donor not found.")
    return donor


@router.patch("/donors/{donor_id}", response_model=DonorRead)
def update_donor(
    donor_id: uuid.UUID,
    payload: DonorUpdate,
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Donor:
    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(status_code=404, detail="Donor not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(donor, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(donor)
    return donor


@router.delete("/donors/{donor_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_donor(
    donor_id: uuid.UUID,
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(status_code=404, detail="Donor not found.")
    donor.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/donations", response_model=DonationRead, status_code=status.HTTP_201_CREATED)
def create_donation(
    payload: DonationCreate,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> Donation:
    donation = Donation(
        donor_id=donor.id,
        amount=payload.amount.quantize(Decimal("0.01")),
        cause=payload.cause,
        note=payload.note,
        is_anonymous=payload.is_anonymous,
    )
    db.add(donation)
    db.commit()
    db.refresh(donation)
    return donation


@router.get("/donations", response_model=list[DonationRead])
def list_donations(
    donor_id: uuid.UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> list[Donation]:
    query = select(Donation)
    if donor.is_admin:
        if donor_id is not None:
            query = query.where(Donation.donor_id == donor_id)
    else:
        query = query.where(Donation.donor_id == donor.id)
    return list(
        db.scalars(query.order_by(Donation.created_at.desc()).offset(offset).limit(limit))
    )


@router.post(
    "/donations/{donation_id}/checkout",
    response_model=CheckoutRead,
    status_code=status.HTTP_201_CREATED,
)
def create_checkout(
    donation_id: uuid.UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> CheckoutRead:
    donation = db.scalar(
        select(Donation).where(Donation.id == donation_id).with_for_update()
    )
    if donation is None or (not donor.is_admin and donation.donor_id != donor.id):
        raise HTTPException(status_code=404, detail="Donation not found.")
    if donation.receipt is not None:
        raise HTTPException(status_code=409, detail="This donation has already been paid.")
    if idempotency_key:
        existing = db.scalar(
            select(Payment).where(
                Payment.donor_id == donor.id,
                Payment.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.donation_id != donation.id:
                raise HTTPException(
                    status_code=409, detail="This idempotency key belongs to another donation."
                )
            if existing.gateway_order_id:
                return CheckoutRead(
                    donation_id=donation.id,
                    payment_id=existing.id,
                    key_id=payments.require_razorpay()[0],
                    order_id=existing.gateway_order_id,
                    amount=int(existing.amount * 100),
                    currency=existing.currency,
                )
            raise HTTPException(
                status_code=409,
                detail="The previous checkout attempt failed; use a new idempotency key.",
            )

    active_payment = db.scalar(
        select(Payment).where(
            Payment.donation_id == donation.id,
            Payment.status == PaymentStatus.created,
        )
    )
    if active_payment is not None:
        if not active_payment.gateway_order_id:
            raise HTTPException(
                status_code=409,
                detail="A checkout order is being created; retry shortly.",
            )
        return CheckoutRead(
            donation_id=donation.id,
            payment_id=active_payment.id,
            key_id=payments.require_razorpay()[0],
            order_id=active_payment.gateway_order_id,
            amount=int(active_payment.amount * 100),
            currency=active_payment.currency,
        )

    payments.require_razorpay()
    payment = Payment(
        donation_id=donation.id,
        donor_id=donation.donor_id,
        amount=donation.amount,
        currency=donation.currency,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="The checkout request was duplicated; retry with the same key."
        ) from exc
    db.refresh(payment)

    try:
        order = payments.create_order(payment.amount, payment.currency, str(donation.id))
    except HTTPException as exc:
        payment.status = PaymentStatus.failed
        payment.failure_reason = str(exc.detail)[:500]
        db.commit()
        raise
    payment.gateway_order_id = order["id"]
    db.commit()
    return CheckoutRead(
        donation_id=donation.id,
        payment_id=payment.id,
        key_id=payments.require_razorpay()[0],
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
    )


@router.post("/payments/verify", response_model=PaymentRead)
def verify_payment(
    payload: PaymentVerify,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> Payment:
    payment = db.scalar(
        select(Payment)
        .where(Payment.gateway_order_id == payload.razorpay_order_id)
        .with_for_update()
    )
    if payment is None or (not donor.is_admin and payment.donor_id != donor.id):
        raise HTTPException(status_code=404, detail="Payment order not found.")
    if not payments.verify_checkout_signature(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="Payment signature verification failed.")
    if payment.status == PaymentStatus.succeeded:
        if payment.gateway_payment_id == payload.razorpay_payment_id:
            return payment
        raise HTTPException(status_code=409, detail="A different payment already completed this order.")
    provider_payment = payments.fetch_payment(payload.razorpay_payment_id)
    if provider_payment.get("id") != payload.razorpay_payment_id:
        raise HTTPException(status_code=400, detail="Payment provider returned a different transaction.")
    payment = _finalize_payment(db, payment, provider_payment)
    return payment


@router.post("/payments/{payment_id}/failure", response_model=PaymentRead)
def record_payment_failure(
    payment_id: uuid.UUID,
    payload: PaymentFailure,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> Payment:
    payment = db.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if payment is None or (not donor.is_admin and payment.donor_id != donor.id):
        raise HTTPException(status_code=404, detail="Payment not found.")
    if payment.status == PaymentStatus.succeeded:
        raise HTTPException(status_code=409, detail="A successful payment cannot be marked failed.")
    if not payment.gateway_order_id:
        raise HTTPException(status_code=409, detail="No payment-provider order exists for this attempt.")
    provider_payment = payments.fetch_payment(payload.razorpay_payment_id)
    if (
        provider_payment.get("id") != payload.razorpay_payment_id
        or provider_payment.get("status") != "failed"
        or provider_payment.get("order_id") != payment.gateway_order_id
    ):
        raise HTTPException(
            status_code=409,
            detail="The provider has not confirmed that this payment attempt failed.",
        )
    existing = db.scalar(
        select(Payment).where(
            Payment.gateway_payment_id == payload.razorpay_payment_id,
            Payment.id != payment.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This provider transaction was already recorded.")
    payment.status = PaymentStatus.failed
    payment.gateway_payment_id = payload.razorpay_payment_id
    payment.failure_reason = str(
        provider_payment.get("error_description") or payload.reason
    )[:500]
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/payments/razorpay/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
) -> Response:
    body = await request.body()
    if not signature or not payments.verify_webhook_signature(body, signature):
        raise HTTPException(status_code=400, detail="Webhook signature verification failed.")
    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Webhook payload is not valid JSON.") from exc

    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object.")
    event_type = event.get("event")
    payload = event.get("payload")
    payment_payload = payload.get("payment") if isinstance(payload, dict) else None
    entity = payment_payload.get("entity") if isinstance(payment_payload, dict) else None
    if not isinstance(entity, dict):
        raise HTTPException(status_code=400, detail="Webhook payment data is malformed.")
    order_id = entity.get("order_id")
    if event_type not in {"payment.captured", "payment.failed"} or not order_id:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    payment = db.scalar(
        select(Payment).where(Payment.gateway_order_id == order_id).with_for_update()
    )
    if payment is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if event_type == "payment.captured":
        _finalize_payment(db, payment, entity)
    elif payment.status != PaymentStatus.succeeded:
        provider_payment_id = entity.get("id")
        if entity.get("status") != "failed" or not provider_payment_id:
            raise HTTPException(status_code=400, detail="Failed-payment webhook data is incomplete.")
        existing = db.scalar(
            select(Payment).where(Payment.gateway_payment_id == provider_payment_id)
        )
        if existing is not None and existing.id != payment.id:
            raise HTTPException(status_code=409, detail="This provider transaction was already recorded.")
        payment.status = PaymentStatus.failed
        payment.gateway_payment_id = provider_payment_id
        payment.failure_reason = str(
            entity.get("error_description") or "Payment failed at the provider."
        )[:500]
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/material-donations",
    response_model=MaterialDonationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_material_donation(
    payload: MaterialDonationCreate,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> MaterialDonation:
    item = MaterialDonation(donor_id=donor.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/material-donations", response_model=list[MaterialDonationRead])
def list_material_donations(
    item_status: MaterialStatus | None = Query(default=None, alias="status"),
    donor_id: uuid.UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> list[MaterialDonation]:
    query = select(MaterialDonation)
    if not donor.is_admin:
        query = query.where(MaterialDonation.donor_id == donor.id)
    elif donor_id is not None:
        query = query.where(MaterialDonation.donor_id == donor_id)
    if item_status is not None:
        query = query.where(MaterialDonation.status == item_status)
    return list(
        db.scalars(query.order_by(MaterialDonation.created_at.desc()).offset(offset).limit(limit))
    )


@router.get("/material-donations/{material_id}", response_model=MaterialDonationRead)
def read_material_donation(
    material_id: uuid.UUID,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> MaterialDonation:
    item = db.get(MaterialDonation, material_id)
    if item is None or (not donor.is_admin and item.donor_id != donor.id):
        raise HTTPException(status_code=404, detail="Material donation not found.")
    return item


@router.post(
    "/admin/material-donations/{material_id}/decision",
    response_model=MaterialDonationRead,
)
def decide_material_donation(
    material_id: uuid.UUID,
    payload: MaterialDecision,
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MaterialDonation:
    item = db.scalar(
        select(MaterialDonation)
        .where(MaterialDonation.id == material_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Material donation not found.")
    if item.status != MaterialStatus.pending_approval:
        raise HTTPException(status_code=409, detail="Only pending items can be approved or rejected.")
    item.status = MaterialStatus(payload.status)
    item.admin_note = payload.admin_note
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/admin/material-donations/{material_id}/schedule",
    response_model=MaterialDonationRead,
)
def schedule_material_donation(
    material_id: uuid.UUID,
    payload: MaterialSchedule,
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MaterialDonation:
    item = db.scalar(
        select(MaterialDonation)
        .where(MaterialDonation.id == material_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Material donation not found.")
    if item.status != MaterialStatus.approved:
        raise HTTPException(status_code=409, detail="Only approved items can be scheduled.")
    if payload.scheduled_for <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="The schedule time must be in the future.")
    item.scheduled_for = payload.scheduled_for
    item.status = MaterialStatus.scheduled
    item.admin_note = payload.admin_note
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/admin/material-donations/{material_id}/receive",
    response_model=MaterialDonationRead,
)
def confirm_material_receipt(
    material_id: uuid.UUID,
    payload: MaterialReceive,
    _: Donor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MaterialDonation:
    item = db.scalar(
        select(MaterialDonation)
        .where(MaterialDonation.id == material_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Material donation not found.")
    if item.status != MaterialStatus.scheduled:
        raise HTTPException(status_code=409, detail="Only scheduled items can be confirmed as received.")
    item.status = MaterialStatus.received
    item.admin_note = payload.confirmation_note
    _new_receipt(
        db,
        donor_id=item.donor_id,
        kind=ReceiptKind.material,
        material_donation_id=item.id,
    )
    db.commit()
    db.refresh(item)
    return item


@router.get("/receipts", response_model=list[ReceiptRead])
def list_receipts(
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> list[Receipt]:
    query = select(Receipt)
    if not donor.is_admin:
        query = query.where(Receipt.donor_id == donor.id)
    return list(db.scalars(query.order_by(Receipt.issued_at.desc())))


@router.get("/receipts/{receipt_id}", response_model=ReceiptRead)
def read_receipt(
    receipt_id: uuid.UUID,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or (not donor.is_admin and receipt.donor_id != donor.id):
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return receipt


@router.get("/receipts/{receipt_id}/document", response_class=HTMLResponse)
def receipt_document(
    receipt_id: uuid.UUID,
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None or (not donor.is_admin and receipt.donor_id != donor.id):
        raise HTTPException(status_code=404, detail="Receipt not found.")
    if receipt.kind == ReceiptKind.monetary:
        donation = receipt.donation
        if donation is None or donation.receipt is None:
            raise HTTPException(status_code=409, detail="The monetary receipt is incomplete.")
        details = (
            f"<p>Amount: {escape(donation.currency)} {escape(format(donation.amount, '.2f'))}</p>"
            f"<p>Cause: {escape(donation.cause)}</p>"
        )
    else:
        item = receipt.material_donation
        if item is None:
            raise HTTPException(status_code=409, detail="The material receipt is incomplete.")
        details = (
            f"<p>Item: {escape(item.item_name)}</p>"
            f"<p>Quantity: {item.quantity} {escape(item.unit)}</p>"
            "<p>Confirmation: Received by the organization</p>"
        )
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Donation acknowledgment {escape(receipt.receipt_number)}</title></head>"
        "<body><main><h1>Hope Foundation</h1><h2>Donation acknowledgment</h2>"
        f"<p>Receipt: {escape(receipt.receipt_number)}</p>"
        f"<p>Donor: {escape(receipt.donor.full_name)}</p>{details}"
        f"<p>Issued: {escape(receipt.issued_at.isoformat())}</p>"
        "<p>This acknowledgment is not a tax certificate.</p>"
        "<button onclick=\"window.print()\">Print</button></main></body></html>"
    )
    return HTMLResponse(content=html)


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(
    donor: Donor = Depends(get_current_donor),
    db: Session = Depends(get_db),
) -> DashboardStats:
    donor_filter = [] if donor.is_admin else [Donation.donor_id == donor.id]
    material_filter = (
        [] if donor.is_admin else [MaterialDonation.donor_id == donor.id]
    )
    donor_count = (
        db.scalar(select(func.count(Donor.id)).where(Donor.is_active.is_(True))) or 0
        if donor.is_admin
        else 1
    )
    donation_count = db.scalar(
        select(func.count(func.distinct(Donation.id)))
        .join(Payment, Payment.donation_id == Donation.id)
        .where(Payment.status == PaymentStatus.succeeded, *donor_filter)
    ) or 0
    verified_total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(Donation, Payment.donation_id == Donation.id)
        .where(Payment.status == PaymentStatus.succeeded, *donor_filter)
    ) or Decimal("0.00")
    material_count = db.scalar(
        select(func.count(MaterialDonation.id)).where(*material_filter)
    ) or 0
    pending_material_count = db.scalar(
        select(func.count(MaterialDonation.id)).where(
            MaterialDonation.status == MaterialStatus.pending_approval,
            *material_filter,
        )
    ) or 0
    return DashboardStats(
        donor_count=donor_count,
        monetary_donation_count=donation_count,
        verified_monetary_total=verified_total,
        material_donation_count=material_count,
        pending_material_count=pending_material_count,
    )
