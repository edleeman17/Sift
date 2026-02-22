import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx

from models import Message

# Ollama configuration from environment
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# LLM log file for detailed query logging
LLM_LOG_FILE = Path("/app/data/llm.log")


def log_llm(msg: str):
    """Log to stdout for basic logging."""
    print(f"[LLM] {msg}")


def log_llm_query(query_type: str, prompt: str, response: str, duration_ms: int, model: str = None):
    """Log detailed LLM query info to file for status page display."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        model = model or OLLAMA_MODEL

        # Truncate for log display but keep enough context
        prompt_preview = prompt.replace('\n', ' ')[:200]
        response_preview = response.replace('\n', ' ')[:200]

        log_entry = (
            f"{timestamp} | {query_type} | {model} | {duration_ms}ms\n"
            f"  PROMPT: {prompt_preview}\n"
            f"  RESPONSE: {response_preview}\n"
        )

        # Append to log file
        with open(LLM_LOG_FILE, "a") as f:
            f.write(log_entry)

        # Keep log file from growing too large (keep last 100 entries)
        _trim_log_file()
    except Exception as e:
        print(f"[LLM] Log write error: {e}")


def _trim_log_file(max_entries: int = 100):
    """Keep log file from growing too large."""
    try:
        if not LLM_LOG_FILE.exists():
            return
        lines = LLM_LOG_FILE.read_text().split('\n')
        # Each entry is 3 lines (header + prompt + response)
        entry_count = sum(1 for line in lines if ' | ' in line and 'ms' in line)
        if entry_count > max_entries:
            # Keep last max_entries entries (3 lines each)
            keep_lines = max_entries * 3
            LLM_LOG_FILE.write_text('\n'.join(lines[-keep_lines:]))
    except Exception:
        pass


async def analyze_feedback_with_ai(feedback_data: list[dict], ollama_url: str = None) -> dict:
    ollama_url = ollama_url or OLLAMA_URL
    """Use LLM to analyze feedback patterns and suggest rules."""
    if not feedback_data:
        return {"analysis": "No feedback data to analyze.", "suggestions": []}

    # Group feedback by outcome
    bad_sends = [f for f in feedback_data if f["action"] == "sent" and f["feedback"] == "bad"]
    good_drops = [f for f in feedback_data if f["action"] == "dropped" and f["feedback"] == "good"]
    good_sends = [f for f in feedback_data if f["action"] == "sent" and f["feedback"] == "good"]
    bad_drops = [f for f in feedback_data if f["action"] == "dropped" and f["feedback"] == "bad"]

    # Build summary for LLM
    def format_notifications(notifs, limit=5):
        lines = []
        for n in notifs[:limit]:
            lines.append(f"- {n['app']}: {n['title'][:30]} | {(n['body'] or '')[:50]}")
        return "\n".join(lines) if lines else "(none)"

    # bad_sends = sent but user says shouldn't have been → suggest drop rules
    # bad_drops = dropped but user says should have been sent → suggest send rules
    all_feedback = bad_sends + bad_drops

    if not all_feedback:
        return {"analysis": "No actionable feedback yet. Mark sent notifications with 👎 if they shouldn't have been sent, or dropped notifications with 👎 if they should have been sent.", "suggestions": []}

    prompt = f"""Analyze notification feedback and suggest YAML rules.

WRONGLY SENT ({len(bad_sends)} - sent but shouldn't have been, need DROP rules):
{format_notifications(bad_sends, limit=10)}

WRONGLY DROPPED ({len(bad_drops)} - dropped but should have been sent, need SEND rules):
{format_notifications(bad_drops, limit=10)}

For EACH notification above, suggest a specific rule. Format:

```yaml
appname:
  rules:
    - sender_contains: "exact text from title"
      action: drop
```

Or for body matching:
```yaml
    - body_contains: "exact text"
      action: send
```

Available matchers: sender_contains, body_contains, sender_not_contains, body_not_contains

IMPORTANT: Generate ONE rule per notification. Use exact text from the notifications. Be specific."""

    log_llm(f"AI prompt: bad_sends={len(bad_sends)}, bad_drops={len(bad_drops)}")

    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for slow models
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": "qwen2.5:7b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 1024},
                },
            )
            resp.raise_for_status()
            result = resp.json()
            duration_ms = int((time.time() - start_time) * 1000)
            analysis = result.get("response", "No response from LLM")
            log_llm(f"AI insights generated: {len(analysis)} chars in {duration_ms}ms")
            log_llm_query("feedback_analysis", prompt, analysis, duration_ms, "qwen2.5:7b")
            return {
                "analysis": analysis,
                "stats": {
                    "good_sends": len(good_sends),
                    "bad_sends": len(bad_sends),
                    "good_drops": len(good_drops),
                    "bad_drops": len(bad_drops),
                }
            }
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        log_llm(f"AI insights error: {error_msg}")
        return {"analysis": f"Error: {error_msg}", "suggestions": []}


@dataclass
class ClassificationResult:
    should_send: bool
    confidence: float
    reason: str


@dataclass
class SentimentResult:
    is_urgent: bool
    sentiment: str  # urgent, worried, angry, normal
    reason: str


class LLMClassifier:
    """Ollama-based notification classifier."""

    def __init__(self, ollama_url: str = None, model: str = None):
        self.ollama_url = ollama_url or OLLAMA_URL
        self.model = model or OLLAMA_MODEL
        self._available: Optional[bool] = None

    async def check_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
                self._available = resp.status_code == 200
                return self._available
        except Exception:
            self._available = False
            return False

    async def classify(self, msg: Message, custom_prompt: str = None) -> ClassificationResult:
        """Classify notification importance using LLM."""
        log_llm(f"Classifying: {msg.app} | {msg.title}: {msg.body[:50]}...")

        # Check availability if not yet checked
        if self._available is None:
            await self.check_available()

        if not self._available:
            log_llm("Unavailable, defaulting to DROP (6p rule)")
            return ClassificationResult(
                should_send=False,
                confidence=0.0,
                reason="LLM unavailable, defaulting to drop"
            )

        if custom_prompt:
            # Use custom prompt with message context
            prompt = f"""You are filtering notifications. {custom_prompt}

App: {msg.app}
From: {msg.title}
Message: {msg.body}

Based on the above criteria, should this notification be forwarded?
Answer with a single word: SEND or DROP"""
        else:
            prompt = self._build_prompt(msg)

        try:
            start_time = time.time()
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for slow models
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 256},
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                duration_ms = int((time.time() - start_time) * 1000)
                raw_response = result.get("response", "")
                log_llm(f"Response ({duration_ms}ms): {raw_response[:100]}")
                classification = self._parse_response(raw_response)
                action = "SEND" if classification.should_send else "DROP"
                log_llm(f"Decision: {action} - {classification.reason}")
                log_llm_query("classify", prompt, f"{action}: {raw_response}", duration_ms, self.model)
                return classification
        except Exception as e:
            log_llm(f"Error: {type(e).__name__}: {e}, defaulting to DROP (6p rule)")
            return ClassificationResult(
                should_send=False,
                confidence=0.0,
                reason=f"LLM error, defaulting to drop"
            )

    def _build_prompt(self, msg: Message) -> str:
        return f"""You are filtering notifications for SMS forwarding. Each SMS costs 6p.
Only SEND if the message requires IMMEDIATE attention or is time-sensitive.
When in doubt, DROP. The user can check their phone later for non-urgent things.

App: {msg.app}
From: {msg.title}
Message: {msg.body}

SEND - worth 6p (urgent, time-sensitive, requires action):
- Someone asking to meet up or make plans → SEND
- Direct question needing a response → SEND
- Client reporting a problem → SEND
- Someone needs help or is waiting → SEND

DROP - not worth 6p (can wait, noise, FYI only):
- Group chat banter, reactions, "lol", "haha" → DROP
- Sharing memes, links, photos to look at later → DROP
- News, updates, announcements → DROP
- Social media engagement notifications → DROP
- Marketing, newsletters, receipts → DROP
- "Thanks", "OK", acknowledgments → DROP

Classify this notification. Answer only SEND or DROP:
App: {msg.app}
From: {msg.title}
Message: {msg.body}
Answer:"""

    def _parse_response(self, response: str) -> ClassificationResult:
        """Parse LLM response into classification."""
        lines = response.strip().split("\n")
        first_word = lines[0].strip().upper() if lines else ""

        should_send = first_word == "SEND"
        reason = lines[1].strip() if len(lines) > 1 else "LLM decision"

        return ClassificationResult(
            should_send=should_send,
            confidence=0.8,  # Fixed confidence for now
            reason=reason
        )

    async def analyze_sentiment(self, msg: "Message") -> SentimentResult:
        """Analyze message sentiment for urgency/emotion."""
        log_llm(f"Sentiment check: {msg.app} | {msg.title}: {msg.body[:50]}...")

        if self._available is None:
            await self.check_available()

        if not self._available:
            return SentimentResult(is_urgent=False, sentiment="unknown", reason="LLM unavailable")

        # Check if it's a group chat (title often contains group name or multiple people)
        is_likely_group = "," in msg.title or "Group" in msg.title or "~" in msg.title

        prompt = f"""Classify this chat message. Answer NORMAL unless there is a genuine emergency.

URGENT (extremely rare - genuine emergencies only):
- Someone in physical danger or medical emergency
- "Help", "call 999", "I'm hurt", "accident"
- Explicit "call me NOW it's urgent"

NORMAL (99% of messages - the default):
- Questions: "how are you?", "what's up?", "you there?", "are you coming?"
- Chat: jokes, memes, banter, reactions, emojis
- Sharing: photos, links, videos, articles
- Updates: "I'm here", "on my way", "running late"
- Opinions, stories, venting, complaining
- ANY group chat message (groups are never urgent)
- "Where are you" without explicit distress
- Anything that can wait 1 hour

{"This is a GROUP CHAT - group messages are NEVER urgent. Answer NORMAL." if is_likely_group else ""}

Message from {msg.title}:
{msg.body[:200]}

Answer NORMAL or URGENT (almost always NORMAL):"""

        try:
            start_time = time.time()
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 128},
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                duration_ms = int((time.time() - start_time) * 1000)
                raw = result.get("response", "").strip()
                log_llm(f"Sentiment response ({duration_ms}ms): {raw[:100]}")

                first_word = raw.split()[0].upper() if raw else "NORMAL"
                is_urgent = first_word == "URGENT"
                sentiment = "urgent" if is_urgent else "normal"
                reason = raw.split("\n")[0] if raw else "No response"

                log_llm_query("sentiment", prompt, f"{sentiment}: {raw}", duration_ms, self.model)
                return SentimentResult(
                    is_urgent=is_urgent,
                    sentiment=sentiment,
                    reason=reason
                )
        except Exception as e:
            log_llm(f"Sentiment error: {e}")
            return SentimentResult(is_urgent=False, sentiment="error", reason=str(e))


class BatchedSentimentAnalyzer:
    """Batches sentiment checks to reduce LLM calls."""

    def __init__(self, classifier: LLMClassifier, batch_window: float = 2.0, max_batch_size: int = 10):
        self.classifier = classifier
        self.batch_window = batch_window
        self.max_batch_size = max_batch_size
        self._pending: list[tuple[Message, asyncio.Future]] = []
        self._batch_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def analyze_sentiment(self, msg: Message) -> SentimentResult:
        """Queue message for batched sentiment analysis."""
        future = asyncio.get_event_loop().create_future()

        async with self._lock:
            self._pending.append((msg, future))
            log_llm(f"Batched: {msg.title} ({len(self._pending)} pending)")

            # Start batch timer if this is the first message
            if len(self._pending) == 1:
                self._batch_task = asyncio.create_task(self._process_after_delay())
            # Process immediately if batch is full
            elif len(self._pending) >= self.max_batch_size:
                if self._batch_task:
                    self._batch_task.cancel()
                asyncio.create_task(self._process_batch())

        return await future

    async def _process_after_delay(self):
        """Wait for batch window then process."""
        await asyncio.sleep(self.batch_window)
        await self._process_batch()

    async def _process_batch(self):
        """Process all pending messages in a single LLM call."""
        async with self._lock:
            if not self._pending:
                return
            batch = self._pending[:]
            self._pending = []
            self._batch_task = None

        messages = [msg for msg, _ in batch]
        futures = [fut for _, fut in batch]

        log_llm(f"Processing batch of {len(messages)} messages")

        # Single message - use regular sentiment check
        if len(messages) == 1:
            result = await self.classifier.analyze_sentiment(messages[0])
            if not futures[0].done():
                futures[0].set_result(result)
            return

        # Build batched prompt
        results = await self._analyze_batch(messages)

        # Resolve futures
        for i, future in enumerate(futures):
            if not future.done():
                if i < len(results):
                    future.set_result(results[i])
                else:
                    future.set_result(SentimentResult(is_urgent=False, sentiment="error", reason="Missing result"))

    async def _analyze_batch(self, messages: list[Message]) -> list[SentimentResult]:
        """Analyze multiple messages in a single LLM call."""
        if self.classifier._available is None:
            await self.classifier.check_available()

        if not self.classifier._available:
            return [SentimentResult(is_urgent=False, sentiment="unknown", reason="LLM unavailable")] * len(messages)

        # Build message list for prompt
        msg_lines = []
        for i, msg in enumerate(messages, 1):
            msg_lines.append(f"{i}. From {msg.title}: {msg.body[:150]}")
        messages_text = "\n".join(msg_lines)

        prompt = f"""Classify these chat messages. Answer NORMAL unless there is a genuine emergency.

URGENT (extremely rare - genuine emergencies only):
- Someone in physical danger or medical emergency
- "Help", "call 999", "I'm hurt", "accident"
- Explicit "call me NOW it's urgent"

NORMAL (99% of messages - the default):
- Questions, casual chat, sharing links/photos
- Updates like "on my way", "running late"
- Anything that can wait 1 hour

Messages to classify:
{messages_text}

For each message, answer with just the number and NORMAL or URGENT.
Example format:
1. NORMAL
2. NORMAL
3. URGENT

Your answers:"""

        try:
            start_time = time.time()
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.classifier.ollama_url}/api/generate",
                    json={
                        "model": self.classifier.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 256},
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                duration_ms = int((time.time() - start_time) * 1000)
                raw = result.get("response", "").strip()
                log_llm(f"Batch sentiment response ({duration_ms}ms): {raw[:200]}")
                log_llm_query(f"batch_sentiment_{len(messages)}", prompt, raw, duration_ms, self.classifier.model)

                return self._parse_batch_response(raw, len(messages))
        except Exception as e:
            log_llm(f"Batch sentiment error: {e}")
            return [SentimentResult(is_urgent=False, sentiment="error", reason=str(e))] * len(messages)

    def _parse_batch_response(self, response: str, count: int) -> list[SentimentResult]:
        """Parse batched LLM response into individual results."""
        results = []
        lines = response.strip().split("\n")

        # Try to extract NORMAL/URGENT from each line
        for line in lines:
            line_upper = line.upper()
            if "URGENT" in line_upper:
                results.append(SentimentResult(is_urgent=True, sentiment="urgent", reason="URGENT"))
            elif "NORMAL" in line_upper:
                results.append(SentimentResult(is_urgent=False, sentiment="normal", reason="NORMAL"))

        # Pad with NORMAL if we didn't get enough results
        while len(results) < count:
            results.append(SentimentResult(is_urgent=False, sentiment="normal", reason="Default"))

        return results[:count]
