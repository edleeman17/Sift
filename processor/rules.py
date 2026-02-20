from dataclasses import dataclass
from enum import Enum
from typing import Optional
import re
import yaml
from pathlib import Path

from models import Message


# Unicode control characters to strip (bidi, zero-width, etc.)
CONTROL_CHARS = re.compile(r'[\u2068\u2069\u200b\u200c\u200d\ufeff\u202a-\u202e]')


def normalize_text(text: str) -> str:
    """Strip invisible Unicode control characters."""
    return CONTROL_CHARS.sub('', text)


class Action(Enum):
    SEND = "send"
    DROP = "drop"
    LLM = "llm"


@dataclass
class RuleResult:
    action: Action
    reason: str
    priority: str = "default"  # default, high, critical
    prompt: str = None  # Custom LLM prompt for action=llm


class RuleEngine:
    """Evaluates notifications against configured rules."""

    def __init__(self, config_path: Path):
        self.config = self._load_config(config_path)
        self.apps = self.config.get("apps", {})
        self.global_config = self.config.get("global", {})
        self.global_rules = self.global_config.get("rules", [])
        self._regex_cache: dict[str, re.Pattern] = {}

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            return {"apps": {}, "global": {"unknown_apps": "drop"}}
        with open(path) as f:
            return yaml.safe_load(f) or {}

    def evaluate(self, msg: Message) -> RuleResult:
        """Evaluate a message against rules."""
        # Check global rules first (apply to all apps)
        for rule in self.global_rules:
            if self._matches_rule(msg, rule):
                action = Action(rule.get("action", "send"))
                priority = rule.get("priority", "default")
                prompt = rule.get("prompt")
                return RuleResult(
                    action=action,
                    reason=f"global rule: {self._describe_rule(rule)}",
                    priority=priority,
                    prompt=prompt
                )

        app_config = self.apps.get(msg.app)

        # Unknown app handling
        if app_config is None:
            unknown_action = self.global_config.get("unknown_apps", "drop")
            return RuleResult(
                action=Action(unknown_action),
                reason=f"unknown app '{msg.app}'"
            )

        # Check app-specific rules
        rules = app_config.get("rules", [])
        for rule in rules:
            if self._matches_rule(msg, rule):
                action = Action(rule.get("action", "send"))
                priority = rule.get("priority", "default")
                prompt = rule.get("prompt")
                return RuleResult(
                    action=action,
                    reason=f"matched rule: {self._describe_rule(rule)}",
                    priority=priority,
                    prompt=prompt
                )

        # Fall back to default for app
        default = app_config.get("default", "drop")
        return RuleResult(
            action=Action(default),
            reason=f"app default: {default}"
        )

    def _get_regex(self, pattern: str) -> re.Pattern:
        """Get compiled regex, using cache for performance."""
        if pattern not in self._regex_cache:
            self._regex_cache[pattern] = re.compile(pattern, re.IGNORECASE)
        return self._regex_cache[pattern]

    def _matches_rule(self, msg: Message, rule: dict) -> bool:
        """Check if message matches a rule."""
        # Normalize text to strip invisible Unicode control characters
        title = normalize_text(msg.title.lower())
        body = normalize_text(msg.body.lower())
        combined = f"{title} {body}"

        # Simple contains matching
        if "sender_contains" in rule:
            if rule["sender_contains"].lower() not in title:
                return False

        if "sender_not_contains" in rule:
            if rule["sender_not_contains"].lower() in title:
                return False

        if "body_contains" in rule:
            if rule["body_contains"].lower() not in body:
                return False

        if "body_not_contains" in rule:
            if rule["body_not_contains"].lower() in body:
                return False

        if "channel_contains" in rule:
            term = rule["channel_contains"].lower()
            if term not in title and term not in body:
                return False

        if "contains" in rule:
            # Match anywhere in title or body
            if rule["contains"].lower() not in combined:
                return False

        # Regex matching
        if "sender_regex" in rule:
            try:
                if not self._get_regex(rule["sender_regex"]).search(msg.title):
                    return False
            except re.error:
                return False

        if "body_regex" in rule:
            try:
                if not self._get_regex(rule["body_regex"]).search(msg.body):
                    return False
            except re.error:
                return False

        if "regex" in rule:
            # Match anywhere in title or body
            try:
                if not self._get_regex(rule["regex"]).search(f"{msg.title} {msg.body}"):
                    return False
            except re.error:
                return False

        return True

    def _describe_rule(self, rule: dict) -> str:
        """Human-readable rule description."""
        parts = []
        if "sender_contains" in rule:
            parts.append(f"sender contains '{rule['sender_contains']}'")
        if "sender_not_contains" in rule:
            parts.append(f"sender not contains '{rule['sender_not_contains']}'")
        if "body_contains" in rule:
            parts.append(f"body contains '{rule['body_contains']}'")
        if "body_not_contains" in rule:
            parts.append(f"body not contains '{rule['body_not_contains']}'")
        if "channel_contains" in rule:
            parts.append(f"channel contains '{rule['channel_contains']}'")
        if "contains" in rule:
            parts.append(f"contains '{rule['contains']}'")
        if "sender_regex" in rule:
            parts.append(f"sender matches /{rule['sender_regex']}/")
        if "body_regex" in rule:
            parts.append(f"body matches /{rule['body_regex']}/")
        if "regex" in rule:
            parts.append(f"matches /{rule['regex']}/")
        return " AND ".join(parts) if parts else "empty rule"
