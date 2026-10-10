import asyncio
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Campaign, CampaignRecipient, Customer, utc_now
from app.services.providers import get_provider

def recipient_matches_tag(customer: Customer, target_tag: str | None) -> bool:
    if not target_tag:
        return True
    tags = {t.strip().lower() for t in (customer.tags or "").split(",") if t.strip()}
    return target_tag.strip().lower() in tags

async def process_campaign(campaign_id: int) -> None:
    # A background task must own its own DB session.
    db: Session = SessionLocal()
    try:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            return
        campaign.status = "processing"
        db.commit()

        customers = db.scalars(select(Customer).where(Customer.merchant_id == campaign.merchant_id)).all()
        eligible = [c for c in customers if c.marketing_consent and not c.is_opted_out
                    and recipient_matches_tag(c, campaign.target_tag)]

        for customer in eligible:
            existing = db.scalar(select(CampaignRecipient).where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.customer_id == customer.id))
            if existing is None:
                db.add(CampaignRecipient(campaign_id=campaign.id, customer_id=customer.id, status="pending"))
        db.commit()

        # Campaign channel is the explicit merchant choice. Customer data never silently
        # switches a campaign to WhatsApp.
        channel = campaign.primary_channel
        merchant = campaign.merchant
        if channel == "whatsapp" and not merchant.whatsapp_enabled:
            campaign.status = "failed"
            db.commit()
            return

        for customer in eligible:
            recipient = db.scalar(select(CampaignRecipient).where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.customer_id == customer.id))
            if recipient is None or recipient.status in {"sent", "delivered", "read"}:
                continue
            result = await get_provider(channel).send(
                phone_number=customer.phone_number, body=campaign.message_body,
                media_url=campaign.media_url, button_text=campaign.button_text,
                campaign_id=campaign.id)
            if result.status == "sent":
                recipient.status = "sent"
                recipient.channel_used = channel
                recipient.provider_message_id = result.message_id
                recipient.error_detail = None
            else:
                can_fallback = (campaign.fallback_channel == "sms" and channel != "sms"
                                and result.status in {"unsupported_device", "failed"})
                if can_fallback:
                    fallback = await get_provider("sms").send(
                        phone_number=customer.phone_number,
                        body=f"{campaign.message_body} Offer: https://example.com/offers/{campaign.id}",
                        campaign_id=campaign.id)
                    recipient.fallback_used = True
                    recipient.channel_used = "sms"
                    recipient.provider_message_id = fallback.message_id
                    recipient.status = "sent" if fallback.status == "sent" else "failed"
                    recipient.error_detail = fallback.error
                else:
                    recipient.status = "failed"
                    recipient.channel_used = channel
                    recipient.error_detail = result.error or result.status
            recipient.updated_at = utc_now()
            db.commit()
            await asyncio.sleep(0.01)

        pending = db.scalar(select(CampaignRecipient.id).where(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status.in_(["pending", "processing"])).limit(1))
        campaign.status = "completed" if pending is None else "processing"
        db.commit()
    except Exception:
        db.rollback()
        campaign = db.get(Campaign, campaign_id)
        if campaign:
            campaign.status = "failed"
            db.commit()
        raise
    finally:
        db.close()
