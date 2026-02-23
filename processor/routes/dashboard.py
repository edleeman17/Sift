"""Dashboard routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from classifier import analyze_feedback_with_ai
from services.pi_health import get_pi_health, format_time_ago, get_last_notification_ago
from templates.dashboard import DASHBOARD_HTML
import db

router = APIRouter(tags=["dashboard"])

# Apps to hide from dashboard (sink echoes)
HIDDEN_APPS = {"bark", "ntfy"}


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Dashboard showing recent notifications and stats."""
    stats = db.get_stats()
    app_stats = [s for s in db.get_stats_by_app() if s["app"] not in HIDDEN_APPS]
    notifications = [n for n in db.get_recent_notifications(100) if n["app"] not in HIDDEN_APPS]
    pi_health = await get_pi_health()

    # Connection status
    last_notif_ago = get_last_notification_ago(db, HIDDEN_APPS)
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


@router.get("/api/dashboard")
async def dashboard_api():
    """JSON API for dashboard data."""
    stats = db.get_stats()
    app_stats = [s for s in db.get_stats_by_app() if s["app"] not in HIDDEN_APPS]
    notifications = [n for n in db.get_recent_notifications(100) if n["app"] not in HIDDEN_APPS]
    pi_health = await get_pi_health()

    # Connection status
    last_notif_ago = get_last_notification_ago(db, HIDDEN_APPS)
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


@router.get("/api/insights")
async def insights_api():
    """Get feedback-based rule suggestions."""
    return db.get_feedback_insights()


@router.get("/api/insights/ai")
async def insights_ai_api():
    """Get AI-powered feedback analysis."""
    feedback_data = db.get_feedback_data_for_ai()
    return await analyze_feedback_with_ai(feedback_data)


@router.post("/feedback/{notification_id}")
async def set_feedback(notification_id: int, feedback: str):
    """Set or clear feedback for a notification."""
    if feedback == "clear":
        db.clear_feedback(notification_id)
    elif feedback == "bad":
        db.set_feedback(notification_id, feedback)
    else:
        return {"error": "Invalid feedback"}
    return {"status": "ok"}


@router.post("/api/dismiss-suggestion")
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
