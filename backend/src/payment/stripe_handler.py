import os

import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# MVP: in-memory mapping session_id → customer_id
# Phase 2: replace with Supabase/PostgreSQL
_valid_sessions: dict[str, str] = {}


def create_checkout_session(email: str) -> str:
    session = stripe.checkout.Session.create(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{"price": os.environ["STRIPE_PRICE_ID"], "quantity": 1}],
        mode="subscription",
        success_url=f"{os.environ['APP_URL']}?token={{CHECKOUT_SESSION_ID}}",
        cancel_url=os.environ["APP_URL"],
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> None:
    event = stripe.Webhook.construct_event(
        payload,
        sig_header,
        os.environ["STRIPE_WEBHOOK_SECRET"],
    )
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        _valid_sessions[session["id"]] = session["customer"]
    elif event["type"] == "customer.subscription.deleted":
        customer_id = event["data"]["object"]["customer"]
        # Remove all sessions for this customer
        to_remove = [sid for sid, cid in _valid_sessions.items() if cid == customer_id]
        for sid in to_remove:
            del _valid_sessions[sid]


def verify_access(token: str | None) -> bool:
    if not token:
        return False
    token = str(token).strip()
    if token not in _valid_sessions:
        return False
    customer_id = _valid_sessions[token]
    try:
        subs = stripe.Subscription.list(customer=customer_id, status="active", limit=1)
        return len(subs.data) > 0
    except stripe.StripeError:
        return False
