"""Core notification processing routes."""

import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel

from models import NotificationRequest, NotificationResponse, Message
from rules import Action
import db

log = logging.getLogger(__name__)

router = APIRouter(tags=["notification"])


@router.post("/notification", response_model=NotificationResponse)
async def receive_notification(req: NotificationRequest, request: Request):
    """Process incoming notification."""
    app = request.app
    msg = Message.from_request(req)

    # Log to DB first
    notification_id = db.log_notification(msg)

    # Rule evaluation first (drop early before rate limiting)
    rule_result = app.state.rules.evaluate(msg)

    if rule_result.action == Action.DROP:
        # Check sentiment before dropping - urgent messages get through
        # Skip group chats (WhatsApp uses ~ prefix, others use "Group" or commas)
        is_group_chat = "~" in msg.title or "Group" in msg.title or ", " in msg.title
        sentiment_config = app.state.rules.global_config.get("sentiment_detection", {})
        if sentiment_config.get("enabled", False) and not is_group_chat:
            allowed_apps = sentiment_config.get("apps", [])
            if not allowed_apps or msg.app in allowed_apps:
                sentiment = await app.state.sentiment_analyzer.analyze_sentiment(msg)
                if sentiment.is_urgent:
                    log.info(f"[URGENT] {msg.app}/{msg.title}: sentiment override - {sentiment.reason}")
                    rule_result.action = Action.SEND
                    rule_result.reason = f"sentiment: {sentiment.reason}"

        if rule_result.action == Action.DROP:
            log.info(f"[DROPPED] {msg.app}/{msg.title}: {rule_result.reason}")
            db.update_notification(notification_id, "dropped", rule_result.reason)
            return NotificationResponse(status="dropped", reason=rule_result.reason)

    # Rate limit check (only for non-dropped notifications)
    rate_result = app.state.rate_limiter.check(msg)
    if not rate_result.allowed:
        log.info(f"[RATE_LIMITED] {msg.app}/{msg.title}: {rate_result.reason}")
        db.update_notification(notification_id, "rate_limited", rate_result.reason)
        return NotificationResponse(status="rate_limited", reason=rate_result.reason)

    if rule_result.action == Action.LLM:
        # Run through classifier (with optional custom prompt from rule)
        classification = await app.state.classifier.classify(msg, custom_prompt=rule_result.prompt)
        if not classification.should_send:
            log.info(f"[DROPPED] {msg.app}/{msg.title}: LLM: {classification.reason}")
            db.update_notification(notification_id, "dropped", f"LLM: {classification.reason}")
            return NotificationResponse(status="dropped", reason=f"LLM: {classification.reason}")
        rule_result.reason = f"LLM: {classification.reason}"

    # Set priority from rule result
    msg.priority = rule_result.priority

    # Send to all enabled sinks
    sent_to = []
    for sink in app.state.sinks:
        if sink.is_enabled():
            success = await sink.send(msg)
            if success:
                sent_to.append(sink.name)

    reason = f"{rule_result.reason} -> sent to: {', '.join(sent_to)}"
    log.info(f"[SENT] {msg.app}/{msg.title}: {reason}")
    db.update_notification(notification_id, "sent", reason)
    return NotificationResponse(status="sent", reason=reason)


class HealthResponse(BaseModel):
    status: str
    db: str
    ollama: str


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    """Health check endpoint."""
    app = request.app
    db_ok = db.check_db()
    ollama_ok = await app.state.classifier.check_available()

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        db="ok" if db_ok else "error",
        ollama="ok" if ollama_ok else "unavailable"
    )
