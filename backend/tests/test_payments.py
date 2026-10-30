import hashlib
import hmac
import json

from app import payments
from app.settings import settings


def register(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "payer@example.com",
            "full_name": "Test Payer",
            "password": "Secure-password-123",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_donation(client, headers, amount="25.00"):
    response = client.post(
        "/api/donations",
        headers=headers,
        json={"amount": amount, "cause": "Food security"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def configure_provider(monkeypatch, provider_status="captured"):
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_id")
    monkeypatch.setattr(settings, "razorpay_key_secret", "rzp_test_secret")
    created_orders = []

    def create_order(amount, currency, receipt):
        order = {
            "id": f"order_{len(created_orders) + 1}",
            "amount": int(amount * 100),
            "currency": currency,
        }
        created_orders.append(order)
        return order

    monkeypatch.setattr(payments, "create_order", create_order)
    monkeypatch.setattr(payments, "verify_checkout_signature", lambda *_: True)
    fetched_count = 0

    def fetch_payment(payment_id):
        nonlocal fetched_count
        order = created_orders[fetched_count]
        fetched_count += 1
        return {
            "id": payment_id,
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "status": provider_status,
        }

    monkeypatch.setattr(payments, "fetch_payment", fetch_payment)
    return created_orders


def test_payment_only_succeeds_after_provider_capture_and_is_idempotent(
    client, monkeypatch
):
    headers = register(client)
    created_orders = configure_provider(monkeypatch)
    donation_id = make_donation(client, headers)
    checkout = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "checkout-one"},
    )
    assert checkout.status_code == 201
    order_id = checkout.json()["order_id"]
    repeated_checkout = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "checkout-one"},
    )
    assert repeated_checkout.status_code == 201
    assert repeated_checkout.json()["order_id"] == order_id
    assert len(created_orders) == 1
    verify_payload = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_1",
        "razorpay_signature": "test-signature",
    }

    paid = client.post("/api/payments/verify", headers=headers, json=verify_payload)
    assert paid.status_code == 200
    assert paid.json()["status"] == "succeeded"
    assert paid.json()["verified_at"] is not None
    repeated = client.post("/api/payments/verify", headers=headers, json=verify_payload)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == paid.json()["id"]

    second_donation = make_donation(client, headers, "25.00")
    second_checkout = client.post(
        f"/api/donations/{second_donation}/checkout",
        headers={**headers, "Idempotency-Key": "checkout-two"},
    )
    assert second_checkout.status_code == 201
    duplicate_transaction = client.post(
        "/api/payments/verify",
        headers=headers,
        json={
            "razorpay_order_id": second_checkout.json()["order_id"],
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "test-signature",
        },
    )
    assert duplicate_transaction.status_code == 409

    stats = client.get("/api/dashboard/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["verified_monetary_total"] == "25.00"
    assert stats.json()["monetary_donation_count"] == 1
    receipts = client.get("/api/receipts", headers=headers)
    assert receipts.status_code == 200
    assert len(receipts.json()) == 1
    document = client.get(
        f"/api/receipts/{receipts.json()[0]['id']}/document", headers=headers
    )
    assert document.status_code == 200
    assert "INR 25.00" in document.text
    assert len(created_orders) == 2


def test_authorized_or_unsigned_payment_is_never_marked_successful(client, monkeypatch):
    headers = register(client)
    configure_provider(monkeypatch, provider_status="authorized")
    donation_id = make_donation(client, headers, "10.00")
    checkout = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "checkout-auth-only"},
    )
    order_id = checkout.json()["order_id"]

    monkeypatch.setattr(payments, "verify_checkout_signature", lambda *_: False)
    rejected_signature = client.post(
        "/api/payments/verify",
        headers=headers,
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "not-valid",
        },
    )
    assert rejected_signature.status_code == 400

    monkeypatch.setattr(payments, "verify_checkout_signature", lambda *_: True)
    not_captured = client.post(
        "/api/payments/verify",
        headers=headers,
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "test-signature",
        },
    )
    assert not_captured.status_code == 400
    payments_list = client.get("/api/donations", headers=headers)
    assert payments_list.status_code == 200
    assert payments_list.json()[0]["status"] == "pending"
    assert client.get("/api/receipts", headers=headers).json() == []
    stats = client.get("/api/dashboard/stats", headers=headers)
    assert stats.json()["verified_monetary_total"] == "0.00"
    assert stats.json()["monetary_donation_count"] == 0


def test_checkout_disabled_without_razorpay_credentials(client, monkeypatch):
    headers = register(client)
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")
    donation_id = make_donation(client, headers)
    response = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "no-provider"},
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_live_razorpay_key_is_rejected(client, monkeypatch):
    headers = register(client)
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_live_not-allowed")
    monkeypatch.setattr(settings, "razorpay_key_secret", "some-secret")
    donation_id = make_donation(client, headers)
    response = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "live-key"},
    )
    assert response.status_code == 503
    assert "test credentials" in response.json()["detail"]


def test_failed_payment_requires_provider_confirmation(client, monkeypatch):
    headers = register(client)
    configure_provider(monkeypatch, provider_status="captured")
    donation_id = make_donation(client, headers, "15.00")
    checkout = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "checkout-failure"},
    )
    payment_id = checkout.json()["payment_id"]

    unconfirmed = client.post(
        f"/api/payments/{payment_id}/failure",
        headers=headers,
        json={"reason": "The checkout was cancelled", "razorpay_payment_id": "pay_1"},
    )
    assert unconfirmed.status_code == 409
    assert client.get("/api/receipts", headers=headers).json() == []

    monkeypatch.setattr(
        payments,
        "fetch_payment",
        lambda provider_payment_id: {
            "id": provider_payment_id,
            "order_id": checkout.json()["order_id"],
            "status": "failed",
            "error_description": "Payment declined",
        },
    )
    failed = client.post(
        f"/api/payments/{payment_id}/failure",
        headers=headers,
        json={"reason": "Bank declined", "razorpay_payment_id": "pay_1"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["failure_reason"] == "Payment declined"


def test_signed_webhook_confirms_and_deduplicates_captured_payment(client, monkeypatch):
    headers = register(client)
    configure_provider(monkeypatch)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "webhook-test-secret")
    donation_id = make_donation(client, headers, "32.50")
    checkout = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "webhook-checkout"},
    )
    order_id = checkout.json()["order_id"]
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook",
                        "order_id": order_id,
                        "amount": 3250,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
    ).encode()
    signature = hmac.new(
        b"webhook-test-secret", body, hashlib.sha256
    ).hexdigest()

    response = client.post(
        "/api/payments/razorpay/webhook",
        content=body,
        headers={"X-Razorpay-Signature": signature},
    )
    assert response.status_code == 204
    repeated = client.post(
        "/api/payments/razorpay/webhook",
        content=body,
        headers={"X-Razorpay-Signature": signature},
    )
    assert repeated.status_code == 204

    stats = client.get("/api/dashboard/stats", headers=headers)
    assert stats.json()["verified_monetary_total"] == "32.50"
    assert stats.json()["monetary_donation_count"] == 1
    assert len(client.get("/api/receipts", headers=headers).json()) == 1


def test_webhook_rejects_bad_signature_without_changing_payment(client, monkeypatch):
    headers = register(client)
    configure_provider(monkeypatch)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "webhook-test-secret")
    donation_id = make_donation(client, headers, "12.00")
    checkout = client.post(
        f"/api/donations/{donation_id}/checkout",
        headers={**headers, "Idempotency-Key": "bad-webhook"},
    )
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_bad",
                        "order_id": checkout.json()["order_id"],
                        "amount": 1200,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
    )
    response = client.post(
        "/api/payments/razorpay/webhook",
        content=body,
        headers={"X-Razorpay-Signature": "invalid"},
    )
    assert response.status_code == 400
    assert client.get("/api/receipts", headers=headers).json() == []
