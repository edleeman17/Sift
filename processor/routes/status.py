"""System status routes."""

import os
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services.pi_health import get_pi_health
from templates.status import STATUS_HTML
from sinks import get_config_warnings
import db

router = APIRouter(tags=["status"])

# Apps to hide from dashboard (sink echoes)
HIDDEN_APPS = {"bark", "ntfy"}


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """System status page."""
    return HTMLResponse(content=STATUS_HTML)


async def check_endpoint(url: str, timeout: float = 2.0, verify: bool = True) -> dict:
    """Check an HTTP endpoint and return response or error."""
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return {"ok": True, "data": resp.json()}
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


@router.get("/api/status")
async def status_api(request: Request):
    """JSON API for system status data."""
    app = request.app

    # Core services (internal, no external health checks)
    core_services = []

    # Processor
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

    # Rule Engine
    rules = app.state.rules
    global_rules = len(rules.global_config.get("rules", []))
    app_count = len(rules.config.get("apps", {}))
    core_services.append({
        "id": "rules",
        "name": "Rule Engine",
        "status": "Healthy",
        "detail": f"{app_count} apps configured",
        "checks": {
            "apps": app_count,
            "global_rules": global_rules,
        }
    })

    # Rate Limiter
    rl = app.state.rate_limiter
    core_services.append({
        "id": "rate_limiter",
        "name": "Rate Limiter",
        "status": "Healthy",
        "detail": f"Max {rl.max_per_hour}/hr, {rl.cooldown_seconds}s cooldown",
        "checks": {
            "max_per_hour": rl.max_per_hour,
            "cooldown_seconds": rl.cooldown_seconds,
        }
    })

    # Sentiment Analyzer
    sentiment_config = rules.global_config.get("sentiment_detection", {})
    sentiment_enabled = sentiment_config.get("enabled", False)
    core_services.append({
        "id": "sentiment",
        "name": "Sentiment Analyzer",
        "status": "Healthy" if sentiment_enabled else "Disabled",
        "detail": "Batched LLM urgency detection" if sentiment_enabled else "Not enabled in config",
        "checks": {
            "enabled": sentiment_enabled,
            "batch_window": sentiment_config.get("batch_window_seconds", 60),
            "max_batch": sentiment_config.get("max_batch_size", 30),
        } if sentiment_enabled else {}
    })

    # External services (with health checks)
    external_services = []

    # Pi/ancs-bridge
    pi_url = os.getenv("PI_HEALTH_URL", "")
    if pi_url:
        result = await check_endpoint(pi_url, timeout=3.0)
        if result["ok"]:
            data = result["data"]
            connected = data.get("phone_connected", False)
            battery = data.get("battery")
            checks = {"phone_connected": "Yes" if connected else "No"}
            if battery is not None:
                checks["battery"] = f"{battery}%"
            external_services.append({
                "id": "pi",
                "name": "Raspberry Pi (ancs-bridge)",
                "status": "Healthy" if connected else "Degraded",
                "detail": "iPhone connected" if connected else "iPhone not connected",
                "url": pi_url,
                "response": data,
                "checks": checks,
            })
        else:
            external_services.append({
                "id": "pi",
                "name": "Raspberry Pi (ancs-bridge)",
                "status": "Unhealthy",
                "detail": result["error"],
                "url": pi_url,
                "error": result["error"],
            })
    else:
        external_services.append({
            "id": "pi",
            "name": "Raspberry Pi (ancs-bridge)",
            "status": "Disabled",
            "detail": "PI_HEALTH_URL not set",
        })

    # Ollama
    ollama_url = os.getenv("OLLAMA_URL", "")
    if ollama_url:
        result = await check_endpoint(f"{ollama_url}/api/tags")
        if result["ok"]:
            models = result["data"].get("models", [])
            model_names = [m.get("name", "?") for m in models[:3]]
            external_services.append({
                "id": "ollama",
                "name": "Ollama LLM",
                "status": "Healthy",
                "detail": f"Models: {', '.join(model_names)}" if model_names else "No models",
                "url": f"{ollama_url}/api/tags",
                "response": {"models": [m.get("name") for m in models], "count": len(models)},
                "checks": {"models_available": len(models)}
            })
        else:
            external_services.append({
                "id": "ollama",
                "name": "Ollama LLM",
                "status": "Unhealthy",
                "detail": result["error"],
                "url": f"{ollama_url}/api/tags",
                "error": result["error"],
            })
    else:
        external_services.append({
            "id": "ollama",
            "name": "Ollama LLM",
            "status": "Disabled",
            "detail": "OLLAMA_URL not set",
        })

    # iMessage Gateway
    imessage_url = os.getenv("IMESSAGE_GATEWAY_URL", "")
    if imessage_url:
        result = await check_endpoint(f"{imessage_url}/health")
        if result["ok"]:
            external_services.append({
                "id": "imessage",
                "name": "iMessage Gateway",
                "status": "Healthy",
                "detail": "macOS Messages.app bridge running",
                "url": f"{imessage_url}/health",
                "response": result["data"],
            })
        else:
            external_services.append({
                "id": "imessage",
                "name": "iMessage Gateway",
                "status": "Unhealthy",
                "detail": result["error"],
                "url": f"{imessage_url}/health",
                "error": result["error"],
            })
    else:
        external_services.append({
            "id": "imessage",
            "name": "iMessage Gateway",
            "status": "Disabled",
            "detail": "IMESSAGE_GATEWAY_URL not set",
        })

    # Bark
    bark_config = app.state.rules.config.get("sinks", {}).get("bark", {})
    bark_url = bark_config.get("url", "")
    if bark_url:
        result = await check_endpoint(f"{bark_url}/ping")
        if result["ok"]:
            external_services.append({
                "id": "bark",
                "name": "Bark Push Server",
                "status": "Healthy" if result["data"].get("code") == 200 else "Unhealthy",
                "detail": "iOS push notifications ready",
                "url": f"{bark_url}/ping",
                "response": result["data"],
            })
        else:
            external_services.append({
                "id": "bark",
                "name": "Bark Push Server",
                "status": "Unhealthy",
                "detail": result["error"],
                "url": f"{bark_url}/ping",
                "error": result["error"],
            })
    else:
        external_services.append({
            "id": "bark",
            "name": "Bark Push Server",
            "status": "Disabled",
            "detail": "Not configured",
        })

    # ntfy
    ntfy_config = app.state.rules.config.get("sinks", {}).get("ntfy", {})
    ntfy_url = ntfy_config.get("url", "")
    if ntfy_url:
        ntfy_base = "/".join(ntfy_url.rstrip("/").split("/")[:-1]) if "/" in ntfy_url else ntfy_url
        result = await check_endpoint(f"{ntfy_base}/v1/health", verify=False)
        if result["ok"]:
            external_services.append({
                "id": "ntfy",
                "name": "ntfy Server",
                "status": "Healthy" if result["data"].get("healthy") else "Unhealthy",
                "detail": "Push notifications ready",
                "url": f"{ntfy_base}/v1/health",
                "response": result["data"],
            })
        else:
            external_services.append({
                "id": "ntfy",
                "name": "ntfy Server",
                "status": "Unhealthy",
                "detail": result["error"],
                "url": f"{ntfy_base}/v1/health",
                "error": result["error"],
            })
    else:
        external_services.append({
            "id": "ntfy",
            "name": "ntfy Server",
            "status": "Disabled",
            "detail": "Not configured",
        })

    # SMS Assistant (heartbeat file)
    sms_heartbeat = Path("/app/sms-assistant-state/heartbeat")
    if sms_heartbeat.exists():
        try:
            heartbeat_content = sms_heartbeat.read_text().strip()
            heartbeat_time = datetime.fromisoformat(heartbeat_content)
            age_seconds = int((datetime.now() - heartbeat_time).total_seconds())
            external_services.append({
                "id": "sms_assistant",
                "name": "SMS Assistant",
                "status": "Healthy" if age_seconds < 60 else "Degraded",
                "detail": "Polling for messages" if age_seconds < 60 else f"Last heartbeat {age_seconds}s ago",
                "url": str(sms_heartbeat),
                "response": {"last_heartbeat": heartbeat_content, "age_seconds": age_seconds},
                "checks": {"last_heartbeat": f"{age_seconds}s ago"}
            })
        except Exception as e:
            external_services.append({
                "id": "sms_assistant",
                "name": "SMS Assistant",
                "status": "Unhealthy",
                "detail": "Invalid heartbeat file",
                "url": str(sms_heartbeat),
                "error": str(e)[:100],
            })
    else:
        external_services.append({
            "id": "sms_assistant",
            "name": "SMS Assistant",
            "status": "Disabled",
            "detail": "No heartbeat file",
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
                        # LLM log format: "2026-02-23 11:14:11 | type | ..."
                        timestamp = parts[0].strip()
                        time_part = timestamp.split(" ")[1] if " " in timestamp else timestamp
                        logs.append({
                            "sort_key": timestamp,  # Full timestamp for sorting
                            "time": time_part[:8],  # HH:MM:SS for display
                            "source": "llm",
                            "type": "llm",
                            "message": f"{parts[1]} ({parts[3]})"
                        })
        except Exception:
            pass

    # Also add recent notifications to logs
    recent = db.get_recent_notifications(15)
    for n in recent:
        if n["app"] not in HIDDEN_APPS:
            # Notification timestamp format: "2026-02-23T11:14:12.862953" (ISO with T)
            timestamp = n["timestamp"]
            # Handle both "T" and space separators
            if "T" in timestamp:
                time_part = timestamp.split("T")[1][:8]
            elif " " in timestamp:
                time_part = timestamp.split(" ")[1][:8]
            else:
                time_part = timestamp[:8]
            logs.append({
                "sort_key": timestamp.replace("T", " "),  # Normalize for sorting
                "time": time_part,
                "source": n["app"][:10],
                "type": n["action"],
                "message": f"{n['title'][:30]}: {n['body'][:40]}..."
            })

    # Sort by full timestamp descending and limit
    logs = sorted(logs, key=lambda x: x["sort_key"], reverse=True)[:15]

    # Remove sort_key from output
    for log in logs:
        del log["sort_key"]

    return {
        "warnings": get_config_warnings(),
        "core": core_services,
        "external": external_services,
        "sinks": sinks_status,
        "logs": logs,
    }
