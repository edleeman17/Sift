"""Battery monitoring service - alerts when iPhone battery drops below threshold."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from models import Message
from services.pi_health import get_pi_health

log = logging.getLogger(__name__)


class BatteryMonitor:
    """Monitors iPhone battery via Pi health endpoint and sends alerts."""

    def __init__(self, sinks: list, threshold: int = 20, cooldown_minutes: int = 60):
        self.sinks = sinks
        self.threshold = threshold
        self.cooldown = cooldown_minutes * 60  # Convert to seconds
        self.last_alert_time: Optional[datetime] = None
        self.last_battery: Optional[int] = None
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the battery monitoring loop."""
        log.info(f"Starting battery monitor (threshold={self.threshold}%, cooldown={self.cooldown // 60}min)")
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop the battery monitoring loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            log.info("Battery monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - checks battery every 60 seconds."""
        while True:
            try:
                await asyncio.sleep(60)
                await self._check_battery()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Battery monitor error: {e}")

    async def _check_battery(self):
        """Check current battery level and alert if needed."""
        health = await get_pi_health()
        battery = health.get("battery")

        if battery is None:
            return  # No battery data available

        previous = self.last_battery
        self.last_battery = battery

        # Reset alert when battery goes above threshold
        if battery > self.threshold:
            if self.last_alert_time:
                log.info(f"Battery recovered to {battery}%, resetting alert state")
                self.last_alert_time = None
            return

        # Battery is below threshold
        if self._should_alert(previous):
            await self._send_alert(battery)

    def _should_alert(self, previous_battery: Optional[int]) -> bool:
        """Determine if we should send an alert."""
        # First time crossing below threshold
        if previous_battery is not None and previous_battery > self.threshold:
            return True

        # Cooldown expired
        if self.last_alert_time:
            elapsed = (datetime.now() - self.last_alert_time).total_seconds()
            return elapsed >= self.cooldown

        # First check and already low - alert once
        return self.last_alert_time is None

    async def _send_alert(self, battery: int):
        """Send low battery alert to all enabled sinks."""
        self.last_alert_time = datetime.now()

        msg = Message(
            app="system",
            title="iPhone Battery Low",
            body=f"Battery at {battery}%",
            timestamp=datetime.now(),
            priority="high"
        )

        sent_to = []
        for sink in self.sinks:
            if sink.is_enabled():
                try:
                    success = await sink.send(msg)
                    if success:
                        sent_to.append(sink.name)
                except Exception as e:
                    log.error(f"Failed to send battery alert to {sink.name}: {e}")

        log.warning(f"[BATTERY] Low battery alert ({battery}%) sent to: {', '.join(sent_to)}")
