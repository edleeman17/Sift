import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from models import Message


@dataclass
class RateLimitResult:
    allowed: bool
    reason: str


class RateLimiter:
    """Per-app/sender rate limiting with deduplication."""

    def __init__(self, max_per_hour: int = 20, cooldown_seconds: int = 60, app_dedup_hours: dict[str, int] = None, exempt_apps: list[str] = None, no_cooldown_apps: list[str] = None):
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds
        self.app_dedup_hours = app_dedup_hours or {}
        self.exempt_apps = set(exempt_apps or [])
        self.no_cooldown_apps = set(no_cooldown_apps or [])
        # Track messages per app+sender
        self._history: dict[str, list[datetime]] = defaultdict(list)
        # Track recent message hashes for deduplication
        self._recent_hashes: dict[str, datetime] = {}
        self._default_dedup_window = timedelta(minutes=5)

    def check(self, msg: Message) -> RateLimitResult:
        """Check if message should be rate limited."""
        # Skip rate limiting for exempt apps
        if msg.app in self.exempt_apps:
            return RateLimitResult(allowed=True, reason="")

        now = datetime.utcnow()
        key = f"{msg.app}:{msg.title}"

        # Get app-specific dedup window or default
        if msg.app in self.app_dedup_hours:
            dedup_window = timedelta(hours=self.app_dedup_hours[msg.app])
        else:
            dedup_window = self._default_dedup_window

        # Dedupe check first
        msg_hash = self._hash_message(msg)
        if msg_hash in self._recent_hashes:
            hash_time = self._recent_hashes[msg_hash]
            if now - hash_time < dedup_window:
                hours = dedup_window.total_seconds() / 3600
                if hours >= 1:
                    return RateLimitResult(
                        allowed=False,
                        reason=f"duplicate within {int(hours)}h"
                    )
                return RateLimitResult(
                    allowed=False,
                    reason=f"duplicate within {int(dedup_window.total_seconds())}s"
                )

        # Clean old entries
        self._cleanup(now)

        # Check cooldown (skip for no_cooldown_apps)
        if self._history[key] and msg.app not in self.no_cooldown_apps:
            last_msg = self._history[key][-1]
            cooldown_delta = timedelta(seconds=self.cooldown_seconds)
            if now - last_msg < cooldown_delta:
                wait = (cooldown_delta - (now - last_msg)).seconds
                return RateLimitResult(
                    allowed=False,
                    reason=f"cooldown: wait {wait}s"
                )

        # Check hourly limit
        hour_ago = now - timedelta(hours=1)
        recent_count = sum(1 for t in self._history[key] if t > hour_ago)
        if recent_count >= self.max_per_hour:
            return RateLimitResult(
                allowed=False,
                reason=f"hourly limit reached ({self.max_per_hour}/hr)"
            )

        # Record this message
        self._history[key].append(now)
        self._recent_hashes[msg_hash] = now

        return RateLimitResult(allowed=True, reason="")

    def _hash_message(self, msg: Message) -> str:
        """Create hash of message for deduplication.

        Normalizes content for fuzzy matching:
        - Lowercase
        - Strip whitespace
        - Remove emoji (often varies between duplicate messages)
        - Truncate body to first 100 chars (ignore trailing content)
        """
        import re
        # Remove emoji and special unicode
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map
            u"\U0001F1E0-\U0001F1FF"  # flags
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)

        title_norm = emoji_pattern.sub('', msg.title.lower().strip())
        body_norm = emoji_pattern.sub('', msg.body[:100].lower().strip())

        content = f"{msg.app}:{title_norm}:{body_norm}"
        return hashlib.md5(content.encode()).hexdigest()

    def _cleanup(self, now: datetime):
        """Remove old entries."""
        hour_ago = now - timedelta(hours=1)
        max_dedup = max(self.app_dedup_hours.values()) if self.app_dedup_hours else 1
        max_dedup_window = timedelta(hours=max_dedup)

        # Clean history
        for key in list(self._history.keys()):
            self._history[key] = [t for t in self._history[key] if t > hour_ago]
            if not self._history[key]:
                del self._history[key]

        # Clean dedup hashes (use max dedup window to be safe)
        for h in list(self._recent_hashes.keys()):
            if now - self._recent_hashes[h] > max_dedup_window:
                del self._recent_hashes[h]
