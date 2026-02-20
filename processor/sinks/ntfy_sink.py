import httpx
from models import Message
from .base import NotificationSink


class NtfySink(NotificationSink):
    """Sends notifications to ntfy server."""

    def __init__(self, url: str, enabled: bool = True):
        self._url = url
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "ntfy"

    def _sanitize_header(self, value: str) -> str:
        """Remove non-ASCII chars from header values."""
        return value.encode('ascii', errors='ignore').decode('ascii')

    def _map_priority(self, priority: str) -> str:
        """Map internal priority to ntfy priority (1-5 or names)."""
        # ntfy: min, low, default, high, urgent (or 1-5)
        mapping = {
            "critical": "urgent",
            "high": "high",
            "default": "default",
        }
        return mapping.get(priority, "default")

    async def send(self, msg: Message) -> bool:
        if not self._enabled:
            return False

        try:
            ntfy_priority = self._map_priority(msg.priority)
            # verify=False for self-signed certs on local network
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.post(
                    self._url,
                    headers={
                        "Title": self._sanitize_header(f"{msg.app}: {msg.title}"),
                        "Priority": ntfy_priority,
                        "Tags": msg.app,
                    },
                    content=msg.body.encode('utf-8'),
                )
                return resp.status_code == 200
        except Exception as e:
            print(f"[ntfy] Error sending: {e}")
            return False

    def is_enabled(self) -> bool:
        return self._enabled
