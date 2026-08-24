"""Shared, side-effect-free billing security primitives.

Platform subscription payments and school-fee payments are deliberately
different domains. This module contains only validation/signature helpers so
the Flask routes and future workers can enforce the same rules without
persisting credentials or payment payloads.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re


PLATFORM_SUBSCRIPTION_DOMAIN = "platform_subscription"
SCHOOL_FEE_DOMAIN = "school_fee"
ALLOWED_PAYMENT_METHODS = {"upi", "cash", "bank_transfer", "razorpay", "other"}
ALLOWED_PAYMENT_MODES = {"monthly", "half_yearly", "quarterly", "yearly", "full", "partial"}
FINAL_WEBHOOK_STATUSES = {"processed", "ignored", "rejected"}
REFUND_EVENTS = {"refund.processed", "refund.created"}
DISPUTE_EVENTS = {"payment.dispute.created", "payment.dispute.won", "payment.dispute.lost"}


class PaymentValidationError(ValueError):
    pass


class PaymentProviderUnavailable(RuntimeError):
    pass


def parse_amount(value) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PaymentValidationError("Invalid payment amount.") from exc
    if amount <= 0 or amount > Decimal("999999999.99"):
        raise PaymentValidationError("Payment amount is outside the allowed range.")
    return amount


def validate_school_fee_amount(value, outstanding) -> Decimal:
    amount = parse_amount(value)
    try:
        remaining_raw = Decimal(str(outstanding))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PaymentValidationError("Remaining fee amount is invalid.") from exc
    remaining = parse_amount(outstanding) if remaining_raw > 0 else Decimal("0.00")
    if amount > remaining:
        raise PaymentValidationError("Payment exceeds the remaining school fee due.")
    return amount


def validate_payment_options(mode, method):
    mode = str(mode or "").strip().lower()
    method = str(method or "").strip().lower()
    if mode not in ALLOWED_PAYMENT_MODES:
        raise PaymentValidationError("Unsupported payment mode.")
    if method not in ALLOWED_PAYMENT_METHODS:
        raise PaymentValidationError("Unsupported payment method.")
    return mode, method


def verify_razorpay_payment_signature(order_id, payment_id, signature, secret) -> bool:
    if not all(isinstance(value, str) and value for value in (order_id, payment_id, signature, secret)):
        return False
    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_razorpay_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    if not isinstance(raw_body, (bytes, bytearray)) or not isinstance(signature, str) or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), bytes(raw_body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def safe_event_id(payload, supplied=None):
    event_id = supplied or (payload.get("id") if isinstance(payload, dict) else None)
    if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,200}", event_id):
        raise PaymentValidationError("Webhook event identity is required.")
    return event_id


def redact_payment_payload(value):
    sensitive = re.compile(r"(?i)(secret|password|token|signature|api[_-]?key|authorization|card|bank|vpa)")
    if isinstance(value, dict):
        return {key: "[redacted]" if sensitive.search(str(key)) else redact_payment_payload(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payment_payload(item) for item in value]
    return value


def subscription_expiry(current_expiry, days: int, now=None):
    if not isinstance(days, int) or days <= 0 or days > 3660:
        raise PaymentValidationError("Invalid subscription duration.")
    now = now or datetime.utcnow()
    base = now
    if current_expiry:
        if isinstance(current_expiry, date) and not isinstance(current_expiry, datetime):
            current_expiry = datetime.combine(current_expiry, datetime.min.time())
        elif isinstance(current_expiry, str):
            current_expiry = datetime.strptime(current_expiry[:10], "%Y-%m-%d")
        if current_expiry > base:
            base = current_expiry
    return (base + timedelta(days=days)).date()


def provider_credentials_from_env(environment, key_id, key_secret, webhook_secret):
    if str(environment or "development").lower() == "production" and not all(
        isinstance(value, str) and value.strip() for value in (key_id, key_secret, webhook_secret)
    ):
        raise PaymentProviderUnavailable("Production Razorpay configuration is incomplete.")
    if not all(isinstance(value, str) and value.strip() for value in (key_id, key_secret, webhook_secret)):
        raise PaymentProviderUnavailable("Razorpay is not configured.")
    return {"key_id": key_id.strip(), "key_secret": key_secret, "webhook_secret": webhook_secret}


def json_event(raw_body: bytes):
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PaymentValidationError("Invalid webhook payload.") from exc
    if not isinstance(event, dict):
        raise PaymentValidationError("Invalid webhook payload.")
    return event


def provider_event_entity(event, event_type):
    payload = event.get("payload") or {}
    if event_type in REFUND_EVENTS:
        return (payload.get("refund") or {}).get("entity") or {}
    if event_type in DISPUTE_EVENTS:
        return (payload.get("dispute") or {}).get("entity") or {}
    return (payload.get("payment") or {}).get("entity") or {}
