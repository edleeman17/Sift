"""System status routes."""

import os
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services.pi_health import get_pi_health
from templates.status import STATUS_HTML
import db

router = APIRouter(tags=["status"])

# Apps to hide from dashboard (sink echoes)
HIDDEN_APPS = {"bark", "ntfy"}


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """System status page."""
    return HTMLResponse(content=STATUS_HTML)


@router.get("/api/status")
async def status_api(request: Request):
    """JSON API for system status data."""
    app = request.app

    # Core services
    core_services = []

    # Processor (always healthy if we're responding)
    core_services.append({
        "id": "processor",
        "name": "Notification Processor",
        "status": "Healthy",
        "detail": "FastAPI server running",
        "checks": {
            "uptime": "OK",
            "rules_loaded": len(app.state.rules.config.get("apps", {})),
        }
    })

    # Database
    try:
        stats = db.get_stats()
        db_status = "Healthy"
        db_detail = f"{stats.get('total', 0)} notifications logged"
    except Exception as e:
        db_status = "Unhealthy"
        db_detail = str(e)[:50]
    core_services.append({
        "id": "database",
        "name": "SQLite Database",
        "status": db_status,
        "detail": db_detail,
    })

    # External services
    external_services = []

    # Ollama
    ollama_url = os.getenv("OLLAMA_URL", "")
    if ollama_url:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{ollama_url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    model_names = [m.get("name", "?") for m in models[:3]]
                    external_services.append({
                        "id": "ollama",
                        "name": "Ollama LLM",
                        "status": "Healthy",
                        "detail": f"Models: {', '.join(model_names)}",
                        "checks": {"models_available": len(models)}
                    })
                else:
                    external_services.append({
                        "id": "ollama",
                        "name": "Ollama LLM",
                        "status": "Unhealthy",
                        "detail": f"HTTP {resp.status_code}",
                    })
        except Exception as e:
            external_services.append({
                "id": "ollama",
                "name": "Ollama LLM",
                "status": "Unhealthy",
                "detail": str(e)[:50],
            })
    else:
        external_services.append({
            "id": "ollama",
            "name": "Ollama LLM",
            "status": "Disabled",
            "detail": "OLLAMA_URL not set",
        })

    # Pi/ancs-bridge
    pi_health = await get_pi_health()
    if pi_health.get("status") == "disabled":
        external_services.append({
            "id": "pi",
            "name": "Raspberry Pi (ancs-bridge)",
            "status": "Disabled",
            "detail": "PI_HEALTH_URL not set",
        })
    elif pi_health.get("status") == "unreachable":
        external_services.append({
            "id": "pi",
            "name": "Raspberry Pi (ancs-bridge)",
            "status": "Unhealthy",
            "detail": pi_health.get("error", "Unreachable")[:50],
        })
    else:
        connected = pi_health.get("phone_connected", False)
        battery = pi_health.get("battery")
        last_activity = pi_health.get("last_activity_ago")
        checks = {"phone_connected": "Yes" if connected else "No"}
        if battery is not None:
            checks["battery"] = f"{battery}%"
        if last_activity:
            checks["last_activity"] = f"{last_activity}s ago"
        external_services.append({
            "id": "pi",
            "name": "Raspberry Pi (ancs-bridge)",
            "status": "Healthy" if connected else "Degraded",
            "detail": "iPhone connected" if connected else "iPhone not connected",
            "checks": checks,
        })

    # iMessage Gateway
    imessage_url = os.getenv("IMESSAGE_GATEWAY_URL", "")
    if imessage_url:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{imessage_url}/health")
                if resp.status_code == 200:
                    external_services.append({
                        "id": "imessage",
                        "name": "iMessage Gateway",
                        "status": "Healthy",
                        "detail": "macOS Messages.app bridge running",
                    })
                else:
                    external_services.append({
                        "id": "imessage",
                        "name": "iMessage Gateway",
                        "status": "Unhealthy",
                        "detail": f"HTTP {resp.status_code}",
                    })
        except Exception:
            external_services.append({
                "id": "imessage",
                "name": "iMessage Gateway",
                "status": "Unhealthy",
                "detail": "Connection failed",
            })

    # SMS Assistant (check heartbeat file)
    sms_heartbeat = Path(os.path.expanduser("~/.sms-assistant/heartbeat"))
    if sms_heartbeat.exists():
        try:
            heartbeat_time = datetime.fromisoformat(sms_heartbeat.read_text().strip())
            age_seconds = (datetime.now() - heartbeat_time).total_seconds()
            if age_seconds < 60:
                external_services.append({
                    "id": "sms_assistant",
                    "name": "SMS Assistant",
                    "status": "Healthy",
                    "detail": "Polling for messages",
                    "checks": {"last_heartbeat": f"{int(age_seconds)}s ago"}
                })
            else:
                external_services.append({
                    "id": "sms_assistant",
                    "name": "SMS Assistant",
                    "status": "Degraded",
                    "detail": f"Last heartbeat {int(age_seconds)}s ago",
                })
        except Exception:
            external_services.append({
                "id": "sms_assistant",
                "name": "SMS Assistant",
                "status": "Degraded",
                "detail": "Invalid heartbeat file",
            })

    # Notification sinks
    sinks_status = []
    for sink in app.state.sinks:
        if sink.is_enabled():
            sinks_status.append({
                "id": sink.name.lower().replace(" ", "_"),
                "name": sink.name,
                "status": "Healthy",
                "detail": "Enabled and configured",
            })
        else:
            sinks_status.append({
                "id": sink.name.lower().replace(" ", "_"),
                "name": sink.name,
                "status": "Disabled",
                "detail": "Not configured",
            })

    # Recent logs (from LLM log file if exists)
    logs = []
    llm_log_file = Path("/app/data/llm.log")
    if llm_log_file.exists():
        try:
            lines = llm_log_file.read_text().strip().split("\n")
            for line in lines[-20:]:
                if " | " in line and not line.startswith("  "):
                    parts = line.split(" | ")
                    if len(parts) >= 4:
                        logs.append({
                            "time": parts[0].split(" ")[1] if " " in parts[0] else parts[0],
                            "source": "llm",
                            "type": "llm",
                            "message": f"{parts[1]} ({parts[3]})"
                        })
        except Exception:
            pass

    # Also add recent notifications to logs
    recent = db.get_recent_notifications(10)
    for n in recent:
        if n["app"] not in HIDDEN_APPS:
            logs.append({
                "time": n["timestamp"].split(" ")[1][:8] if " " in n["timestamp"] else n["timestamp"][:8],
                "source": n["app"][:10],
                "type": n["action"],
                "message": f"{n['title'][:30]}: {n['body'][:40]}..."
            })

    # Sort by time descending and limit
    logs = sorted(logs, key=lambda x: x["time"], reverse=True)[:15]

    return {
        "core": core_services,
        "external": external_services,
        "sinks": sinks_status,
        "logs": logs,
    }
