"""Debug routes - view log files."""

import os
from pathlib import Path

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["debug"])

# Log files accessible from container
LOG_FILES = {
    "sms-assistant": Path("/app/logs/sms-assistant.log"),
    "imessage-gateway": Path("/app/logs/imessage-gateway.log"),
    "llm": Path("/app/data/llm.log"),
}

# Pi logs fetched via HTTP
PI_HEALTH_URL = os.getenv("PI_HEALTH_URL", "")
PI_LOGS_URL = PI_HEALTH_URL.replace("/health", "/logs") if PI_HEALTH_URL else ""

TAIL_LINES = 100


def read_log_tail(path: Path, lines: int = TAIL_LINES) -> str:
    """Read last N lines from a log file."""
    if not path.exists():
        return f"[Log file not found: {path}]"
    try:
        content = path.read_text()
        log_lines = content.strip().split("\n")
        return "\n".join(log_lines[-lines:])
    except Exception as e:
        return f"[Error reading log: {e}]"


async def fetch_pi_logs(lines: int = TAIL_LINES) -> str:
    """Fetch logs from Pi's ancs-bridge /logs endpoint."""
    if not PI_LOGS_URL:
        return "[PI_HEALTH_URL not configured - cannot fetch Pi logs]"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{PI_LOGS_URL}?lines={lines}")
            data = resp.json()
            return "\n".join(data.get("logs", []))
    except Exception as e:
        return f"[Error fetching Pi logs: {e}]"


@router.get("/debug/logs", response_class=HTMLResponse)
async def debug_logs_json():
    """Return log content as JSON for live updates."""
    from fastapi.responses import JSONResponse

    logs = {}
    for name, path in LOG_FILES.items():
        logs[name] = read_log_tail(path)

    # Add Pi logs
    logs["ancs-bridge"] = await fetch_pi_logs()

    return JSONResponse(content=logs)


@router.get("/debug", response_class=HTMLResponse)
async def debug_page():
    """Show all log files in a debug page."""

    logs_html = ""

    # Pi logs first (most important for debugging)
    pi_logs = await fetch_pi_logs()
    logs_html += f"""
    <div class="log-section">
        <h2>ancs-bridge (Pi)</h2>
        <div class="log-path">{PI_LOGS_URL or "PI_HEALTH_URL not set"}</div>
        <pre class="log-content" id="log-ancs-bridge">{pi_logs}</pre>
    </div>
    """

    for name, path in LOG_FILES.items():
        content = read_log_tail(path)
        logs_html += f"""
        <div class="log-section">
            <h2>{name}</h2>
            <div class="log-path">{path}</div>
            <pre class="log-content" id="log-{name}">{content}</pre>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Debug - Logs</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 0;
            padding: 20px;
        }}
        h1 {{
            color: #fff;
            margin-bottom: 10px;
        }}
        .nav {{
            margin-bottom: 20px;
        }}
        .nav a {{
            color: #6c9;
            margin-right: 15px;
        }}
        .refresh-info {{
            color: #888;
            font-size: 0.9em;
            margin-bottom: 20px;
        }}
        .log-section {{
            background: #16213e;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .log-section h2 {{
            margin: 0 0 5px 0;
            color: #6c9;
            font-size: 1.1em;
        }}
        .log-path {{
            color: #666;
            font-size: 0.8em;
            margin-bottom: 10px;
            font-family: monospace;
        }}
        .log-content {{
            background: #0f0f1a;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 0.85em;
            line-height: 1.4;
            margin: 0;
            max-height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .log-content::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        .log-content::-webkit-scrollbar-track {{
            background: #1a1a2e;
        }}
        .log-content::-webkit-scrollbar-thumb {{
            background: #444;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <h1>Debug - Logs</h1>
    <div class="nav">
        <a href="/">Dashboard</a>
        <a href="/rules">Rules</a>
        <a href="/debug">Logs</a>
    </div>
    <div class="refresh-info">
        Showing last {TAIL_LINES} lines per log.
        <label style="margin-left: 15px; cursor: pointer;">
            <input type="checkbox" id="auto-refresh" checked> Auto-refresh (1s)
        </label>
        <span id="status" style="margin-left: 10px; color: #6c9;"></span>
    </div>
    {logs_html}
    <script>
        let autoRefresh = true;
        let refreshInterval;

        async function fetchLogs() {{
            try {{
                const res = await fetch('/debug/logs');
                const logs = await res.json();
                for (const [name, content] of Object.entries(logs)) {{
                    const el = document.getElementById('log-' + name);
                    if (el) {{
                        const wasAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 50;
                        el.textContent = content;
                        if (wasAtBottom) {{
                            el.scrollTop = el.scrollHeight;
                        }}
                    }}
                }}
                document.getElementById('status').textContent = 'Updated ' + new Date().toLocaleTimeString();
            }} catch (e) {{
                document.getElementById('status').textContent = 'Error: ' + e.message;
            }}
        }}

        function startRefresh() {{
            refreshInterval = setInterval(fetchLogs, 1000);
        }}

        function stopRefresh() {{
            clearInterval(refreshInterval);
            document.getElementById('status').textContent = 'Paused';
        }}

        document.getElementById('auto-refresh').addEventListener('change', (e) => {{
            autoRefresh = e.target.checked;
            if (autoRefresh) {{
                startRefresh();
            }} else {{
                stopRefresh();
            }}
        }});

        // Initial scroll to bottom
        document.querySelectorAll('.log-content').forEach(el => {{
            el.scrollTop = el.scrollHeight;
        }});

        // Start auto-refresh
        startRefresh();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)
