import logging
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

from models import NotificationRequest, NotificationResponse, Message
from rules import RuleEngine, Action
from rate_limiter import RateLimiter
from classifier import LLMClassifier, BatchedSentimentAnalyzer, analyze_feedback_with_ai
from sinks import ConsoleSink, NtfySink, BarkSink, TwilioSink, IMessageSink
import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# Load config
CONFIG_PATH = Path("/app/config.yaml")

# Apps to hide from dashboard (sink echoes)
HIDDEN_APPS = {"bark", "ntfy"}


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    # Initialize sinks from config
    sinks_config = app.state.rules.config.get("sinks", {})
    app.state.sinks = []

    console_conf = sinks_config.get("console", {})
    if console_conf.get("enabled", True):
        app.state.sinks.append(ConsoleSink())

    ntfy_conf = sinks_config.get("ntfy", {})
    if ntfy_conf.get("enabled", False):
        app.state.sinks.append(NtfySink(
            url=ntfy_conf.get("url", "")
        ))

    bark_conf = sinks_config.get("bark", {})
    if bark_conf.get("enabled", False):
        app.state.sinks.append(BarkSink(
            url=bark_conf.get("url", ""),
            device_key=bark_conf.get("device_key", "")
        ))

    twilio_conf = sinks_config.get("twilio", {})
    if twilio_conf.get("enabled", False):
        app.state.sinks.append(TwilioSink(
            account_sid=twilio_conf.get("account_sid", ""),
            auth_token=twilio_conf.get("auth_token", ""),
            from_number=twilio_conf.get("from_number", ""),
            to_number=twilio_conf.get("to_number", ""),
        ))

    imessage_conf = sinks_config.get("imessage", {})
    if imessage_conf.get("enabled", False):
        app.state.sinks.append(IMessageSink(
            gateway_url=imessage_conf.get("gateway_url", "http://host.docker.internal:8095"),
            recipient=imessage_conf.get("recipient", ""),
        ))

    yield
    # Shutdown - nothing to clean up


app = FastAPI(title="Sift", lifespan=lifespan)


@app.post("/notification", response_model=NotificationResponse)
async def receive_notification(req: NotificationRequest):
    """Process incoming notification."""
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


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    db_ok = db.check_db()
    ollama_ok = await app.state.classifier.check_available()

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        db="ok" if db_ok else "error",
        ollama="ok" if ollama_ok else "unavailable",
    )


# Dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: #e0e0e0; }}
        h1 {{ margin: 0 0 20px; font-size: 24px; }}
        .stats {{ display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }}
        .stat {{ background: #2a2a2a; padding: 12px 16px; border-radius: 8px; min-width: 80px; flex: 1; }}
        .stat-value {{ font-size: 24px; font-weight: bold; }}
        .stat-label {{ font-size: 11px; color: #888; text-transform: uppercase; }}
        .stat.sent .stat-value {{ color: #4ade80; }}
        .stat.dropped .stat-value {{ color: #f87171; }}
        .stat.rate_limited .stat-value {{ color: #fbbf24; }}
        .connection {{ background: #2a2a2a; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; }}
        .connection-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
        .connection-dot.connected {{ background: #3b82f6; animation: pulse 2s ease-in-out infinite; }}
        .connection-dot.disconnected {{ background: #f87171; box-shadow: 0 0 8px #f87171; }}
        .connection-dot.unknown {{ background: #fbbf24; }}
        @keyframes pulse {{ 0%, 100% {{ box-shadow: 0 0 4px #3b82f6; }} 50% {{ box-shadow: 0 0 16px #3b82f6, 0 0 24px #3b82f6; }} }}
        .connection-info {{ display: flex; flex-direction: column; }}
        .connection-status {{ font-weight: bold; font-size: 14px; }}
        .connection-detail {{ font-size: 12px; color: #888; }}
        .filters {{ display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }}
        .filters select, .filters input {{ background: #2a2a2a; border: 1px solid #3a3a3a; color: #e0e0e0; padding: 8px 12px; border-radius: 6px; font-size: 14px; }}
        .filters select {{ min-width: 120px; }}
        .filters input {{ flex: 1; min-width: 150px; }}
        .filters select:focus, .filters input:focus {{ outline: none; border-color: #3b82f6; }}
        .app-stats {{ margin-bottom: 20px; }}
        .app-stats table {{ font-size: 14px; width: 100%; border-collapse: collapse; background: #2a2a2a; border-radius: 8px; overflow: hidden; }}
        .app-stats th, .app-stats td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #3a3a3a; }}
        .app-stats th {{ background: #333; font-size: 11px; text-transform: uppercase; color: #888; }}
        h2 {{ font-size: 16px; margin: 20px 0 10px; }}

        /* Desktop table */
        .notif-table {{ width: 100%; border-collapse: collapse; background: #2a2a2a; border-radius: 8px; overflow: hidden; }}
        .notif-table th, .notif-table td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #3a3a3a; }}
        .notif-table th {{ background: #333; font-size: 11px; text-transform: uppercase; color: #888; }}
        .notif-table tr.notif-row {{ cursor: pointer; }}
        .notif-table tr.notif-row:hover {{ background: #333; }}
        .action-sent {{ color: #4ade80; }}
        .action-dropped {{ color: #f87171; }}
        .action-rate_limited {{ color: #fbbf24; }}
        .badge-duplicate {{ background: #7c3aed; color: white; font-size: 10px; padding: 2px 6px; border-radius: 3px; margin-left: 6px; }}
        .truncate {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .body-cell {{ color: #888; }}
        .feedback {{ display: flex; gap: 5px; }}
        .feedback button {{ padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }}
        .feedback .wrong {{ background: #374151; color: #9ca3af; }}
        .feedback .wrong:hover {{ background: #4b5563; color: white; }}
        .feedback .wrong.selected {{ background: #991b1b; color: white; }}

        /* Expanded row */
        .notif-expanded {{ display: none; background: #252525; }}
        .notif-expanded.show {{ display: table-row; }}
        .notif-expanded td {{ padding: 15px; }}
        .notif-detail {{ display: grid; gap: 10px; }}
        .notif-detail-row {{ display: flex; gap: 10px; }}
        .notif-detail-label {{ font-size: 11px; color: #666; text-transform: uppercase; min-width: 60px; }}
        .notif-detail-value {{ font-size: 13px; word-break: break-word; }}

        /* Mobile cards */
        .notif-cards {{ display: none; }}
        .notif-card {{ background: #2a2a2a; border-radius: 8px; padding: 12px; margin-bottom: 10px; cursor: pointer; }}
        .notif-card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .notif-card-app {{ font-weight: bold; font-size: 14px; }}
        .notif-card-time {{ font-size: 12px; color: #888; }}
        .notif-card-title {{ font-size: 14px; margin-bottom: 4px; }}
        .notif-card-body {{ font-size: 13px; color: #888; margin-bottom: 8px; }}
        .notif-card-body.truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .notif-card-body.expanded {{ white-space: normal; word-break: break-word; }}
        .notif-card-footer {{ display: flex; justify-content: space-between; align-items: center; }}
        .notif-card-action {{ font-size: 12px; font-weight: bold; }}
        .notif-card-reason {{ font-size: 11px; color: #888; margin-top: 4px; }}
        .notif-card-reason.truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }}
        .notif-card-reason.expanded {{ white-space: normal; word-break: break-word; max-width: none; }}

        /* Insights panel */
        .insights {{ background: #2a2a2a; border-radius: 8px; padding: 16px; margin-bottom: 20px; }}
        .insights-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .insights-header h3 {{ margin: 0; font-size: 14px; }}
        .insights-stats {{ font-size: 12px; color: #888; }}
        .insights-empty {{ color: #666; font-size: 13px; text-align: center; padding: 20px; }}
        .suggestion {{ background: #333; border-radius: 6px; padding: 12px; margin-bottom: 8px; }}
        .suggestion:last-child {{ margin-bottom: 0; }}
        .suggestion-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .suggestion-type {{ font-size: 11px; text-transform: uppercase; font-weight: bold; padding: 2px 6px; border-radius: 3px; }}
        .suggestion-type.drop {{ background: #991b1b; color: white; }}
        .suggestion-type.send {{ background: #166534; color: white; }}
        .suggestion-app {{ font-size: 12px; color: #888; }}
        .suggestion-pattern {{ font-size: 14px; margin-bottom: 4px; }}
        .suggestion-reason {{ font-size: 12px; color: #888; margin-bottom: 8px; }}
        .suggestion-rule {{ font-family: monospace; font-size: 11px; background: #1a1a1a; padding: 8px; border-radius: 4px; white-space: pre; overflow-x: auto; }}
        .suggestion-actions {{ display: flex; gap: 8px; margin-top: 8px; }}
        .suggestion-copy {{ font-size: 11px; background: #3b82f6; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; }}
        .suggestion-copy:hover {{ background: #2563eb; }}
        .suggestion-dismiss {{ font-size: 11px; background: #4b5563; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; }}
        .suggestion-dismiss:hover {{ background: #6b7280; }}
        .suggestion-add {{ font-size: 11px; background: #166534; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; }}
        .suggestion-add:hover {{ background: #15803d; }}

        /* Rules panel */
        .rules-panel {{ background: #2a2a2a; border-radius: 8px; padding: 16px; margin-bottom: 20px; }}
        .rules-filter {{ margin-bottom: 12px; }}
        .rules-filter select {{ background: #333; border: 1px solid #444; color: #e0e0e0; padding: 6px 10px; border-radius: 4px; }}
        .rule-item {{ display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: #333; border-radius: 6px; margin-bottom: 6px; flex-wrap: wrap; }}
        .rule-app {{ font-weight: bold; min-width: 80px; color: #9ca3af; }}
        .rule-matcher {{ color: #60a5fa; }}
        .rule-value {{ color: #fbbf24; flex: 1; min-width: 150px; word-break: break-all; }}
        .rule-action {{ font-size: 12px; font-weight: bold; padding: 2px 8px; border-radius: 3px; }}
        .rule-action.send {{ background: #166534; color: white; }}
        .rule-action.drop {{ background: #991b1b; color: white; }}
        .rule-action.llm {{ background: #7c3aed; color: white; }}
        .rule-default {{ opacity: 0.6; font-style: italic; }}
        .rule-delete {{ background: #dc2626; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }}
        .rule-delete:hover {{ background: #b91c1c; }}
        .rule-priority {{ font-size: 10px; background: #f97316; color: white; padding: 2px 6px; border-radius: 3px; }}
        .ai-button {{ background: #8b5cf6; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
        .ai-button:hover {{ background: #7c3aed; }}
        .ai-button:disabled {{ background: #4b5563; cursor: not-allowed; }}
        .ai-analysis {{ background: #1a1a1a; border-radius: 6px; padding: 16px; margin-top: 12px; white-space: pre-wrap; font-size: 13px; line-height: 1.5; max-height: 400px; overflow-y: auto; }}
        .ai-analysis code {{ background: #333; padding: 2px 6px; border-radius: 3px; }}
        .ai-analysis pre {{ background: #333; padding: 12px; border-radius: 6px; overflow-x: auto; }}

        @media (max-width: 768px) {{
            body {{ padding: 12px; }}
            .notif-table {{ display: none; }}
            .notif-cards {{ display: block; }}
            .stat {{ padding: 10px 12px; }}
            .stat-value {{ font-size: 20px; }}
            .app-stats {{ display: none; }}
            .insights-header {{ flex-direction: column; gap: 8px; }}
        }}
    </style>
</head>
<body>
    <h1>Sift</h1>

    <div class="connection">
        <div id="conn-dot" class="connection-dot {connection_class}"></div>
        <div class="connection-info">
            <div id="conn-status" class="connection-status">{connection_status}</div>
            <div id="conn-detail" class="connection-detail">{connection_detail}</div>
        </div>
    </div>

    <div class="stats">
        <div class="stat"><div id="stat-total" class="stat-value">{total}</div><div class="stat-label">Total</div></div>
        <div class="stat sent"><div id="stat-sent" class="stat-value">{sent}</div><div class="stat-label">Sent</div></div>
        <div class="stat dropped"><div id="stat-dropped" class="stat-value">{dropped}</div><div class="stat-label">Dropped</div></div>
        <div class="stat rate_limited"><div id="stat-rate-limited" class="stat-value">{rate_limited}</div><div class="stat-label">Rate Lim</div></div>
    </div>

    <h2>By App</h2>
    <div class="app-stats">
        <table>
            <tr><th>App</th><th>Total</th><th>Sent</th><th>Dropped</th></tr>
            <tbody id="app-stats-body">{app_stats_rows}</tbody>
        </table>
    </div>

    <h2>Insights</h2>
    <div class="insights" id="insights-panel">
        <div class="insights-header">
            <h3>Rule Suggestions</h3>
            <div>
                <span class="insights-stats" id="insights-stats"></span>
                <button class="ai-button" id="ai-analyze-btn" onclick="runAiAnalysis()">Analyze with AI</button>
            </div>
        </div>
        <div id="insights-content">
            <div class="insights-empty">Loading insights...</div>
        </div>
        <div id="ai-analysis-container" style="display: none;">
            <div class="ai-analysis" id="ai-analysis-content"></div>
        </div>
    </div>

    <div style="margin-bottom: 20px;">
        <a href="/rules" class="ai-button" style="text-decoration: none;">Manage Rules</a>
    </div>

    <h2>Recent Notifications</h2>
    <div class="filters">
        <select id="filter-app"><option value="">All Apps</option></select>
        <select id="filter-action">
            <option value="">All Actions</option>
            <option value="sent">Sent</option>
            <option value="dropped">Dropped</option>
            <option value="rate_limited">Rate Limited</option>
        </select>
        <input type="text" id="filter-search" placeholder="Search...">
    </div>

    <table class="notif-table">
        <thead><tr><th>Time</th><th>App</th><th>Title</th><th>Body</th><th>Action</th><th>Reason</th><th></th></tr></thead>
        <tbody id="notifications-body">{notification_rows}</tbody>
    </table>

    <div id="notifications-cards" class="notif-cards"></div>

    <script>
        let allNotifications = [];
        let allApps = new Set();

        const truncate = (s, len) => s && s.length > len ? s.slice(0, len) + '…' : (s || '');
        const esc = s => (s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const isDupe = reason => reason && reason.toLowerCase().includes('duplicate');

        async function feedback(id, currentValue, e) {{
            e.stopPropagation();
            // Toggle: if already marked, clear it; otherwise set it
            const newValue = currentValue === 'bad' ? 'clear' : 'bad';
            await fetch(`/feedback/${{id}}?feedback=${{newValue}}`, {{ method: 'POST' }});
            refresh();
        }}

        // Track expanded notifications to preserve state across refreshes
        const expandedRows = new Set();
        const expandedCards = new Set();

        function toggleRow(id) {{
            const row = document.getElementById('expand-' + id);
            row.classList.toggle('show');
            if (row.classList.contains('show')) {{
                expandedRows.add(id);
            }} else {{
                expandedRows.delete(id);
            }}
        }}

        function toggleCard(id) {{
            const card = document.getElementById('card-' + id);
            const body = card.querySelector('.notif-card-body');
            const reason = card.querySelector('.notif-card-reason');
            const isExpanded = body.classList.contains('expanded');
            body.classList.toggle('truncate');
            body.classList.toggle('expanded');
            reason.classList.toggle('truncate');
            reason.classList.toggle('expanded');
            if (!isExpanded) {{
                expandedCards.add(id);
            }} else {{
                expandedCards.delete(id);
            }}
        }}

        function restoreExpandedState() {{
            expandedRows.forEach(id => {{
                const row = document.getElementById('expand-' + id);
                if (row) row.classList.add('show');
            }});
            expandedCards.forEach(id => {{
                const card = document.getElementById('card-' + id);
                if (card) {{
                    const body = card.querySelector('.notif-card-body');
                    const reason = card.querySelector('.notif-card-reason');
                    if (body) {{ body.classList.remove('truncate'); body.classList.add('expanded'); }}
                    if (reason) {{ reason.classList.remove('truncate'); reason.classList.add('expanded'); }}
                }}
            }});
        }}

        function renderNotifications(notifications) {{
            const filtered = notifications.filter(n => {{
                const appFilter = document.getElementById('filter-app').value;
                const actionFilter = document.getElementById('filter-action').value;
                const search = document.getElementById('filter-search').value.toLowerCase();
                if (appFilter && n.app !== appFilter) return false;
                if (actionFilter && n.action !== actionFilter) return false;
                if (search && !`${{n.title}} ${{n.body}} ${{n.reason}}`.toLowerCase().includes(search)) return false;
                return true;
            }});

            // Desktop table with expandable rows
            document.getElementById('notifications-body').innerHTML = filtered
                .map(n => `<tr class="notif-row" onclick="toggleRow(${{n.id}})">
                    <td>${{esc(n.time)}}</td>
                    <td>${{esc(n.app)}}</td>
                    <td class="truncate">${{esc(n.title)}}</td>
                    <td class="truncate body-cell">${{esc(n.body)}}</td>
                    <td class="action-${{n.action}}">${{n.action}}${{isDupe(n.reason) ? '<span class="badge-duplicate">DUPE</span>' : ''}}</td>
                    <td class="truncate body-cell">${{esc(truncate(n.reason, 40))}}</td>
                    <td class="feedback">
                        <button class="wrong ${{n.feedback === 'bad' ? 'selected' : ''}}" onclick="feedback(${{n.id}}, '${{n.feedback || ''}}', event)">${{n.feedback === 'bad' ? '✗' : '?'}}</button>
                    </td>
                </tr>
                <tr id="expand-${{n.id}}" class="notif-expanded">
                    <td colspan="7">
                        <div class="notif-detail">
                            <div class="notif-detail-row"><span class="notif-detail-label">Title</span><span class="notif-detail-value">${{esc(n.title)}}</span></div>
                            <div class="notif-detail-row"><span class="notif-detail-label">Body</span><span class="notif-detail-value">${{esc(n.body)}}</span></div>
                            <div class="notif-detail-row"><span class="notif-detail-label">Reason</span><span class="notif-detail-value">${{esc(n.reason)}}</span></div>
                        </div>
                    </td>
                </tr>`).join('');

            // Mobile cards with expandable content
            document.getElementById('notifications-cards').innerHTML = filtered
                .map(n => `<div id="card-${{n.id}}" class="notif-card" onclick="toggleCard(${{n.id}})">
                    <div class="notif-card-header">
                        <span class="notif-card-app">${{esc(n.app)}}</span>
                        <span class="notif-card-time">${{esc(n.time)}}</span>
                    </div>
                    <div class="notif-card-title">${{esc(n.title)}}</div>
                    <div class="notif-card-body truncate">${{esc(n.body)}}</div>
                    <div class="notif-card-footer">
                        <div>
                            <span class="notif-card-action action-${{n.action}}">${{n.action}}${{isDupe(n.reason) ? '<span class="badge-duplicate">DUPE</span>' : ''}}</span>
                            <div class="notif-card-reason truncate">${{esc(n.reason)}}</div>
                        </div>
                        <div class="feedback">
                            <button class="wrong ${{n.feedback === 'bad' ? 'selected' : ''}}" onclick="feedback(${{n.id}}, '${{n.feedback || ''}}', event)">${{n.feedback === 'bad' ? '✗' : '?'}}</button>
                        </div>
                    </div>
                </div>`).join('');

            // Restore expanded state after re-render
            restoreExpandedState();
        }}

        function updateAppFilter() {{
            const select = document.getElementById('filter-app');
            const current = select.value;
            select.innerHTML = '<option value="">All Apps</option>' +
                [...allApps].sort().map(app => `<option value="${{app}}">${{app}}</option>`).join('');
            select.value = current;
        }}

        async function refresh() {{
            try {{
                const resp = await fetch('/api/dashboard');
                const data = await resp.json();

                // Update connection
                document.getElementById('conn-dot').className = 'connection-dot ' + data.connection.class;
                document.getElementById('conn-status').textContent = data.connection.status;
                document.getElementById('conn-detail').textContent = data.connection.detail;

                // Update stats
                document.getElementById('stat-total').textContent = data.stats.total;
                document.getElementById('stat-sent').textContent = data.stats.sent;
                document.getElementById('stat-dropped').textContent = data.stats.dropped;
                document.getElementById('stat-rate-limited').textContent = data.stats.rate_limited;

                // Update app stats
                document.getElementById('app-stats-body').innerHTML = data.app_stats
                    .map(s => `<tr><td>${{s.app}}</td><td>${{s.total}}</td><td>${{s.sent}}</td><td>${{s.dropped}}</td></tr>`)
                    .join('');

                // Update notifications
                allNotifications = data.notifications;
                data.notifications.forEach(n => allApps.add(n.app));
                updateAppFilter();
                renderNotifications(allNotifications);
            }} catch (e) {{
                console.error('Refresh failed:', e);
            }}
        }}

        // Filter event listeners
        document.getElementById('filter-app').addEventListener('change', () => renderNotifications(allNotifications));
        document.getElementById('filter-action').addEventListener('change', () => renderNotifications(allNotifications));
        document.getElementById('filter-search').addEventListener('input', () => renderNotifications(allNotifications));

        function copyRule(text) {{
            navigator.clipboard.writeText(text);
        }}

        async function dismissSuggestion(app, pattern, type) {{
            await fetch('/api/dismiss-suggestion', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{app, pattern, type}})
            }});
            refreshInsights();
        }}

        async function runAiAnalysis() {{
            const btn = document.getElementById('ai-analyze-btn');
            const container = document.getElementById('ai-analysis-container');
            const content = document.getElementById('ai-analysis-content');

            btn.disabled = true;
            btn.textContent = 'Analyzing...';
            container.style.display = 'block';
            content.innerHTML = 'Running AI analysis on your feedback data...\\n\\nThis may take 30-60 seconds.';

            try {{
                const resp = await fetch('/api/insights/ai');
                const data = await resp.json();

                // Format the analysis with markdown-like rendering
                let html = data.analysis
                    .replace(/```yaml([\\s\\S]*?)```/g, '<pre><code>$1</code></pre>')
                    .replace(/```([\\s\\S]*?)```/g, '<pre><code>$1</code></pre>')
                    .replace(/`([^`]+)`/g, '<code>$1</code>');

                if (data.stats) {{
                    html = `<strong>Feedback analyzed:</strong> ${{data.stats.good_sends + data.stats.bad_sends}} sent, ${{data.stats.good_drops + data.stats.bad_drops}} dropped\\n\\n` + html;
                }}

                content.innerHTML = html;
            }} catch (e) {{
                content.innerHTML = 'Error running AI analysis: ' + e.message;
            }}

            btn.disabled = false;
            btn.textContent = 'Analyze with AI';
        }}

        async function refreshInsights() {{
            try {{
                const resp = await fetch('/api/insights');
                const data = await resp.json();

                const statsEl = document.getElementById('insights-stats');
                statsEl.textContent = `${{data.stats.bad}} flagged incorrect`;

                const contentEl = document.getElementById('insights-content');

                const allItems = [
                    ...data.bad_sends.map(s => ({{...s, type: 'drop', reason: `Sent incorrectly (${{s.count}}x)`, rule: `- sender_contains: "${{s.title}}"\\n  action: drop`}})),
                    ...data.bad_drops.map(s => ({{...s, type: 'send', reason: `Dropped incorrectly (${{s.count}}x)`, rule: `- sender_contains: "${{s.title}}"\\n  action: send`}})),
                    ...data.suggestions.map(s => ({{...s, title: s.pattern}}))
                ];

                if (allItems.length === 0) {{
                    contentEl.innerHTML = '<div class="insights-empty">No suggestions yet. Rate more notifications with 👍/👎 to get rule suggestions.</div>';
                    return;
                }}

                contentEl.innerHTML = allItems.map((s, i) => `
                    <div class="suggestion" data-idx="${{i}}">
                        <div class="suggestion-header">
                            <span class="suggestion-type ${{s.type}}">${{s.type}}</span>
                            <span class="suggestion-app">${{esc(s.app)}}</span>
                        </div>
                        <div class="suggestion-pattern">${{esc(s.title || s.pattern)}}</div>
                        <div class="suggestion-reason">${{esc(s.reason)}}</div>
                        <div class="suggestion-rule">${{esc(s.rule)}}</div>
                        <div class="suggestion-actions">
                            <button class="suggestion-add" data-action="add" data-idx="${{i}}">Add Rule</button>
                            <button class="suggestion-copy" data-action="copy" data-idx="${{i}}">Copy</button>
                            <button class="suggestion-dismiss" data-action="dismiss" data-idx="${{i}}">Dismiss</button>
                        </div>
                    </div>
                `).join('');

                // Store suggestions for button handlers
                window.currentSuggestions = allItems;
            }} catch (e) {{
                console.error('Insights failed:', e);
            }}
        }}

        // Handle suggestion button clicks via event delegation
        document.getElementById('insights-content').addEventListener('click', async (e) => {{
            const btn = e.target.closest('button[data-action]');
            if (!btn) return;

            const idx = parseInt(btn.dataset.idx);
            const s = window.currentSuggestions[idx];
            if (!s) return;

            const action = btn.dataset.action;
            const pattern = s.title || s.pattern;

            if (action === 'add') {{
                await fetch('/api/rules', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        app: s.app,
                        matcher: 'sender_contains',
                        value: pattern,
                        action: s.type
                    }})
                }});
                await fetch('/api/dismiss-suggestion', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{app: s.app, pattern: pattern, type: s.type}})
                }});
                refreshInsights();
            }} else if (action === 'copy') {{
                navigator.clipboard.writeText(s.rule);
            }} else if (action === 'dismiss') {{
                await fetch('/api/dismiss-suggestion', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{app: s.app, pattern: pattern, type: s.type}})
                }});
                refreshInsights();
            }}
        }});

        refresh();
        refreshInsights();
        setInterval(refresh, 5000);
        setInterval(refreshInsights, 30000);
    </script>
</body>
</html>
"""


import os

PI_HEALTH_URL = os.getenv("PI_HEALTH_URL", "")


async def get_pi_health() -> dict:
    """Fetch health status from Pi's ancs-bridge."""
    if not PI_HEALTH_URL:
        return {"status": "disabled", "phone_connected": None, "last_activity_ago": None}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(PI_HEALTH_URL)
            # Parse JSON even on 503 - it contains useful error details
            return resp.json()
    except Exception as e:
        return {"status": "unreachable", "phone_connected": None, "last_activity_ago": None, "error": str(e)}


def format_time_ago(seconds: int) -> str:
    """Format seconds into human-readable time ago."""
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    else:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m ago"


def get_last_notification_ago() -> str | None:
    """Get human-readable time since last visible notification."""
    last_time = db.get_last_notification_time(exclude_apps=HIDDEN_APPS)
    if not last_time:
        return None
    try:
        # Parse the SQLite timestamp
        dt = datetime.fromisoformat(last_time.replace(" ", "T"))
        seconds_ago = int((datetime.utcnow() - dt).total_seconds())
        return format_time_ago(max(0, seconds_ago))
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Dashboard showing recent notifications and stats."""
    stats = db.get_stats()
    app_stats = [s for s in db.get_stats_by_app() if s["app"] not in HIDDEN_APPS]
    notifications = [n for n in db.get_recent_notifications(100) if n["app"] not in HIDDEN_APPS]
    pi_health = await get_pi_health()

    # Connection status
    last_notif_ago = get_last_notification_ago()
    active_iphone = pi_health.get("active_iphone")
    configured_iphone = pi_health.get("configured_iphone")

    # Format iPhone info for display
    iphone_info = ""
    if configured_iphone:
        iphone_info = f"Configured: {configured_iphone}"
    elif active_iphone:
        iphone_info = f"Detected: {active_iphone}"

    if pi_health.get("phone_connected") is True:
        connection_class = "connected"
        battery = pi_health.get("battery")
        if battery is not None:
            connection_status = f"iPhone Connected • {battery}%"
        else:
            connection_status = "iPhone Connected"
        if last_notif_ago:
            connection_detail = f"Last notification: {last_notif_ago}"
            if iphone_info:
                connection_detail += f" • {iphone_info}"
        else:
            connection_detail = iphone_info or "No notifications yet"
    elif pi_health.get("phone_connected") is False:
        connection_class = "disconnected"
        connection_status = "iPhone Disconnected"
        reason = pi_health.get("reason", "Waiting for Bluetooth connection")
        disconnected_for = pi_health.get("disconnected_for")
        if disconnected_for:
            connection_detail = f"{reason} • Disconnected for {format_time_ago(disconnected_for)}"
        else:
            connection_detail = reason
        if iphone_info:
            connection_detail += f" • {iphone_info}"
    elif pi_health.get("status") == "unreachable":
        connection_class = "unknown"
        connection_status = "Pi Unreachable"
        connection_detail = pi_health.get("error", "Cannot reach ancs-bridge on Pi")
    else:
        connection_class = "unknown"
        connection_status = "Pi Unreachable"
        connection_detail = "Cannot reach ancs-bridge on Pi"

    app_stats_rows = "".join(
        f"<tr><td>{s['app']}</td><td>{s['total']}</td><td>{s['sent']}</td><td>{s['dropped']}</td></tr>"
        for s in app_stats
    )

    notification_rows = "".join(
        f"""<tr>
            <td>{n['created_at'][:16] if n['created_at'] else ''}</td>
            <td>{n['app']}</td>
            <td>{n['title'][:40]}</td>
            <td class="body">{n['body'][:50] if n['body'] else ''}</td>
            <td class="action-{n['action']}">{n['action']}</td>
            <td>{(n['reason'] or '')[:50]}</td>
            <td class="feedback">
                <button class="good {'selected' if n.get('feedback') == 'good' else ''}" onclick="feedback({n['id']}, 'good')">👍</button>
                <button class="bad {'selected' if n.get('feedback') == 'bad' else ''}" onclick="feedback({n['id']}, 'bad')">👎</button>
            </td>
        </tr>"""
        for n in notifications
    )

    html = DASHBOARD_HTML.format(
        total=stats['total'],
        sent=stats['sent'],
        dropped=stats['dropped'],
        rate_limited=stats['rate_limited'],
        connection_class=connection_class,
        connection_status=connection_status,
        connection_detail=connection_detail,
        app_stats_rows=app_stats_rows,
        notification_rows=notification_rows,
    )
    return HTMLResponse(content=html)


RULES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Rules - Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: #e0e0e0; }
        h1 { margin: 0 0 20px; font-size: 24px; display: flex; align-items: center; gap: 15px; }
        a.back { color: #60a5fa; text-decoration: none; font-size: 14px; }
        a.back:hover { text-decoration: underline; }
        .rules-filter { margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap; }
        .rules-filter select { background: #2a2a2a; border: 1px solid #3a3a3a; color: #e0e0e0; padding: 8px 12px; border-radius: 6px; }
        .rule-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: #2a2a2a; border-radius: 6px; margin-bottom: 8px; flex-wrap: wrap; }
        .rule-app { font-weight: bold; min-width: 100px; color: #9ca3af; }
        .rule-matcher { color: #60a5fa; min-width: 120px; }
        .rule-value { color: #fbbf24; flex: 1; min-width: 150px; word-break: break-all; }
        .rule-action { font-size: 12px; font-weight: bold; padding: 3px 10px; border-radius: 4px; }
        .rule-action.send { background: #166534; color: white; }
        .rule-action.drop { background: #991b1b; color: white; }
        .rule-action.llm { background: #7c3aed; color: white; }
        .rule-default { opacity: 0.8; }
        .default-action-select { background: #333; border: 1px solid #555; color: #e0e0e0; padding: 4px 8px; border-radius: 4px; cursor: pointer; }
        .rule-global { background: #1e3a5f; border: 1px solid #3b82f6; }
        .rule-global .rule-app { color: #60a5fa; }
        .rule-delete { background: #dc2626; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .rule-delete:hover { background: #b91c1c; }
        .rule-priority { font-size: 10px; background: #f97316; color: white; padding: 2px 6px; border-radius: 3px; }
        .rule-prompt { cursor: help; font-size: 14px; }
        .empty { color: #666; text-align: center; padding: 40px; }

        /* Add rule form */
        .add-rule-form { background: #2a2a2a; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
        .add-rule-form h3 { margin: 0 0 12px; font-size: 14px; }
        .form-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
        .form-row input, .form-row select { background: #333; border: 1px solid #444; color: #e0e0e0; padding: 8px 12px; border-radius: 4px; font-size: 14px; }
        .form-row input { flex: 1; min-width: 150px; }
        .form-row select { min-width: 120px; }
        .form-row button { background: #166534; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .form-row button:hover { background: #15803d; }
        .form-error { color: #f87171; font-size: 12px; margin-top: 5px; }

        @media (max-width: 768px) {
            .rule-item { padding: 12px; }
            .rule-app { min-width: 70px; font-size: 13px; }
            .rule-matcher { min-width: 100px; font-size: 13px; }
        }
    </style>
</head>
<body>
    <h1><a href="/" class="back">← Dashboard</a> Rules</h1>

    <div class="add-rule-form">
        <h3>Add Rule</h3>
        <div class="form-row">
            <select id="new-app" onchange="toggleCustomApp()">
                <option value="">Select app...</option>
            </select>
            <input type="text" id="new-app-custom" placeholder="Custom app name" style="display: none;">
        </div>
        <div class="form-row">
            <select id="new-matcher">
                <option value="sender_contains">sender contains</option>
                <option value="sender_not_contains">sender not contains</option>
                <option value="body_contains">body contains</option>
                <option value="body_not_contains">body not contains</option>
                <option value="contains">contains (anywhere)</option>
                <option value="sender_regex">sender regex</option>
                <option value="body_regex">body regex</option>
                <option value="regex">regex (anywhere)</option>
            </select>
            <input type="text" id="new-value" placeholder="Match text">
        </div>
        <div class="form-row">
            <select id="new-action" onchange="togglePrompt()">
                <option value="send">send</option>
                <option value="drop">drop</option>
                <option value="llm">llm</option>
            </select>
            <select id="new-priority">
                <option value="">Priority: default</option>
                <option value="high">Priority: high</option>
                <option value="critical">Priority: critical</option>
            </select>
            <button onclick="addRule()">Add Rule</button>
        </div>
        <div class="form-row" id="prompt-row" style="display: none;">
            <select id="new-prompt-type" onchange="toggleCustomPrompt()">
                <option value="default">Default LLM prompt</option>
                <option value="custom">Custom prompt</option>
            </select>
            <input type="text" id="new-prompt" placeholder="Custom prompt - must ask for SEND or DROP response" style="display: none;">
        </div>
        <div id="form-error" class="form-error"></div>
    </div>

    <div class="rules-filter">
        <select id="rules-app-filter"><option value="">All Apps</option></select>
    </div>

    <div id="rules-content">Loading...</div>

    <script>
        const esc = s => (s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        let allRules = [];

        async function refreshRules() {
            try {
                const resp = await fetch('/api/rules');
                const data = await resp.json();
                allRules = data.rules;

                const apps = [...new Set(allRules.map(r => r.app))].sort();

                // Populate filter dropdown
                const filterEl = document.getElementById('rules-app-filter');
                const current = filterEl.value;
                filterEl.innerHTML = '<option value="">All Apps</option>' +
                    apps.map(a => `<option value="${a}">${a}</option>`).join('');
                filterEl.value = current;

                // Populate add-rule app dropdown
                const appSelect = document.getElementById('new-app');
                const currentApp = appSelect.value;
                appSelect.innerHTML = '<option value="">Select app...</option>' +
                    '<option value="__global__">⭐ Global (all apps)</option>' +
                    apps.filter(a => a !== '__global__').map(a => `<option value="${a}">${a}</option>`).join('') +
                    '<option value="__other__">Other (custom)...</option>';
                appSelect.value = currentApp;

                renderRules();
            } catch (e) {
                console.error('Rules refresh failed:', e);
            }
        }

        function toggleCustomApp() {
            const appSelect = document.getElementById('new-app');
            const customInput = document.getElementById('new-app-custom');
            if (appSelect.value === '__other__') {
                customInput.style.display = 'block';
                customInput.focus();
            } else {
                customInput.style.display = 'none';
                customInput.value = '';
            }
        }

        function renderRules() {
            const filter = document.getElementById('rules-app-filter').value;
            const filtered = filter ? allRules.filter(r => r.app === filter) : allRules;

            const contentEl = document.getElementById('rules-content');
            if (filtered.length === 0) {
                contentEl.innerHTML = '<div class="empty">No rules configured.</div>';
                return;
            }

            contentEl.innerHTML = filtered.map(r => {
                const isGlobal = r.app === '__global__';
                const appDisplay = isGlobal ? '⭐ Global' : esc(r.app);
                const itemClass = isGlobal ? 'rule-item rule-global' : 'rule-item';

                if (r.type === 'default') {
                    return `<div class="rule-item rule-default" data-app="${esc(r.app)}">
                        <span class="rule-app">${esc(r.app)}</span>
                        <span class="rule-matcher">default</span>
                        <span class="rule-value"></span>
                        <select class="default-action-select" data-app="${esc(r.app)}" onchange="changeDefault('${esc(r.app)}', this.value)">
                            <option value="drop" ${r.action === 'drop' ? 'selected' : ''}>drop</option>
                            <option value="send" ${r.action === 'send' ? 'selected' : ''}>send</option>
                        </select>
                    </div>`;
                }
                return `<div class="${itemClass}" data-app="${esc(r.app)}" data-index="${r.index}">
                    <span class="rule-app">${appDisplay}</span>
                    <span class="rule-matcher">${r.matcher.replace(/_/g, ' ')}</span>
                    <span class="rule-value">"${esc(r.value)}"</span>
                    <span class="rule-action ${r.action}">${r.action}</span>
                    ${r.priority ? `<span class="rule-priority">${r.priority}</span>` : ''}
                    ${r.prompt ? `<span class="rule-prompt" title="${esc(r.prompt)}">📝</span>` : ''}
                    <button class="rule-delete">Delete</button>
                </div>`;
            }).join('');
        }

        async function changeDefault(app, action) {
            await fetch('/api/rules/default', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({app, action})
            });
            refreshRules();
        }

        function togglePrompt() {
            const action = document.getElementById('new-action').value;
            document.getElementById('prompt-row').style.display = action === 'llm' ? 'flex' : 'none';
        }

        function toggleCustomPrompt() {
            const type = document.getElementById('new-prompt-type').value;
            document.getElementById('new-prompt').style.display = type === 'custom' ? 'block' : 'none';
        }

        async function addRule() {
            const appSelect = document.getElementById('new-app').value;
            const appCustom = document.getElementById('new-app-custom').value.trim().toLowerCase();
            const app = appSelect === '__other__' ? appCustom : appSelect;
            const matcher = document.getElementById('new-matcher').value;
            const value = document.getElementById('new-value').value.trim();
            const action = document.getElementById('new-action').value;
            const priority = document.getElementById('new-priority').value;
            const errorEl = document.getElementById('form-error');

            if (!app || !value) {
                errorEl.textContent = 'App and match text are required';
                return;
            }

            errorEl.textContent = '';

            const body = {app, matcher, value, action};

            // Add priority if set
            if (priority) {
                body.priority = priority;
            }

            // Add prompt if LLM action with custom prompt
            if (action === 'llm') {
                const promptType = document.getElementById('new-prompt-type').value;
                if (promptType === 'custom') {
                    const prompt = document.getElementById('new-prompt').value.trim();
                    if (prompt) body.prompt = prompt;
                }
            }

            const resp = await fetch('/api/rules', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });

            if (resp.ok) {
                document.getElementById('new-app').value = '';
                document.getElementById('new-app-custom').value = '';
                document.getElementById('new-app-custom').style.display = 'none';
                document.getElementById('new-value').value = '';
                document.getElementById('new-prompt').value = '';
                document.getElementById('new-action').value = 'send';
                document.getElementById('new-priority').value = '';
                document.getElementById('new-prompt-type').value = 'default';
                togglePrompt();
                refreshRules();
            } else {
                const data = await resp.json();
                errorEl.textContent = data.error || 'Failed to add rule';
            }
        }

        document.getElementById('rules-content').addEventListener('click', async (e) => {
            if (!e.target.classList.contains('rule-delete')) return;
            if (!confirm('Delete this rule?')) return;

            const item = e.target.closest('.rule-item');
            const app = item.dataset.app;
            const index = parseInt(item.dataset.index);

            await fetch('/api/rules', {
                method: 'DELETE',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({app, index})
            });
            refreshRules();
        });

        document.getElementById('rules-app-filter').addEventListener('change', renderRules);

        refreshRules();
    </script>
</body>
</html>
"""


@app.get("/rules", response_class=HTMLResponse)
async def rules_page():
    """Rules management page."""
    return HTMLResponse(content=RULES_HTML)


@app.get("/api/dashboard")
async def dashboard_api():
    """JSON API for dashboard data."""
    stats = db.get_stats()
    app_stats = [s for s in db.get_stats_by_app() if s["app"] not in HIDDEN_APPS]
    notifications = [n for n in db.get_recent_notifications(100) if n["app"] not in HIDDEN_APPS]
    pi_health = await get_pi_health()

    # Connection status
    last_notif_ago = get_last_notification_ago()
    active_iphone = pi_health.get("active_iphone")
    configured_iphone = pi_health.get("configured_iphone")

    # Format iPhone info for display
    iphone_info = ""
    if configured_iphone:
        iphone_info = f"Configured: {configured_iphone}"
    elif active_iphone:
        iphone_info = f"Detected: {active_iphone}"

    battery = pi_health.get("battery")
    if pi_health.get("phone_connected") is True:
        connection_class = "connected"
        if battery is not None:
            connection_status = f"iPhone Connected • {battery}%"
        else:
            connection_status = "iPhone Connected"
        if last_notif_ago:
            connection_detail = f"Last notification: {last_notif_ago}"
            if iphone_info:
                connection_detail += f" • {iphone_info}"
        else:
            connection_detail = iphone_info or "No notifications yet"
    elif pi_health.get("phone_connected") is False:
        connection_class = "disconnected"
        connection_status = "iPhone Disconnected"
        reason = pi_health.get("reason", "Waiting for Bluetooth connection")
        disconnected_for = pi_health.get("disconnected_for")
        if disconnected_for:
            connection_detail = f"{reason} • Disconnected for {format_time_ago(disconnected_for)}"
        else:
            connection_detail = reason
        if iphone_info:
            connection_detail += f" • {iphone_info}"
    elif pi_health.get("status") == "unreachable":
        connection_class = "unknown"
        connection_status = "Pi Unreachable"
        connection_detail = pi_health.get("error", "Cannot reach ancs-bridge on Pi")
    else:
        connection_class = "unknown"
        connection_status = "Pi Unreachable"
        connection_detail = "Cannot reach ancs-bridge on Pi"

    return {
        "connection": {
            "class": connection_class,
            "status": connection_status,
            "detail": connection_detail,
            "active_iphone": active_iphone,
            "configured_iphone": configured_iphone,
            "battery": battery,
        },
        "stats": stats,
        "app_stats": app_stats,
        "notifications": [
            {
                "id": n["id"],
                "time": n["created_at"][:16] if n["created_at"] else "",
                "app": n["app"],
                "title": n["title"],
                "body": n["body"] or "",
                "action": n["action"],
                "reason": n["reason"] or "",
                "feedback": n.get("feedback"),
            }
            for n in notifications
        ],
    }


@app.get("/api/insights")
async def insights_api():
    """Get feedback-based rule suggestions."""
    return db.get_feedback_insights()


@app.get("/api/insights/ai")
async def insights_ai_api():
    """Get AI-powered feedback analysis."""
    feedback_data = db.get_feedback_data_for_ai()
    return await analyze_feedback_with_ai(feedback_data)


@app.post("/feedback/{notification_id}")
async def set_feedback(notification_id: int, feedback: str):
    """Set or clear feedback for a notification."""
    if feedback == "clear":
        db.clear_feedback(notification_id)
    elif feedback == "bad":
        db.set_feedback(notification_id, feedback)
    else:
        return {"error": "Invalid feedback"}
    return {"status": "ok"}


@app.post("/api/dismiss-suggestion")
async def dismiss_suggestion(request: Request):
    """Dismiss a suggestion so it won't appear again."""
    data = await request.json()
    app_name = data.get("app", "")
    pattern = data.get("pattern", "")
    suggestion_type = data.get("type", "")
    if not all([app_name, pattern, suggestion_type]):
        return {"error": "Missing app, pattern, or type"}
    db.dismiss_suggestion(app_name, pattern, suggestion_type)
    return {"status": "ok"}


MATCHERS = [
    "sender_contains", "sender_not_contains",
    "body_contains", "body_not_contains",
    "contains", "channel_contains",
    "sender_regex", "body_regex", "regex"
]


@app.get("/api/rules")
async def get_rules():
    """Get all rules from config."""
    rules_list = []

    # Global rules first
    for i, rule in enumerate(app.state.rules.global_rules):
        action = rule.get("action", "send")
        for matcher in MATCHERS:
            if matcher in rule:
                rules_list.append({
                    "app": "__global__",
                    "type": "global",
                    "index": i,
                    "action": action,
                    "matcher": matcher,
                    "value": rule[matcher],
                    "priority": rule.get("priority"),
                    "prompt": rule.get("prompt"),
                })
                break

    # App-specific rules
    for app_name, app_config in app.state.rules.apps.items():
        default_action = app_config.get("default", "drop")
        rules_list.append({
            "app": app_name,
            "type": "default",
            "action": default_action,
            "matcher": None,
            "value": None,
        })
        for i, rule in enumerate(app_config.get("rules", [])):
            action = rule.get("action", "send")
            for matcher in MATCHERS:
                if matcher in rule:
                    rules_list.append({
                        "app": app_name,
                        "type": "rule",
                        "index": i,
                        "action": action,
                        "matcher": matcher,
                        "value": rule[matcher],
                        "priority": rule.get("priority"),
                        "prompt": rule.get("prompt"),
                    })
                    break

    return {
        "rules": rules_list,
        "unknown_apps": app.state.rules.global_config.get("unknown_apps", "drop"),
        "matchers": MATCHERS
    }


@app.post("/api/rules")
async def add_rule(request: Request):
    """Add a new rule to config."""
    import yaml
    data = await request.json()
    app_name = data.get("app", "").lower()
    matcher = data.get("matcher", "")
    value = data.get("value", "")
    action = data.get("action", "send")
    priority = data.get("priority")
    prompt = data.get("prompt")

    if not all([matcher, value, action]):
        return {"error": "Missing required fields"}

    if not app_name and app_name != "__global__":
        return {"error": "App is required"}

    # Read current config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    # Build the new rule
    new_rule = {matcher: value, "action": action}
    if priority:
        new_rule["priority"] = priority
    if prompt:
        new_rule["prompt"] = prompt

    if app_name == "__global__":
        # Add to global rules
        if "global" not in config:
            config["global"] = {}
        if "rules" not in config["global"]:
            config["global"]["rules"] = []
        config["global"]["rules"].append(new_rule)
    else:
        # Add to app-specific rules
        if "apps" not in config:
            config["apps"] = {}
        if app_name not in config["apps"]:
            config["apps"][app_name] = {"default": "drop", "rules": []}
        if "rules" not in config["apps"][app_name]:
            config["apps"][app_name]["rules"] = []
        config["apps"][app_name]["rules"].append(new_rule)

    # Write config
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Reload rules
    app.state.rules = RuleEngine(CONFIG_PATH)

    return {"status": "ok"}


@app.delete("/api/rules")
async def delete_rule(request: Request):
    """Delete a rule from config."""
    import yaml
    data = await request.json()
    app_name = data.get("app", "").lower()
    index = data.get("index")

    if not app_name or index is None:
        return {"error": "Missing app or index"}

    # Read current config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    if app_name == "__global__":
        # Delete global rule
        if "global" not in config or "rules" not in config["global"]:
            return {"error": "No global rules found"}
        rules = config["global"]["rules"]
        if index < 0 or index >= len(rules):
            return {"error": f"Rule index {index} out of range"}
        rules.pop(index)
    else:
        # Delete app-specific rule
        if "apps" not in config or app_name not in config["apps"]:
            return {"error": f"App '{app_name}' not found"}
        rules = config["apps"][app_name].get("rules", [])
        if index < 0 or index >= len(rules):
            return {"error": f"Rule index {index} out of range"}
        rules.pop(index)

    # Write config
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Reload rules
    app.state.rules = RuleEngine(CONFIG_PATH)

    return {"status": "ok"}


@app.post("/api/rules/default")
async def set_default_action(request: Request):
    """Set default action for an app."""
    import yaml
    data = await request.json()
    app_name = data.get("app", "").lower()
    action = data.get("action", "")

    if not app_name or action not in ["send", "drop"]:
        return {"error": "Invalid app or action"}

    # Read current config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    # Ensure apps section exists
    if "apps" not in config:
        config["apps"] = {}

    # Ensure app exists
    if app_name not in config["apps"]:
        config["apps"][app_name] = {"default": action, "rules": []}
    else:
        config["apps"][app_name]["default"] = action

    # Write config
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Reload rules
    app.state.rules = RuleEngine(CONFIG_PATH)

    return {"status": "ok"}
