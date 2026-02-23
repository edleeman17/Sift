"""Sift - iOS Notification Forwarder Processor."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from classifier import LLMClassifier, BatchedSentimentAnalyzer
from rate_limiter import RateLimiter
from rules import RuleEngine
from sinks import load_sinks_from_config
from routes import include_all_routes
import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Load config from environment
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/app/config.yaml"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize services on startup."""
    # Startup
    db.init_db()
    db.migrate_db()
    app.state.rules = RuleEngine(CONFIG_PATH)
    app.state.rate_limiter = RateLimiter(
        max_per_hour=app.state.rules.global_config.get("rate_limit", {}).get("max_per_hour", 20),
        cooldown_seconds=app.state.rules.global_config.get("rate_limit", {}).get("cooldown_seconds", 60),
        app_dedup_hours=app.state.rules.global_config.get("rate_limit", {}).get("app_dedup_hours", {}),
        exempt_apps=app.state.rules.global_config.get("rate_limit", {}).get("exempt_apps", []),
        no_cooldown_apps=app.state.rules.global_config.get("rate_limit", {}).get("no_cooldown_apps", []),
    )
    app.state.classifier = LLMClassifier()
    sentiment_config = app.state.rules.global_config.get("sentiment_detection", {})
    app.state.sentiment_analyzer = BatchedSentimentAnalyzer(
        classifier=app.state.classifier,
        batch_window=sentiment_config.get("batch_window_seconds", 60),
        max_batch_size=sentiment_config.get("max_batch_size", 30),
    )

    # Initialize sinks from config using the registry
    sinks_config = app.state.rules.config.get("sinks", {})
    app.state.sinks = load_sinks_from_config(sinks_config)

    yield
    # Shutdown - nothing to clean up


app = FastAPI(title="Sift", lifespan=lifespan)

# Include all route modules
include_all_routes(app)
