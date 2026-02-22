# Notification Sinks

Sinks are plugins that forward notifications to external services. Each sink is a separate module that can be enabled/disabled via `config.yaml`.

## Available Sinks

| Sink | Description | Config Key |
|------|-------------|------------|
| `console` | Prints to stdout (for debugging) | `sinks.console` |
| `bark` | iOS push notifications via Bark server | `sinks.bark` |
| `ntfy` | Push via ntfy.sh or self-hosted | `sinks.ntfy` |
| `twilio` | SMS via Twilio API | `sinks.twilio` |
| `imessage` | SMS via macOS Messages.app | `sinks.imessage` |

## Creating a New Sink

1. Create a new file in `processor/sinks/`, e.g., `my_sink.py`
2. Extend the `NotificationSink` base class
3. Register it in `__init__.py`
4. Add initialization in `main.py` lifespan
5. Add config section to `config.yaml`

### Example: Custom Webhook Sink

```python
# processor/sinks/webhook_sink.py
import httpx
from models import Message
from .base import NotificationSink


class WebhookSink(NotificationSink):
    """Sends notifications to a webhook URL."""

    def __init__(self, url: str, secret: str = "", enabled: bool = True):
        self._url = url
        self._secret = secret
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "webhook"

    async def send(self, msg: Message) -> bool:
        if not self._enabled or not self._url:
            return False

        try:
            payload = {
                "app": msg.app,
                "title": msg.title,
                "body": msg.body,
                "priority": msg.priority,
            }
            headers = {}
            if self._secret:
                headers["Authorization"] = f"Bearer {self._secret}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._url, json=payload, headers=headers)
                return resp.status_code in (200, 201, 202, 204)
        except Exception as e:
            print(f"[webhook] Error: {e}")
            return False

    def is_enabled(self) -> bool:
        return self._enabled and bool(self._url)
```

### Register in `__init__.py`

```python
from .webhook_sink import WebhookSink
```

### Add to `main.py` lifespan

```python
webhook_conf = sinks_config.get("webhook", {})
if webhook_conf.get("enabled", False):
    app.state.sinks.append(WebhookSink(
        url=webhook_conf.get("url", ""),
        secret=webhook_conf.get("secret", ""),
    ))
```

### Config in `config.yaml`

```yaml
sinks:
  webhook:
    enabled: true
    url: "https://example.com/webhook"
    secret: "your-secret-token"
```

## Sink Interface

All sinks must implement the `NotificationSink` abstract base class:

```python
class NotificationSink(ABC):
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
        """Check if sink is properly configured and enabled."""
        pass
```

## Message Object

The `Message` object passed to `send()` contains:

| Field | Type | Description |
|-------|------|-------------|
| `app` | `str` | App name (e.g., "whatsapp", "messages") |
| `title` | `str` | Notification title/sender |
| `body` | `str` | Notification body text |
| `priority` | `str` | "default", "high", or "critical" |
| `action_url` | `str?` | Optional tel:/sms: URL for tap-to-call |
| `timestamp` | `datetime?` | When notification was received |

## Testing Your Sink

```bash
# Start the processor with your sink enabled
make rebuild

# Send a test notification
curl -X POST http://localhost:8090/notification \
  -H "Content-Type: application/json" \
  -d '{"app": "test", "title": "Test", "body": "Hello from test"}'
```

Check the processor logs for your sink's output:
```bash
make logs
```
