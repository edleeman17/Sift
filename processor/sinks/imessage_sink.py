import httpx
from models import Message
from .base import NotificationSink


class IMessageSink(NotificationSink):
    """Sends notifications via iMessage Gateway (SMS to dumbphone)."""

    def __init__(self, gateway_url: str, recipient: str, enabled: bool = True):
        self._gateway_url = gateway_url.rstrip("/")
        self._recipient = recipient
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "imessage"

    async def send(self, msg: Message) -> bool:
        if not self._enabled:
            return False

        # Format message for SMS (160 char limit)
        prefix = f"{msg.app}: {msg.title}\n"
        max_body = 160 - len(prefix)
        body = msg.body[:max_body] if len(msg.body) > max_body else msg.body
        sms_text = f"{prefix}{body}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._gateway_url}/send",
                    json={
                        "recipient": self._recipient,
                        "message": sms_text,
                    }
                )
                if resp.status_code == 200:
                    return True
                else:
                    print(f"[imessage] Gateway error: {resp.status_code} {resp.text}")
                    return False
        except Exception as e:
            print(f"[imessage] Error sending: {e}")
            return False

    def is_enabled(self) -> bool:
        return self._enabled
