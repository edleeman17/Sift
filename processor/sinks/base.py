from abc import ABC, abstractmethod
from models import Message


class NotificationSink(ABC):
    """Base class for notification sinks."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Sink name for logging."""
        pass

    @abstractmethod
    async def send(self, msg: Message) -> bool:
        """Send notification. Returns True on success."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if sink is enabled."""
        pass
