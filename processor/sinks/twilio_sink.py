import httpx
from models import Message
from .base import NotificationSink


class TwilioSink(NotificationSink):
    """Sends notifications via Twilio SMS."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_number: str,
        enabled: bool = True,
    ):
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._to_number = to_number
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "twilio"

    async def send(self, msg: Message) -> bool:
        if not self._enabled:
            return False

        try:
            # Truncate to SMS limit (leaving room for app/title prefix)
            prefix = f"{msg.app}: {msg.title}\n"
            max_body = 160 - len(prefix)
            body = msg.body[:max_body] if len(msg.body) > max_body else msg.body
            sms_text = f"{prefix}{body}"

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    auth=(self._account_sid, self._auth_token),
                    data={
                        "From": self._from_number,
                        "To": self._to_number,
                        "Body": sms_text,
                    },
                )
                if resp.status_code == 201:
                    return True
                else:
                    print(f"[twilio] Error {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            print(f"[twilio] Error sending: {e}")
            return False

    def is_enabled(self) -> bool:
        return self._enabled
