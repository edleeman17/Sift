"""Sink registry for plugin-style loading."""

from typing import Type
from .base import NotificationSink


# Registry of available sink types
_SINK_REGISTRY: dict[str, Type[NotificationSink]] = {}


def register_sink(name: str):
    """Decorator to register a sink class."""
    def decorator(cls: Type[NotificationSink]):
        _SINK_REGISTRY[name] = cls
        return cls
    return decorator


def get_sink_class(name: str) -> Type[NotificationSink] | None:
    """Get a sink class by name."""
    return _SINK_REGISTRY.get(name)


def get_available_sinks() -> list[str]:
    """Get list of available sink names."""
    return list(_SINK_REGISTRY.keys())


def load_sinks_from_config(sinks_config: dict) -> list[NotificationSink]:
    """Load and instantiate sinks from config dict."""
    from .console_sink import ConsoleSink
    from .ntfy_sink import NtfySink
    from .bark_sink import BarkSink
    from .twilio_sink import TwilioSink
    from .imessage_sink import IMessageSink

    sinks = []

    # Console sink
    console_conf = sinks_config.get("console", {})
    if console_conf.get("enabled", True):
        sinks.append(ConsoleSink())

    # ntfy sink
    ntfy_conf = sinks_config.get("ntfy", {})
    if ntfy_conf.get("enabled", False):
        sinks.append(NtfySink(url=ntfy_conf.get("url", "")))

    # Bark sink
    bark_conf = sinks_config.get("bark", {})
    if bark_conf.get("enabled", False):
        sinks.append(BarkSink(
            url=bark_conf.get("url", ""),
            device_key=bark_conf.get("device_key", "")
        ))

    # Twilio sink
    twilio_conf = sinks_config.get("twilio", {})
    if twilio_conf.get("enabled", False):
        sinks.append(TwilioSink(
            account_sid=twilio_conf.get("account_sid", ""),
            auth_token=twilio_conf.get("auth_token", ""),
            from_number=twilio_conf.get("from_number", ""),
            to_number=twilio_conf.get("to_number", ""),
        ))

    # iMessage sink
    imessage_conf = sinks_config.get("imessage", {})
    if imessage_conf.get("enabled", False):
        sinks.append(IMessageSink(
            gateway_url=imessage_conf.get("gateway_url", "http://host.docker.internal:8095"),
            recipient=imessage_conf.get("recipient", ""),
        ))

    return sinks
