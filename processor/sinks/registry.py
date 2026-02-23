"""Sink registry for plugin-style loading."""

from typing import Type
from .base import NotificationSink


# Registry of available sink types
_SINK_REGISTRY: dict[str, Type[NotificationSink]] = {}

# Configuration warnings collected during loading
_CONFIG_WARNINGS: list[dict] = []


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


def get_config_warnings() -> list[dict]:
    """Get configuration warnings from last load."""
    return _CONFIG_WARNINGS.copy()


def load_sinks_from_config(sinks_config: dict) -> list[NotificationSink]:
    """Load and instantiate sinks from config dict."""
    global _CONFIG_WARNINGS
    from .console_sink import ConsoleSink
    from .ntfy_sink import NtfySink
    from .bark_sink import BarkSink
    from .twilio_sink import TwilioSink
    from .imessage_sink import IMessageSink

    sinks = []
    _CONFIG_WARNINGS = []  # Reset warnings on each load

    # Console sink
    console_conf = sinks_config.get("console", {})
    if console_conf.get("enabled", True):
        sinks.append(ConsoleSink())

    # ntfy sink
    ntfy_conf = sinks_config.get("ntfy", {})
    if ntfy_conf.get("enabled", False):
        url = ntfy_conf.get("url", "")
        if not url:
            _CONFIG_WARNINGS.append({
                "sink": "ntfy",
                "message": "Enabled but no URL configured",
            })
        else:
            sinks.append(NtfySink(url=url))

    # Bark sink
    bark_conf = sinks_config.get("bark", {})
    if bark_conf.get("enabled", False):
        url = bark_conf.get("url", "")
        device_key = bark_conf.get("device_key", "")
        if not url or not device_key:
            missing = []
            if not url:
                missing.append("url")
            if not device_key:
                missing.append("device_key")
            _CONFIG_WARNINGS.append({
                "sink": "bark",
                "message": f"Enabled but missing: {', '.join(missing)}",
            })
        else:
            sinks.append(BarkSink(url=url, device_key=device_key))

    # Twilio sink
    twilio_conf = sinks_config.get("twilio", {})
    if twilio_conf.get("enabled", False):
        account_sid = twilio_conf.get("account_sid", "")
        auth_token = twilio_conf.get("auth_token", "")
        from_number = twilio_conf.get("from_number", "")
        to_number = twilio_conf.get("to_number", "")
        missing = []
        if not account_sid:
            missing.append("account_sid")
        if not auth_token:
            missing.append("auth_token")
        if not from_number:
            missing.append("from_number")
        if not to_number:
            missing.append("to_number")
        if missing:
            _CONFIG_WARNINGS.append({
                "sink": "twilio",
                "message": f"Enabled but missing: {', '.join(missing)}",
            })
        else:
            sinks.append(TwilioSink(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
                to_number=to_number,
            ))

    # iMessage sink
    imessage_conf = sinks_config.get("imessage", {})
    if imessage_conf.get("enabled", False):
        recipient = imessage_conf.get("recipient", "")
        if not recipient:
            _CONFIG_WARNINGS.append({
                "sink": "imessage",
                "message": "Enabled but no recipient configured",
            })
        else:
            sinks.append(IMessageSink(
                gateway_url=imessage_conf.get("gateway_url", "http://host.docker.internal:8095"),
                recipient=recipient,
            ))

    # Log warnings
    for w in _CONFIG_WARNINGS:
        print(f"[registry] WARNING: {w['sink']} - {w['message']}")

    return sinks
