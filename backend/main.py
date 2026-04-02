import os
from contextlib import asynccontextmanager

import stripe
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

load_dotenv()

from src.audit.profiler import profile_dataframe
from src.audit.scorer import compute_score
from src.payment.stripe_handler import create_checkout_session, handle_webhook, verify_access
from src.utils.file_handler import parse_csv, validate_file


@asynccontextmanager
async def lifespan(app: FastAPI):
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    yield


app = FastAPI(title="DataLens API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://datalens.badreddineek.com",
        "https://app.datalens.badreddineek.com",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:5500",  # Live Server dev
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    from datetime import datetime, timezone
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/audit")
async def audit_csv(
    file: UploadFile = File(...),
    token: str = Form(default=None),
):
    # Validate MIME type
    if file.content_type and file.content_type not in {
        "text/csv", "application/csv", "text/plain", "application/octet-stream"
    }:
        raise HTTPException(status_code=400, detail="Format invalide. Seuls les fichiers CSV sont acceptés.")

    content = await file.read()

    validate_file(file.filename or "upload.csv", content)

    df, encoding = parse_csv(content)

    is_limited = len(df) > 1000 and not verify_access(token)
    if is_limited:
        raise HTTPException(status_code=402, detail="PAYMENT_REQUIRED")

    profile = profile_dataframe(df)
    score, score_label = compute_score(profile)

    profile["score"] = score
    profile["score_label"] = score_label
    profile["file_info"]["filename"] = file.filename or "upload.csv"
    profile["file_info"]["size_kb"] = round(len(content) / 1024, 1)
    profile["file_info"]["encoding"] = encoding
    profile["file_info"]["is_limited"] = False

    return profile


class CheckoutRequest(BaseModel):
    email: EmailStr


@app.post("/api/create-checkout")
def create_checkout(body: CheckoutRequest):
    try:
        url = create_checkout_session(str(body.email))
        return {"checkout_url": url}
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail="Erreur lors de la création du paiement.") from exc


@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        handle_webhook(payload, sig_header)
    except stripe.errors.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Signature Stripe invalide.") from exc
    return {"received": True}


@app.get("/api/verify-access")
def verify(token: str = ""):
    return {"has_access": verify_access(token or None)}
