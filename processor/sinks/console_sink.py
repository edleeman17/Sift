from models import Message
from .base import NotificationSink


class ConsoleSink(NotificationSink):
    """Prints notifications to console for testing."""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "console"

    async def send(self, msg: Message) -> bool:
        print(f"[NOTIFICATION] {msg.app} | {msg.title}: {msg.body}")
        return True

    def is_enabled(self) -> bool:
        return self._enabled
