from enum import StrEnum
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

class Channel(StrEnum):
    RCS = "rcs"
    WHATSAPP = "whatsapp"
    SMS = "sms"

class MerchantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    shop_name: str = Field(min_length=1, max_length=150)
    phone_number: str = Field(min_length=8, max_length=20)
    whatsapp_enabled: bool = False
    default_channel: Channel = Channel.RCS
    fallback_channel: Channel | None = Channel.SMS

class MerchantOut(BaseModel):
    id: int
    name: str
    shop_name: str
    phone_number: str
    whatsapp_enabled: bool
    default_channel: str
    fallback_channel: str | None
    api_key: str
    model_config = ConfigDict(from_attributes=True)

class CampaignCreate(BaseModel):
    merchant_id: int
    title: str = Field(min_length=1, max_length=200)
    message_body: str = Field(min_length=1, max_length=4000)
    media_url: HttpUrl | None = None
    button_text: str | None = Field(default=None, max_length=100)
    primary_channel: Channel | None = None
    fallback_channel: Channel | None = Channel.SMS
    target_tag: str | None = Field(default=None, max_length=100)

class CampaignOut(BaseModel):
    id: int
    merchant_id: int
    title: str
    message_body: str
    media_url: str | None
    button_text: str | None
    primary_channel: str
    fallback_channel: str | None
    target_tag: str | None
    status: str
    model_config = ConfigDict(from_attributes=True)

class WebhookEvent(BaseModel):
    event_type: str = Field(min_length=1)
    merchant_id: int
    phone_number: str | None = None
    campaign_id: int | None = None
    postback_data: str | None = None
    provider_message_id: str | None = None
    status: str | None = None
