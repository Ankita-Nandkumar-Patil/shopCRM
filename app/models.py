from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Merchant(Base):
    __tablename__ = "merchants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    shop_name: Mapped[str] = mapped_column(String(150))
    phone_number: Mapped[str] = mapped_column(String(20))
    api_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_channel: Mapped[str] = mapped_column(String(20), default="rcs", nullable=False)
    fallback_channel: Mapped[str | None] = mapped_column(String(20), default="sms", nullable=True)
    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="merchant")

class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("merchant_id", "phone_number", name="uq_customer_merchant_phone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), index=True)
    phone_number: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    merchant: Mapped["Merchant"] = relationship(back_populates="customers")

class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message_body: Mapped[str] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    button_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_channel: Mapped[str] = mapped_column(String(20), default="rcs", nullable=False)
    fallback_channel: Mapped[str | None] = mapped_column(String(20), default="sms", nullable=True)
    target_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    merchant: Mapped["Merchant"] = relationship(back_populates="campaigns")
    recipients: Mapped[list["CampaignRecipient"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")

class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"
    __table_args__ = (UniqueConstraint("campaign_id", "customer_id", name="uq_campaign_customer"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    channel_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    campaign: Mapped["Campaign"] = relationship(back_populates="recipients")
    customer: Mapped["Customer"] = relationship()

class Interaction(Base):
    __tablename__ = "interactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50))
    postback_data: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promo_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
