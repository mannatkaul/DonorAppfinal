import hashlib
import hmac
from decimal import Decimal
from typing import Any

import requests
from fastapi import HTTPException, status

from app.settings import settings

RAZORPAY_API = "https://api.razorpay.com/v1"


def require_razorpay() -> tuple[str, str]:
    if not settings.razorpay_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay test credentials are not configured; checkout is disabled.",
        )
    return settings.razorpay_key_id, settings.razorpay_key_secret


def create_order(amount: Decimal, currency: str, receipt: str) -> dict[str, Any]:
    key_id, key_secret = require_razorpay()
    paise = int(amount * 100)
    try:
        response = requests.post(
            f"{RAZORPAY_API}/orders",
            auth=(key_id, key_secret),
            json={"amount": paise, "currency": currency, "receipt": receipt},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider could not create an order.",
        ) from exc
    try:
        data: dict[str, Any] = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider returned an invalid order response.",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider returned an invalid order response.",
        )
    if data.get("amount") != paise or data.get("currency") != currency or not data.get("id"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider returned an invalid order.",
        )
    return data


def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    _, key_secret = require_razorpay()
    expected = hmac.new(
        key_secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def fetch_payment(payment_id: str) -> dict[str, Any]:
    key_id, key_secret = require_razorpay()
    try:
        response = requests.get(
            f"{RAZORPAY_API}/payments/{payment_id}",
            auth=(key_id, key_secret),
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider could not verify the payment status.",
        ) from exc
    try:
        data: dict[str, Any] = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider returned an invalid payment response.",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider returned an invalid payment response.",
        )
    return data


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        return False
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
