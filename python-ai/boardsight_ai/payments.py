from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import razorpay
from sqlalchemy import text

from boardsight_ai.database import fetchone, get_engine, is_postgres
from boardsight_ai.workspaces import PLAN_PRICING


class PaymentConfigurationError(RuntimeError):
    pass


class PaymentGatewayError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _credentials() -> tuple[str, str]:
    key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    if not key_id or not key_secret:
        raise PaymentConfigurationError("Razorpay is not configured on the server.")
    return key_id, key_secret


def _webhook_secret() -> str:
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise PaymentConfigurationError("Razorpay webhook verification is not configured.")
    return secret


def init_payment_storage(database_path: Path) -> None:
    postgres = is_postgres(database_path)
    id_type = "BIGSERIAL PRIMARY KEY" if postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    integer_type = "BIGINT" if postgres else "INTEGER"
    timestamp_type = "TIMESTAMP" if postgres else "TEXT"
    engine = get_engine(database_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS payment_orders (
                    id {id_type},
                    organization_id {integer_type} NOT NULL,
                    requested_by_user_id {integer_type} NOT NULL,
                    plan_code TEXT NOT NULL,
                    billing_cycle TEXT NOT NULL,
                    amount_paise INTEGER NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    receipt TEXT NOT NULL UNIQUE,
                    provider_order_id TEXT NOT NULL UNIQUE,
                    provider_payment_id TEXT UNIQUE,
                    status TEXT NOT NULL DEFAULT 'created',
                    verified_at {timestamp_type},
                    created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_payment_orders_org ON payment_orders(organization_id, created_at)"))
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS razorpay_plans (
                    id {id_type},
                    plan_code TEXT NOT NULL,
                    billing_cycle TEXT NOT NULL,
                    amount_paise INTEGER NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    provider_plan_id TEXT NOT NULL UNIQUE,
                    created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (plan_code, billing_cycle)
                )
                """
            )
        )
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS razorpay_subscriptions (
                    id {id_type},
                    organization_id {integer_type} NOT NULL,
                    requested_by_user_id {integer_type} NOT NULL,
                    plan_code TEXT NOT NULL,
                    billing_cycle TEXT NOT NULL,
                    provider_plan_id TEXT NOT NULL,
                    provider_subscription_id TEXT NOT NULL UNIQUE,
                    provider_payment_id TEXT,
                    status TEXT NOT NULL DEFAULT 'created',
                    current_period_start {timestamp_type},
                    current_period_end {timestamp_type},
                    last_event_created_at {integer_type},
                    authenticated_at {timestamp_type},
                    created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_razorpay_subscriptions_org ON razorpay_subscriptions(organization_id, created_at)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_razorpay_subscription_payment ON razorpay_subscriptions(provider_payment_id)"))
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS razorpay_webhook_events (
                    id {id_type},
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    provider_subscription_id TEXT,
                    status TEXT NOT NULL DEFAULT 'processed',
                    created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def _plan_amount_paise(plan_code: str, billing_cycle: str) -> int:
    plan = PLAN_PRICING.get(plan_code)
    if plan is None or plan_code == "custom":
        raise ValueError("This plan cannot be purchased through self-service checkout.")
    if billing_cycle not in {"monthly", "annual"}:
        raise ValueError("Billing cycle must be monthly or annual.")
    price_key = "annual_price_inr" if billing_cycle == "annual" else "monthly_price_inr"
    price_inr = plan.get(price_key)
    if price_inr is None:
        raise ValueError("This plan does not have a checkout price.")
    amount_paise = int(round(float(price_inr) * 100))
    if amount_paise < 100:
        raise ValueError("Payment amount must be at least 100 paise.")
    return amount_paise


def _gateway_error(exc: Exception, default_message: str) -> PaymentGatewayError:
    status_code = int(getattr(exc, "status_code", 502) or 502)
    if status_code in {401, 403}:
        return PaymentGatewayError("Razorpay authentication failed.", 401)
    if status_code == 400:
        return PaymentGatewayError(default_message, 400)
    return PaymentGatewayError("Razorpay is temporarily unavailable. Please try again.", 502)


def _get_or_create_provider_plan(
    database_path: Path,
    client: razorpay.Client,
    *,
    plan_code: str,
    billing_cycle: str,
) -> tuple[str, int]:
    amount_paise = _plan_amount_paise(plan_code, billing_cycle)
    existing = fetchone(
        database_path,
        "SELECT * FROM razorpay_plans WHERE plan_code = :plan_code AND billing_cycle = :billing_cycle",
        {"plan_code": plan_code, "billing_cycle": billing_cycle},
    )
    if existing is not None:
        if int(existing["amount_paise"]) != amount_paise:
            raise PaymentConfigurationError(
                "The local Razorpay plan price is stale. Create a new provider plan mapping before checkout."
            )
        return str(existing["provider_plan_id"]), amount_paise

    plan_name = str(PLAN_PRICING[plan_code]["name"])
    try:
        provider_plan = client.plan.create(
            data={
                "period": "yearly" if billing_cycle == "annual" else "monthly",
                "interval": 1,
                "item": {
                    "name": f"BoardSight {plan_name} ({billing_cycle})",
                    "amount": amount_paise,
                    "currency": "INR",
                    "description": f"BoardSight {plan_name} recurring subscription",
                },
                "notes": {"plan_code": plan_code, "billing_cycle": billing_cycle},
            }
        )
    except (razorpay.errors.BadRequestError, razorpay.errors.GatewayError, razorpay.errors.ServerError) as exc:
        raise _gateway_error(exc, "Razorpay rejected the subscription plan.") from exc
    provider_plan_id = str(provider_plan.get("id") or "")
    if not provider_plan_id:
        raise PaymentGatewayError("Razorpay returned an invalid plan response.")
    engine = get_engine(database_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO razorpay_plans (
                    plan_code, billing_cycle, amount_paise, currency, provider_plan_id
                ) VALUES (
                    :plan_code, :billing_cycle, :amount_paise, 'INR', :provider_plan_id
                )
                """
            ),
            {
                "plan_code": plan_code,
                "billing_cycle": billing_cycle,
                "amount_paise": amount_paise,
                "provider_plan_id": provider_plan_id,
            },
        )
    return provider_plan_id, amount_paise


def create_recurring_subscription(
    database_path: Path,
    *,
    organization_id: int,
    user_id: int,
    plan_code: str,
    billing_cycle: str,
) -> dict[str, Any]:
    init_payment_storage(database_path)
    key_id, key_secret = _credentials()
    normalized_plan = plan_code.strip().lower()
    normalized_cycle = billing_cycle.strip().lower()
    client = razorpay.Client(auth=(key_id, key_secret))
    provider_plan_id, amount_paise = _get_or_create_provider_plan(
        database_path,
        client,
        plan_code=normalized_plan,
        billing_cycle=normalized_cycle,
    )
    existing_subscription = fetchone(
        database_path,
        """
        SELECT * FROM razorpay_subscriptions
        WHERE organization_id = :organization_id
          AND status IN ('created', 'authenticated', 'active', 'pending', 'halted', 'paused')
        ORDER BY id DESC LIMIT 1
        """,
        {"organization_id": organization_id},
    )
    if existing_subscription is not None:
        if (
            existing_subscription["status"] == "created"
            and existing_subscription["plan_code"] == normalized_plan
            and existing_subscription["billing_cycle"] == normalized_cycle
        ):
            return {
                "subscription_id": str(existing_subscription["provider_subscription_id"]),
                "amount": amount_paise,
                "currency": "INR",
                "key_id": key_id,
                "plan_code": normalized_plan,
                "billing_cycle": normalized_cycle,
            }
        raise ValueError("This workspace already has a Razorpay subscription. Cancel it before starting a different plan.")
    try:
        provider_subscription = client.subscription.create(
            data={
                "plan_id": provider_plan_id,
                "total_count": 10 if normalized_cycle == "annual" else 120,
                "quantity": 1,
                "customer_notify": True,
                "notes": {
                    "organization_id": str(organization_id),
                    "plan_code": normalized_plan,
                    "billing_cycle": normalized_cycle,
                },
            }
        )
    except (razorpay.errors.BadRequestError, razorpay.errors.GatewayError, razorpay.errors.ServerError) as exc:
        raise _gateway_error(exc, "Razorpay rejected the subscription request.") from exc
    provider_subscription_id = str(provider_subscription.get("id") or "")
    if not provider_subscription_id:
        raise PaymentGatewayError("Razorpay returned an invalid subscription response.")
    engine = get_engine(database_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO razorpay_subscriptions (
                    organization_id, requested_by_user_id, plan_code, billing_cycle,
                    provider_plan_id, provider_subscription_id, status
                ) VALUES (
                    :organization_id, :requested_by_user_id, :plan_code, :billing_cycle,
                    :provider_plan_id, :provider_subscription_id, :status
                )
                """
            ),
            {
                "organization_id": organization_id,
                "requested_by_user_id": user_id,
                "plan_code": normalized_plan,
                "billing_cycle": normalized_cycle,
                "provider_plan_id": provider_plan_id,
                "provider_subscription_id": provider_subscription_id,
                "status": str(provider_subscription.get("status") or "created"),
            },
        )
    return {
        "subscription_id": provider_subscription_id,
        "amount": amount_paise,
        "currency": "INR",
        "key_id": key_id,
        "plan_code": normalized_plan,
        "billing_cycle": normalized_cycle,
    }


def verify_subscription_checkout(
    database_path: Path,
    *,
    organization_id: int,
    razorpay_subscription_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> dict[str, Any]:
    init_payment_storage(database_path)
    _, key_secret = _credentials()
    subscription = fetchone(
        database_path,
        """
        SELECT * FROM razorpay_subscriptions
        WHERE provider_subscription_id = :subscription_id AND organization_id = :organization_id
        """,
        {"subscription_id": razorpay_subscription_id, "organization_id": organization_id},
    )
    if subscription is None:
        raise ValueError("Razorpay subscription was not found for this workspace.")
    signed_payload = f"{razorpay_payment_id}|{subscription['provider_subscription_id']}".encode("utf-8")
    expected_signature = hmac.new(key_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, razorpay_signature):
        raise ValueError("Subscription signature verification failed.")

    now = datetime.now(UTC)
    engine = get_engine(database_path)
    with engine.begin() as connection:
        existing_payment = connection.execute(
            text(
                """
                SELECT provider_subscription_id FROM razorpay_subscriptions
                WHERE provider_payment_id = :payment_id AND provider_subscription_id <> :subscription_id
                """
            ),
            {"payment_id": razorpay_payment_id, "subscription_id": razorpay_subscription_id},
        ).mappings().first()
        if existing_payment is not None:
            raise ValueError("This Razorpay payment has already been applied.")
        connection.execute(
            text(
                """
                UPDATE razorpay_subscriptions
                SET provider_payment_id = :payment_id, status = 'authenticated',
                    authenticated_at = :authenticated_at, updated_at = CURRENT_TIMESTAMP
                WHERE provider_subscription_id = :subscription_id
                """
            ),
            {
                "payment_id": razorpay_payment_id,
                "authenticated_at": _timestamp(now),
                "subscription_id": razorpay_subscription_id,
            },
        )
        connection.execute(
            text(
                """
                UPDATE subscriptions
                SET plan_code = :plan_code, status = 'active', provider = 'razorpay',
                    provider_subscription_id = :subscription_id, billing_mode = 'customer', sponsorship_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE organization_id = :organization_id
                """
            ),
            {
                "plan_code": subscription["plan_code"],
                "subscription_id": razorpay_subscription_id,
                "organization_id": organization_id,
            },
        )
    return fetchone(
        database_path,
        "SELECT * FROM razorpay_subscriptions WHERE provider_subscription_id = :subscription_id",
        {"subscription_id": razorpay_subscription_id},
    ) or {}


def _webhook_status(event_type: str) -> str | None:
    if event_type in {"subscription.authenticated", "subscription.activated", "subscription.charged", "subscription.resumed"}:
        return "active"
    if event_type in {"subscription.pending", "subscription.halted", "subscription.paused"}:
        return "past_due"
    if event_type in {"subscription.cancelled", "subscription.completed", "subscription.expired"}:
        return "canceled"
    return None


def process_subscription_webhook(
    database_path: Path,
    *,
    raw_body: bytes,
    signature: str,
    event_id: str,
) -> dict[str, Any]:
    init_payment_storage(database_path)
    if not signature or not event_id:
        raise ValueError("Missing Razorpay webhook headers.")
    if len(raw_body) > 1_000_000:
        raise ValueError("Webhook payload is too large.")
    expected_signature = hmac.new(_webhook_secret().encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise ValueError("Webhook signature verification failed.")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Webhook payload is not valid JSON.") from exc
    event_type = str(payload.get("event") or "")
    subscription_entity = (((payload.get("payload") or {}).get("subscription") or {}).get("entity") or {})
    provider_subscription_id = str(subscription_entity.get("id") or "")
    event_created_at = int(payload.get("created_at") or 0)
    engine = get_engine(database_path)
    with engine.begin() as connection:
        inserted = connection.execute(
            text(
                """
                INSERT INTO razorpay_webhook_events (
                    event_id, event_type, provider_subscription_id, status
                ) VALUES (
                    :event_id, :event_type, :provider_subscription_id, 'processing'
                ) ON CONFLICT (event_id) DO NOTHING
                """
            ),
            {
                "event_id": event_id,
                "event_type": event_type,
                "provider_subscription_id": provider_subscription_id or None,
            },
        )
        if inserted.rowcount == 0:
            return {"status": "duplicate", "event": event_type}
        local_subscription = None
        if provider_subscription_id:
            local_subscription = connection.execute(
                text("SELECT * FROM razorpay_subscriptions WHERE provider_subscription_id = :subscription_id"),
                {"subscription_id": provider_subscription_id},
            ).mappings().first()
        processing_status = "ignored"
        next_status = _webhook_status(event_type)
        if local_subscription is not None and next_status is not None:
            last_event_created_at = int(local_subscription.get("last_event_created_at") or 0)
            if event_created_at >= last_event_created_at:
                current_start = subscription_entity.get("current_start")
                current_end = subscription_entity.get("current_end")
                period_start = _timestamp(datetime.fromtimestamp(int(current_start), UTC)) if current_start else None
                period_end = _timestamp(datetime.fromtimestamp(int(current_end), UTC)) if current_end else None
                payment_entity = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
                payment_id = str(payment_entity.get("id") or "") or None
                connection.execute(
                    text(
                        """
                        UPDATE razorpay_subscriptions
                        SET status = :provider_status, provider_payment_id = COALESCE(:payment_id, provider_payment_id),
                            current_period_start = COALESCE(:period_start, current_period_start),
                            current_period_end = COALESCE(:period_end, current_period_end),
                            last_event_created_at = :event_created_at, updated_at = CURRENT_TIMESTAMP
                        WHERE provider_subscription_id = :subscription_id
                        """
                    ),
                    {
                        "provider_status": str(subscription_entity.get("status") or next_status),
                        "payment_id": payment_id,
                        "period_start": period_start,
                        "period_end": period_end,
                        "event_created_at": event_created_at,
                        "subscription_id": provider_subscription_id,
                    },
                )
                connection.execute(
                    text(
                        """
                        UPDATE subscriptions
                        SET plan_code = :plan_code, status = :status, provider = 'razorpay',
                            provider_subscription_id = :subscription_id,
                            current_period_start = COALESCE(:period_start, current_period_start),
                            current_period_end = COALESCE(:period_end, current_period_end),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE organization_id = :organization_id
                        """
                    ),
                    {
                        "plan_code": local_subscription["plan_code"],
                        "status": next_status,
                        "subscription_id": provider_subscription_id,
                        "period_start": period_start,
                        "period_end": period_end,
                        "organization_id": local_subscription["organization_id"],
                    },
                )
                processing_status = "processed"
            else:
                processing_status = "stale"
        connection.execute(
            text("UPDATE razorpay_webhook_events SET status = :status WHERE event_id = :event_id"),
            {"status": processing_status, "event_id": event_id},
        )
    return {"status": processing_status, "event": event_type}


def create_checkout_order(
    database_path: Path,
    *,
    organization_id: int,
    user_id: int,
    plan_code: str,
    billing_cycle: str,
) -> dict[str, Any]:
    init_payment_storage(database_path)
    key_id, key_secret = _credentials()
    normalized_plan = plan_code.strip().lower()
    normalized_cycle = billing_cycle.strip().lower()
    amount_paise = _plan_amount_paise(normalized_plan, normalized_cycle)
    receipt = f"bs-{organization_id}-{secrets.token_hex(10)}"[:40]
    client = razorpay.Client(auth=(key_id, key_secret))
    try:
        order = client.order.create(
            data={
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": {
                    "organization_id": str(organization_id),
                    "plan_code": normalized_plan,
                    "billing_cycle": normalized_cycle,
                },
            }
        )
    except razorpay.errors.BadRequestError as exc:
        status_code = int(getattr(exc, "status_code", 400) or 400)
        if status_code in {401, 403}:
            raise PaymentGatewayError("Razorpay authentication failed.", 401) from exc
        raise PaymentGatewayError("Razorpay rejected the order request.", 400) from exc
    except razorpay.errors.ServerError as exc:
        raise PaymentGatewayError("Razorpay is temporarily unavailable. Please try again.", 502) from exc
    except razorpay.errors.GatewayError as exc:
        status_code = int(getattr(exc, "status_code", 502) or 502)
        if status_code in {401, 403}:
            raise PaymentGatewayError("Razorpay authentication failed.", 401) from exc
        raise PaymentGatewayError("Razorpay could not create the order.", 502) from exc

    provider_order_id = str(order.get("id") or "")
    if not provider_order_id:
        raise PaymentGatewayError("Razorpay returned an invalid order response.")
    engine = get_engine(database_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO payment_orders (
                    organization_id, requested_by_user_id, plan_code, billing_cycle,
                    amount_paise, currency, receipt, provider_order_id
                ) VALUES (
                    :organization_id, :requested_by_user_id, :plan_code, :billing_cycle,
                    :amount_paise, 'INR', :receipt, :provider_order_id
                )
                """
            ),
            {
                "organization_id": organization_id,
                "requested_by_user_id": user_id,
                "plan_code": normalized_plan,
                "billing_cycle": normalized_cycle,
                "amount_paise": amount_paise,
                "receipt": receipt,
                "provider_order_id": provider_order_id,
            },
        )
    return {
        "order_id": provider_order_id,
        "amount": amount_paise,
        "currency": "INR",
        "key_id": key_id,
        "plan_code": normalized_plan,
        "billing_cycle": normalized_cycle,
    }


def verify_checkout_payment(
    database_path: Path,
    *,
    organization_id: int,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> dict[str, Any]:
    init_payment_storage(database_path)
    _, key_secret = _credentials()
    order = fetchone(
        database_path,
        "SELECT * FROM payment_orders WHERE provider_order_id = :provider_order_id AND organization_id = :organization_id",
        {"provider_order_id": razorpay_order_id, "organization_id": organization_id},
    )
    if order is None:
        raise ValueError("Payment order was not found for this workspace.")
    if order.get("status") == "verified":
        if order.get("provider_payment_id") != razorpay_payment_id:
            raise ValueError("This order has already been paid with a different payment.")
        return order

    signed_payload = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
    expected_signature = hmac.new(key_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, razorpay_signature):
        raise ValueError("Payment signature verification failed.")

    now = datetime.now(UTC)
    period_end = now + timedelta(days=365 if order["billing_cycle"] == "annual" else 30)
    engine = get_engine(database_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE payment_orders
                    SET provider_payment_id = :provider_payment_id, status = 'verified',
                        verified_at = :verified_at, updated_at = CURRENT_TIMESTAMP
                    WHERE provider_order_id = :provider_order_id AND status = 'created'
                    """
                ),
                {
                    "provider_payment_id": razorpay_payment_id,
                    "verified_at": _timestamp(now),
                    "provider_order_id": razorpay_order_id,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE subscriptions
                    SET plan_code = :plan_code, status = 'active', provider = 'razorpay',
                        provider_subscription_id = NULL, billing_mode = 'customer', sponsorship_id = NULL,
                        current_period_start = :period_start, current_period_end = :period_end,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE organization_id = :organization_id
                    """
                ),
                {
                    "plan_code": order["plan_code"],
                    "period_start": _timestamp(now),
                    "period_end": _timestamp(period_end),
                    "organization_id": organization_id,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE subscription_change_requests
                    SET status = 'completed', resolved_at = CURRENT_TIMESTAMP
                    WHERE organization_id = :organization_id AND requested_plan_code = :plan_code
                      AND billing_cycle = :billing_cycle AND status = 'pending'
                    """
                ),
                {
                    "organization_id": organization_id,
                    "plan_code": order["plan_code"],
                    "billing_cycle": order["billing_cycle"],
                },
            )
    except Exception as exc:
        if "provider_payment_id" in str(exc).lower() or "unique" in str(exc).lower():
            raise ValueError("This Razorpay payment has already been applied.") from exc
        raise
    return fetchone(
        database_path,
        "SELECT * FROM payment_orders WHERE provider_order_id = :provider_order_id",
        {"provider_order_id": razorpay_order_id},
    ) or {}
