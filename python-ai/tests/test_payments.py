from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from boardsight_ai.database import execute, fetchone
from boardsight_ai.payments import (
    create_checkout_order,
    create_recurring_subscription,
    init_payment_storage,
    process_subscription_webhook,
    verify_checkout_payment,
    verify_subscription_checkout,
)
from boardsight_ai.workspaces import init_workspace_storage


class _OrderApi:
    def __init__(self) -> None:
        self.payload = None

    def create(self, *, data):
        self.payload = data
        return {"id": "order_test_boardsight", **data}


class _PlanApi:
    def __init__(self) -> None:
        self.payload = None

    def create(self, *, data):
        self.payload = data
        return {"id": "plan_test_boardsight", **data}


class _SubscriptionApi:
    def __init__(self) -> None:
        self.payload = None

    def create(self, *, data):
        self.payload = data
        return {"id": "sub_test_boardsight", "status": "created", **data}


class _RazorpayClient:
    latest = None

    def __init__(self, *, auth) -> None:
        self.auth = auth
        self.order = _OrderApi()
        self.plan = _PlanApi()
        self.subscription = _SubscriptionApi()
        _RazorpayClient.latest = self


@pytest.fixture()
def payment_database(tmp_path, monkeypatch):
    database_path = tmp_path / "payments.db"
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_public")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook_secret")
    monkeypatch.setattr("boardsight_ai.payments.razorpay.Client", _RazorpayClient)
    init_workspace_storage(database_path)
    init_payment_storage(database_path)
    execute(
        database_path,
        "INSERT INTO organizations (name, slug, created_by_user_id) VALUES ('Test', 'test', 1)",
    )
    execute(
        database_path,
        "INSERT INTO subscriptions (organization_id, plan_code, status) VALUES (1, 'personal', 'active')",
    )
    return database_path


def test_create_order_uses_server_side_plan_price(payment_database):
    order = create_checkout_order(
        payment_database,
        organization_id=1,
        user_id=1,
        plan_code="starter",
        billing_cycle="monthly",
    )

    assert order["amount"] == 49_900
    assert order["currency"] == "INR"
    assert order["key_id"] == "rzp_test_public"
    assert _RazorpayClient.latest.order.payload["amount"] == 49_900
    stored = fetchone(payment_database, "SELECT * FROM payment_orders WHERE provider_order_id = 'order_test_boardsight'")
    assert stored["status"] == "created"
    assert stored["plan_code"] == "starter"


def test_verified_signature_activates_the_paid_plan(payment_database):
    order = create_checkout_order(
        payment_database,
        organization_id=1,
        user_id=1,
        plan_code="growth",
        billing_cycle="annual",
    )
    payment_id = "pay_test_boardsight"
    signature = hmac.new(
        b"test_secret",
        f"{order['order_id']}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    result = verify_checkout_payment(
        payment_database,
        organization_id=1,
        razorpay_order_id=order["order_id"],
        razorpay_payment_id=payment_id,
        razorpay_signature=signature,
    )

    assert result["status"] == "verified"
    subscription = fetchone(payment_database, "SELECT * FROM subscriptions WHERE organization_id = 1")
    assert subscription["plan_code"] == "growth"
    assert subscription["provider"] == "razorpay"


def test_invalid_signature_never_marks_order_paid(payment_database):
    order = create_checkout_order(
        payment_database,
        organization_id=1,
        user_id=1,
        plan_code="starter",
        billing_cycle="monthly",
    )

    with pytest.raises(ValueError, match="signature"):
        verify_checkout_payment(
            payment_database,
            organization_id=1,
            razorpay_order_id=order["order_id"],
            razorpay_payment_id="pay_tampered",
            razorpay_signature="not-valid",
        )

    stored = fetchone(payment_database, "SELECT * FROM payment_orders WHERE provider_order_id = :order_id", {"order_id": order["order_id"]})
    assert stored["status"] == "created"
    assert stored["provider_payment_id"] is None


def test_create_and_verify_recurring_subscription(payment_database):
    subscription = create_recurring_subscription(
        payment_database,
        organization_id=1,
        user_id=1,
        plan_code="starter",
        billing_cycle="monthly",
    )

    assert subscription["subscription_id"] == "sub_test_boardsight"
    assert subscription["amount"] == 49_900
    assert _RazorpayClient.latest.plan.payload["period"] == "monthly"
    assert _RazorpayClient.latest.plan.payload["item"]["amount"] == 49_900
    assert _RazorpayClient.latest.subscription.payload["total_count"] == 120

    payment_id = "pay_subscription_auth"
    signature = hmac.new(
        b"test_secret",
        f"{payment_id}|{subscription['subscription_id']}".encode(),
        hashlib.sha256,
    ).hexdigest()
    verified = verify_subscription_checkout(
        payment_database,
        organization_id=1,
        razorpay_subscription_id=subscription["subscription_id"],
        razorpay_payment_id=payment_id,
        razorpay_signature=signature,
    )

    assert verified["status"] == "authenticated"
    workspace_subscription = fetchone(payment_database, "SELECT * FROM subscriptions WHERE organization_id = 1")
    assert workspace_subscription["status"] == "active"
    assert workspace_subscription["provider_subscription_id"] == "sub_test_boardsight"


def test_signed_webhook_updates_subscription_and_deduplicates(payment_database):
    create_recurring_subscription(
        payment_database,
        organization_id=1,
        user_id=1,
        plan_code="growth",
        billing_cycle="annual",
    )
    payload = {
        "event": "subscription.charged",
        "created_at": 1_800_000_000,
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_test_boardsight",
                    "status": "active",
                    "current_start": 1_800_000_000,
                    "current_end": 1_831_536_000,
                }
            },
            "payment": {"entity": {"id": "pay_renewal"}},
        },
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook_secret", raw_body, hashlib.sha256).hexdigest()

    first = process_subscription_webhook(
        payment_database,
        raw_body=raw_body,
        signature=signature,
        event_id="event_unique_1",
    )
    duplicate = process_subscription_webhook(
        payment_database,
        raw_body=raw_body,
        signature=signature,
        event_id="event_unique_1",
    )

    assert first["status"] == "processed"
    assert duplicate["status"] == "duplicate"
    local = fetchone(payment_database, "SELECT * FROM razorpay_subscriptions WHERE provider_subscription_id = 'sub_test_boardsight'")
    assert local["status"] == "active"
    assert local["provider_payment_id"] == "pay_renewal"


def test_webhook_rejects_invalid_signature(payment_database):
    with pytest.raises(ValueError, match="signature"):
        process_subscription_webhook(
            payment_database,
            raw_body=b'{"event":"subscription.charged"}',
            signature="tampered",
            event_id="event_invalid",
        )
