from dataclasses import dataclass
from uuid import uuid4

@dataclass
class SendResult:
    status: str
    message_id: str | None = None
    error: str | None = None

class MockMessagingProvider:
    # Mock only: no real messages are sent.
    def __init__(self, channel: str):
        self.channel = channel

    async def send(self, *, phone_number: str, body: str, media_url: str | None = None,
                   button_text: str | None = None, campaign_id: int | None = None) -> SendResult:
        if self.channel == "rcs" and phone_number.endswith("0000"):
            return SendResult(status="unsupported_device", error="Mock: RCS unsupported")
        if phone_number.endswith("9999"):
            return SendResult(status="failed", error=f"Mock: {self.channel} provider failure")
        return SendResult(status="sent", message_id=f"mock-{self.channel}-{uuid4().hex[:12]}")

def get_provider(channel: str) -> MockMessagingProvider:
    return MockMessagingProvider(channel)
