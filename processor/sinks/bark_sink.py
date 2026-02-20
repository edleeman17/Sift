import httpx
from urllib.parse import quote
from models import Message
from .base import NotificationSink


class BarkSink(NotificationSink):
    """Sends notifications to Bark server (iOS push via APNs)."""

    def __init__(self, url: str, device_key: str, enabled: bool = True):
        self._url = url.rstrip('/')
        self._device_key = device_key
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "bark"

    def _map_level(self, priority: str) -> str:
        """Map internal priority to Bark level."""
        # Bark: active, timeSensitive, passive, critical
        mapping = {
            "critical": "critical",
            "high": "timeSensitive",
            "default": "timeSensitive",
        }
        return mapping.get(priority, "timeSensitive")

    async def send(self, msg: Message) -> bool:
        if not self._enabled or not self._device_key:
            return False

        try:
            title = f"{msg.app}: {msg.title}"
            body = msg.body[:256] if msg.body else ""  # Bark has length limits
            level = self._map_level(msg.priority)

            payload = {
                "title": title,
                "body": body,
                "group": msg.app,
                "level": level,
            }

            # Add action URL if available (tel: or sms:)
            if msg.action_url:
                payload["url"] = msg.action_url

            # Use POST with JSON for better Unicode support
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._url}/{self._device_key}",
                    json=payload,
                )
                return resp.status_code == 200
        except Exception as e:
            print(f"[bark] Error sending: {e}")
            return False

    def is_enabled(self) -> bool:
        return self._enabled and bool(self._device_key)
