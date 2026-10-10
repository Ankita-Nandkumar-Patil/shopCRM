# Omnichannel Marketing Bot MVP

Runnable FastAPI backend for customer imports, campaigns, mock RCS/WhatsApp/SMS routing, delivery tracking and interaction webhooks.

**This is an MVP using mock providers. It sends no real messages.** WhatsApp must be explicitly selected as the campaign's primary channel and enabled for the merchant. It is never an automatic fallback. Customers are eligible only with explicit `marketing_consent=true` and no opt-out.

## Run on Ubuntu

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs. The database `shopcrm.db` is created automatically.

## 1. Create a merchant

POST `/api/v1/merchants`:

```json
{
  "name": "Demo Owner",
  "shop_name": "Demo Store",
  "phone_number": "+919876543210",
  "whatsapp_enabled": true,
  "default_channel": "rcs",
  "fallback_channel": "sms"
}
```

Copy the returned `api_key`; send it in `X-API-Key` on merchant endpoints.

## 2. Upload a CSV/Excel sheet

POST `/api/v1/merchant/upload-customers`, multipart fields `merchant_id` and `file`.

Recommended columns:

```csv
phone_number,name,tags,marketing_consent
9876543210,Asha,vip,true
9123456789,Ravi,regular,true
9988776655,Meera,festive,false
```

Indian numbers are normalized to +91. Invalid numbers are skipped. Without a consent column, consent defaults to false and those contacts are not sent marketing messages.

## 3. Create a campaign

POST `/api/v1/merchant/send-campaign` with `X-API-Key`:

```json
{
  "merchant_id": 1,
  "title": "Festive sale",
  "message_body": "Enjoy 20% off this weekend!",
  "media_url": "https://example.com/sale.jpg",
  "button_text": "Claim offer",
  "primary_channel": "rcs",
  "fallback_channel": "sms",
  "target_tag": "vip"
}
```

The endpoint returns 202 and starts FastAPI BackgroundTasks processing. Inspect `/api/v1/merchant/campaigns` and `/api/v1/merchant/campaigns/{campaign_id}/recipients`.

To use WhatsApp, explicitly set `primary_channel` to `whatsapp` and enable it when creating the merchant. `fallback_channel` cannot be WhatsApp.

## 4. Interaction webhook

POST `/webhook`:

```json
{
  "event_type": "button_click",
  "merchant_id": 1,
  "phone_number": "+919876543210",
  "campaign_id": 1,
  "postback_data": "CLAIM_OFFER_1"
}
```

The development webhook records the interaction and returns a demo promo code.

## Mock routing tests

- A valid Indian mobile ending in `0000` simulates RCS unsupported and exercises SMS fallback.
- A number ending in `9999` simulates provider failure.
- Other eligible numbers simulate successful sends.
- These are simulated results; no messages are actually sent.

## Before production

Add provider-specific integrations and signature verification, Alembic migrations, stronger auth/secret storage, durable queue workers, retry/idempotency logic, rate limits, audit logging and provider-specific compliance. FastAPI BackgroundTasks is not a durable job queue.
