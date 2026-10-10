import secrets
from contextlib import asynccontextmanager
from io import BytesIO
import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models
from app.database import Base, engine, get_db
from app.models import Campaign, CampaignRecipient, Customer, Interaction, Merchant
from app.schemas import CampaignCreate, CampaignOut, MerchantCreate, MerchantOut, WebhookEvent
from app.services.campaigns import process_campaign
from app.services.phone import normalize_indian_phone, parse_bool

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Omnichannel Marketing Bot", version="0.1.0",
              description="Runnable MVP using mock providers only.", lifespan=lifespan)

def get_merchant(x_api_key: str = Header(..., alias="X-API-Key"),
                 db: Session = Depends(get_db)) -> Merchant:
    merchant = db.scalar(select(Merchant).where(Merchant.api_key == x_api_key))
    if merchant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return merchant

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/v1/merchants", response_model=MerchantOut, status_code=201)
def create_merchant(payload: MerchantCreate, db: Session = Depends(get_db)):
    if payload.default_channel.value == "whatsapp" and not payload.whatsapp_enabled:
        raise HTTPException(status_code=422, detail="Enable WhatsApp before setting it as default")
    merchant = Merchant(name=payload.name, shop_name=payload.shop_name,
        phone_number=payload.phone_number, api_key=secrets.token_urlsafe(32),
        whatsapp_enabled=payload.whatsapp_enabled,
        default_channel=payload.default_channel.value,
        fallback_channel=payload.fallback_channel.value if payload.fallback_channel else None)
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant

@app.get("/api/v1/merchants/me")
def merchant_me(merchant: Merchant = Depends(get_merchant)):
    return {"id": merchant.id, "name": merchant.name, "shop_name": merchant.shop_name,
            "whatsapp_enabled": merchant.whatsapp_enabled, "default_channel": merchant.default_channel,
            "fallback_channel": merchant.fallback_channel}

@app.post("/api/v1/merchant/upload-customers")
async def upload_customers(merchant_id: int = Form(...), file: UploadFile = File(...),
                           merchant: Merchant = Depends(get_merchant), db: Session = Depends(get_db)):
    if merchant.id != merchant_id:
        raise HTTPException(status_code=403, detail="API key does not belong to this merchant")
    filename = (file.filename or "").lower()
    raw = await file.read()
    try:
        if filename.endswith(".csv"):
            frame = pd.read_csv(BytesIO(raw), dtype=str).fillna("")
        elif filename.endswith((".xlsx", ".xls")):
            frame = pd.read_excel(BytesIO(raw), dtype=str).fillna("")
        else:
            raise HTTPException(status_code=400, detail="Upload .csv, .xlsx, or .xls")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read spreadsheet: {exc}") from exc
    if frame.empty:
        raise HTTPException(status_code=400, detail="The uploaded sheet has no data rows")
    columns = {str(c).strip().lower(): c for c in frame.columns}
    phone_col = next((columns[k] for k in ("phone_number", "phone", "mobile", "mobile_number", "phone number") if k in columns), None)
    if phone_col is None:
        raise HTTPException(status_code=422, detail="Sheet needs a phone_number, phone, mobile, or mobile_number column")
    name_col = next((columns[k] for k in ("name", "customer_name", "customer name") if k in columns), None)
    tags_col = next((columns[k] for k in ("tags", "tag", "segment") if k in columns), None)
    consent_col = next((columns[k] for k in ("marketing_consent", "consent", "opt_in") if k in columns), None)
    created = updated = skipped = 0
    errors = []
    for idx, row in frame.iterrows():
        try:
            phone = normalize_indian_phone(row[phone_col])
        except ValueError as exc:
            skipped += 1
            if len(errors) < 20:
                errors.append({"row": int(idx) + 2, "error": str(exc)})
            continue
        customer = db.scalar(select(Customer).where(Customer.merchant_id == merchant.id, Customer.phone_number == phone))
        name = str(row[name_col]).strip() if name_col and str(row[name_col]).strip() else None
        tags = str(row[tags_col]).strip() if tags_col and str(row[tags_col]).strip() else None
        consent = parse_bool(row[consent_col]) if consent_col else False
        if customer:
            customer.name = name or customer.name
            customer.tags = tags if tags is not None else customer.tags
            if consent_col:
                customer.marketing_consent = consent
            updated += 1
        else:
            db.add(Customer(merchant_id=merchant.id, phone_number=phone, name=name, tags=tags,
                            marketing_consent=consent, is_opted_out=False))
            created += 1
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database import failed: {exc}") from exc
    return {"merchant_id": merchant.id, "created": created, "updated": updated, "skipped": skipped,
            "row_errors": errors, "note": "Only explicit marketing_consent=true customers are eligible."}

@app.get("/api/v1/merchant/customers")
def list_customers(merchant: Merchant = Depends(get_merchant), db: Session = Depends(get_db), limit: int = 100):
    limit = max(1, min(limit, 500))
    rows = db.scalars(select(Customer).where(Customer.merchant_id == merchant.id).order_by(Customer.id).limit(limit)).all()
    return [{"id": c.id, "phone_number": c.phone_number, "name": c.name, "tags": c.tags,
             "marketing_consent": c.marketing_consent, "is_opted_out": c.is_opted_out} for c in rows]

@app.post("/api/v1/merchant/send-campaign", response_model=CampaignOut, status_code=202)
def send_campaign(payload: CampaignCreate, background_tasks: BackgroundTasks,
                  merchant: Merchant = Depends(get_merchant), db: Session = Depends(get_db)):
    if payload.merchant_id != merchant.id:
        raise HTTPException(status_code=403, detail="API key does not belong to this merchant")
    primary = payload.primary_channel.value if payload.primary_channel else merchant.default_channel
    fallback = payload.fallback_channel.value if payload.fallback_channel else merchant.fallback_channel
    if primary == "whatsapp" and not merchant.whatsapp_enabled:
        raise HTTPException(status_code=422, detail="WhatsApp is not enabled for this merchant")
    if fallback == "whatsapp":
        raise HTTPException(status_code=422, detail="WhatsApp cannot be an automatic fallback")
    campaign = Campaign(merchant_id=merchant.id, title=payload.title, message_body=payload.message_body,
        media_url=str(payload.media_url) if payload.media_url else None, button_text=payload.button_text,
        primary_channel=primary, fallback_channel=fallback, target_tag=payload.target_tag, status="pending")
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    background_tasks.add_task(process_campaign, campaign.id)
    return campaign

@app.get("/api/v1/merchant/campaigns")
def list_campaigns(merchant: Merchant = Depends(get_merchant), db: Session = Depends(get_db)):
    rows = db.scalars(select(Campaign).where(Campaign.merchant_id == merchant.id).order_by(Campaign.id.desc())).all()
    return [{"id": c.id, "title": c.title, "status": c.status, "primary_channel": c.primary_channel,
             "fallback_channel": c.fallback_channel, "target_tag": c.target_tag, "created_at": c.created_at} for c in rows]

@app.get("/api/v1/merchant/campaigns/{campaign_id}/recipients")
def campaign_recipients(campaign_id: int, merchant: Merchant = Depends(get_merchant), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    rows = db.scalars(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)).all()
    return [{"customer_id": r.customer_id, "phone_number": r.customer.phone_number, "status": r.status,
             "channel_used": r.channel_used, "provider_message_id": r.provider_message_id,
             "fallback_used": r.fallback_used, "error_detail": r.error_detail} for r in rows]

@app.post("/webhook")
def webhook_event(event: WebhookEvent, db: Session = Depends(get_db)):
    # Development endpoint only. Verify provider signatures before accepting real events.
    merchant = db.get(Merchant, event.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    customer = None
    if event.phone_number:
        try:
            phone = normalize_indian_phone(event.phone_number)
        except ValueError:
            phone = event.phone_number
        customer = db.scalar(select(Customer).where(Customer.merchant_id == merchant.id, Customer.phone_number == phone))
    if event.event_type in {"sent", "delivered", "read", "failed"} and event.campaign_id:
        campaign = db.get(Campaign, event.campaign_id)
        if campaign is None or campaign.merchant_id != merchant.id:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if customer:
            recipient = db.scalar(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id,
                                                                   CampaignRecipient.customer_id == customer.id))
            if recipient:
                recipient.status = event.event_type
                if event.provider_message_id:
                    recipient.provider_message_id = event.provider_message_id
    promo_code = None
    if event.event_type in {"button_click", "postback"}:
        promo_code = f"SHOP{merchant.id}-C{event.campaign_id or 0}-OFFER"
    db.add(Interaction(merchant_id=merchant.id, customer_id=customer.id if customer else None,
        campaign_id=event.campaign_id, event_type=event.event_type, postback_data=event.postback_data, promo_code=promo_code))
    db.commit()
    return {"accepted": True, "event_type": event.event_type, "promo_code": promo_code,
            "reply": f"Your offer code is {promo_code}" if promo_code else None,
            "note": "Development webhook only; verify real provider signatures before production."}
