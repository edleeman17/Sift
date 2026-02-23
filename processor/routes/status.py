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

    # Health checks - fetch all endpoints and return ALL properties
    health_checks = []

    # 1. Processor health
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://localhost:8090/health")
            if resp.status_code == 200:
                data = resp.json()
                health_checks.append({
                    "id": "processor",
                    "name": "Processor",
                    "url": "/health",
                    "status": "healthy" if data.get("status") == "healthy" else "unhealthy",
                    "response": data,
                })
            else:
                health_checks.append({
                    "id": "processor",
                    "name": "Processor",
                    "url": "/health",
                    "status": "unhealthy",
                    "error": f"HTTP {resp.status_code}",
                })
    except Exception as e:
        health_checks.append({
            "id": "processor",
            "name": "Processor",
            "url": "/health",
            "status": "unhealthy",
            "error": str(e)[:100],
        })

    # 2. Pi/ancs-bridge health
    pi_url = os.getenv("PI_HEALTH_URL", "")
    if pi_url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(pi_url)
                data = resp.json()
                health_checks.append({
                    "id": "pi",
                    "name": "Pi (ancs-bridge)",
                    "url": pi_url,
                    "status": "healthy" if data.get("status") == "healthy" and data.get("phone_connected") else "degraded" if data.get("status") == "healthy" else "unhealthy",
                    "response": data,
                })
        except Exception as e:
            health_checks.append({
                "id": "pi",
                "name": "Pi (ancs-bridge)",
                "url": pi_url,
                "status": "unreachable",
                "error": str(e)[:100],
            })
    else:
        health_checks.append({
            "id": "pi",
            "name": "Pi (ancs-bridge)",
            "url": "not configured",
            "status": "disabled",
            "error": "PI_HEALTH_URL not set",
        })

    # 3. iMessage Gateway health
    imessage_url = os.getenv("IMESSAGE_GATEWAY_URL", "")
    if imessage_url:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{imessage_url}/health")
                if resp.status_code == 200:
                    data = resp.json()
                    health_checks.append({
                        "id": "imessage",
                        "name": "iMessage Gateway",
                        "url": f"{imessage_url}/health",
                        "status": "healthy" if data.get("status") == "healthy" else "unhealthy",
                        "response": data,
                    })
                else:
                    health_checks.append({
                        "id": "imessage",
                        "name": "iMessage Gateway",
                        "url": f"{imessage_url}/health",
                        "status": "unhealthy",
                        "error": f"HTTP {resp.status_code}",
                    })
        except Exception as e:
            health_checks.append({
                "id": "imessage",
                "name": "iMessage Gateway",
                "url": f"{imessage_url}/health",
                "status": "unreachable",
                "error": str(e)[:100],
            })
    else:
        health_checks.append({
            "id": "imessage",
            "name": "iMessage Gateway",
            "url": "not configured",
            "status": "disabled",
            "error": "IMESSAGE_GATEWAY_URL not set",
        })

    # 4. Bark health
    bark_config = app.state.rules.config.get("sinks", {}).get("bark", {})
    bark_url = bark_config.get("url", "")
    if bark_url:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{bark_url}/ping")
                if resp.status_code == 200:
                    data = resp.json()
                    health_checks.append({
                        "id": "bark",
                        "name": "Bark",
                        "url": f"{bark_url}/ping",
                        "status": "healthy" if data.get("code") == 200 else "unhealthy",
                        "response": data,
                    })
                else:
                    health_checks.append({
                        "id": "bark",
                        "name": "Bark",
                        "url": f"{bark_url}/ping",
                        "status": "unhealthy",
                        "error": f"HTTP {resp.status_code}",
                    })
        except Exception as e:
            health_checks.append({
                "id": "bark",
                "name": "Bark",
                "url": f"{bark_url}/ping",
                "status": "unreachable",
                "error": str(e)[:100],
            })
    else:
        health_checks.append({
            "id": "bark",
            "name": "Bark",
            "url": "not configured",
            "status": "disabled",
            "error": "No bark URL in config",
        })

    # 5. ntfy health
    ntfy_config = app.state.rules.config.get("sinks", {}).get("ntfy", {})
    ntfy_url = ntfy_config.get("url", "")
    if ntfy_url:
        # Extract base URL (remove topic path)
        ntfy_base = "/".join(ntfy_url.rstrip("/").split("/")[:-1]) if "/" in ntfy_url else ntfy_url
        try:
            async with httpx.AsyncClient(timeout=2.0, verify=False) as client:
                resp = await client.get(f"{ntfy_base}/v1/health")
                if resp.status_code == 200:
                    data = resp.json()
                    health_checks.append({
                        "id": "ntfy",
                        "name": "ntfy",
                        "url": f"{ntfy_base}/v1/health",
                        "status": "healthy" if data.get("healthy") else "unhealthy",
                        "response": data,
                    })
                else:
                    health_checks.append({
                        "id": "ntfy",
                        "name": "ntfy",
                        "url": f"{ntfy_base}/v1/health",
                        "status": "unhealthy",
                        "error": f"HTTP {resp.status_code}",
                    })
        except Exception as e:
            health_checks.append({
                "id": "ntfy",
                "name": "ntfy",
                "url": f"{ntfy_base}/v1/health",
                "status": "unreachable",
                "error": str(e)[:100],
            })
    else:
        health_checks.append({
            "id": "ntfy",
            "name": "ntfy",
            "url": "not configured",
            "status": "disabled",
            "error": "No ntfy URL in config",
        })

    # 6. Ollama health
    ollama_url = os.getenv("OLLAMA_URL", "")
    if ollama_url:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{ollama_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    health_checks.append({
                        "id": "ollama",
                        "name": "Ollama",
                        "url": f"{ollama_url}/api/tags",
                        "status": "healthy",
                        "response": {
                            "models": [m.get("name") for m in models],
                            "count": len(models),
                        },
                    })
                else:
                    health_checks.append({
                        "id": "ollama",
                        "name": "Ollama",
                        "url": f"{ollama_url}/api/tags",
                        "status": "unhealthy",
                        "error": f"HTTP {resp.status_code}",
                    })
        except Exception as e:
            health_checks.append({
                "id": "ollama",
                "name": "Ollama",
                "url": f"{ollama_url}/api/tags",
                "status": "unreachable",
                "error": str(e)[:100],
            })
    else:
        health_checks.append({
            "id": "ollama",
            "name": "Ollama",
            "url": "not configured",
            "status": "disabled",
            "error": "OLLAMA_URL not set",
        })

    # 7. SMS Assistant (heartbeat file)
    sms_heartbeat_path = Path(os.path.expanduser("~/.sms-assistant/heartbeat"))
    if sms_heartbeat_path.exists():
        try:
            heartbeat_content = sms_heartbeat_path.read_text().strip()
            heartbeat_time = datetime.fromisoformat(heartbeat_content)
            age_seconds = int((datetime.now() - heartbeat_time).total_seconds())
            health_checks.append({
                "id": "sms_assistant",
                "name": "SMS Assistant",
                "url": str(sms_heartbeat_path),
                "status": "healthy" if age_seconds < 60 else "degraded",
                "response": {
                    "last_heartbeat": heartbeat_content,
                    "age_seconds": age_seconds,
                },
            })
        except Exception as e:
            health_checks.append({
                "id": "sms_assistant",
                "name": "SMS Assistant",
                "url": str(sms_heartbeat_path),
                "status": "unhealthy",
                "error": str(e)[:100],
            })
    else:
        health_checks.append({
            "id": "sms_assistant",
            "name": "SMS Assistant",
            "url": str(sms_heartbeat_path),
            "status": "disabled",
            "error": "No heartbeat file found",
        })

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

    # Bark push server
    bark_config = app.state.rules.config.get("sinks", {}).get("bark", {})
    bark_url = bark_config.get("url", "")
    if bark_url:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{bark_url}/ping")
                if resp.status_code == 200:
                    external_services.append({
                        "id": "bark",
                        "name": "Bark Push Server",
                        "status": "Healthy",
                        "detail": "iOS push notifications ready",
                    })
                else:
                    external_services.append({
                        "id": "bark",
                        "name": "Bark Push Server",
                        "status": "Unhealthy",
                        "detail": f"HTTP {resp.status_code}",
                    })
        except Exception:
            external_services.append({
                "id": "bark",
                "name": "Bark Push Server",
                "status": "Unhealthy",
                "detail": "Connection failed",
            })

    # ntfy push server
    ntfy_config = app.state.rules.config.get("sinks", {}).get("ntfy", {})
    ntfy_url = ntfy_config.get("url", "")
    if ntfy_url:
        # Extract base URL (remove topic path)
        ntfy_base = "/".join(ntfy_url.rstrip("/").split("/")[:-1]) if "/" in ntfy_url else ntfy_url
        try:
            async with httpx.AsyncClient(timeout=2.0, verify=False) as client:
                resp = await client.get(f"{ntfy_base}/v1/health")
                if resp.status_code == 200:
                    external_services.append({
                        "id": "ntfy",
                        "name": "ntfy Server",
                        "status": "Healthy",
                        "detail": "Push notifications ready",
                    })
                else:
                    external_services.append({
                        "id": "ntfy",
                        "name": "ntfy Server",
                        "status": "Unhealthy",
                        "detail": f"HTTP {resp.status_code}",
                    })
        except Exception:
            external_services.append({
                "id": "ntfy",
                "name": "ntfy Server",
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
        "health_checks": health_checks,
        "core": core_services,
        "external": external_services,
        "sinks": sinks_status,
        "logs": logs,
    }
