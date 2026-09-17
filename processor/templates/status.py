"""Status page HTML template."""

STATUS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Status - Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --bg: #000; --fg: #fff; --muted: #999; --dim: #666; --border: #333; --border-strong: #fff;
        }
        * { box-sizing: border-box; }
        body { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; margin: 0; padding: 20px; background: var(--bg); color: var(--fg); }
        h1 { margin: 0 0 20px; font-size: 22px; font-weight: normal; text-transform: uppercase; letter-spacing: 2px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid var(--border-strong); padding-bottom: 12px; }
        a.back { color: var(--fg); text-decoration: none; font-size: 14px; text-transform: none; letter-spacing: normal; }
        a.back:hover { text-decoration: underline; }
        .status-grid { display: grid; gap: 12px; }
        .service { border: 1px solid var(--border); padding: 16px; }
        .service-header { display: flex; align-items: center; gap: 16px; }
        .service-icon { width: 40px; height: 40px; border: 1px solid var(--border-strong); display: flex; align-items: center; justify-content: center; font-size: 11px; letter-spacing: 0.5px; flex-shrink: 0; }
        .service-icon.healthy { background: var(--fg); color: var(--bg); }
        .service-icon.degraded { border-style: dashed; }
        .service-icon.unhealthy { animation: pulse 1s ease-in-out infinite; }
        .service-icon.disabled { border-color: var(--border); color: var(--dim); }
        .service-icon.checking { animation: pulse 1s ease-in-out infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        .service-info { flex: 1; min-width: 0; }
        .service-name { font-weight: bold; font-size: 16px; margin-bottom: 2px; }
        .service-detail { font-size: 13px; color: var(--muted); }
        .service-url { font-family: inherit; font-size: 11px; color: var(--dim); margin-top: 4px; word-break: break-all; }
        .service-status { font-size: 11px; font-weight: bold; padding: 4px 10px; border: 1px solid currentColor; flex-shrink: 0; text-transform: uppercase; }
        .service-status.healthy { background: var(--fg); color: var(--bg); }
        .service-status.degraded { background: var(--bg); color: var(--fg); border-style: dashed; }
        .service-status.unhealthy { background: var(--bg); color: var(--fg); animation: pulse 1s ease-in-out infinite; }
        .service-status.disabled { background: var(--bg); color: var(--dim); border-color: var(--border); }
        .service-status.checking { background: var(--bg); color: var(--fg); animation: pulse 1s ease-in-out infinite; }
        .service-checks { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); display: grid; gap: 6px; }
        .check-item { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
        .check-label { color: var(--muted); }
        .check-value { font-family: inherit; }
        .check-value.ok::before { content: "✓ "; }
        .check-value.warn::before { content: "! "; }
        .check-value.error::before { content: "✗ "; font-weight: bold; }
        .check-value.info::before { content: "› "; color: var(--muted); }
        .service-response { font-family: inherit; font-size: 11px; border: 1px dashed var(--border); padding: 8px; margin-top: 10px; max-height: 80px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: var(--muted); }
        .service-response.error { color: var(--fg); border-color: var(--fg); }
        .section-title { font-size: 13px; text-transform: uppercase; color: var(--muted); margin: 24px 0 12px; letter-spacing: 1px; }
        .section-title:first-of-type { margin-top: 0; }
        .refresh-btn { background: var(--bg); color: var(--fg); border: 1px solid var(--border-strong); padding: 8px 16px; cursor: pointer; font-size: 13px; font-family: inherit; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 0.5px; }
        .refresh-btn:hover { background: var(--fg); color: var(--bg); }
        .refresh-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .last-check { font-size: 12px; color: var(--muted); margin-left: 12px; }
        .auto-refresh { font-size: 11px; color: var(--dim); margin-left: 8px; }
        .logs-container { border: 1px solid var(--border); padding: 12px; font-family: inherit; font-size: 12px; max-height: 300px; overflow-y: auto; }
        .log-entry { padding: 4px 0; border-bottom: 1px solid var(--border); display: flex; gap: 10px; }
        .log-entry:last-child { border-bottom: none; }
        .log-time { color: var(--dim); flex-shrink: 0; }
        .log-source { color: var(--muted); flex-shrink: 0; min-width: 80px; }
        .log-source.llm { color: var(--fg); font-weight: bold; }
        .log-message { color: var(--fg); word-break: break-word; }
        .log-message.sent::before { content: "✓ "; }
        .log-message.dropped::before { content: "✗ "; }
        .log-message.rate_limited::before { content: "» "; }
        .log-message.llm::before { content: "† "; }
        .warnings-container { border: 1px solid var(--border-strong); padding: 12px; margin-bottom: 20px; }
        .warning-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--border); }
        .warning-item:last-child { border-bottom: none; }
        .warning-icon { color: var(--fg); font-size: 14px; font-weight: bold; }
        .warning-sink { font-weight: bold; color: var(--fg); min-width: 80px; }
        .warning-message { color: var(--muted); }
        .no-warnings { display: none; }
    </style>
</head>
<body>
    <h1><a href="/" class="back">← Dashboard</a> System Status</h1>

    <button class="refresh-btn" onclick="refresh(true)">Refresh</button>
    <span class="last-check" id="last-check"></span>
    <span class="auto-refresh">(auto-refreshes every 10s)</span>

    <div id="warnings-section" class="no-warnings">
        <div class="section-title">Warnings</div>
        <div class="warnings-container" id="warnings"></div>
    </div>

    <div class="section-title">Core Services</div>
    <div class="status-grid" id="core-services"></div>

    <div class="section-title">External Connections</div>
    <div class="status-grid" id="external-services"></div>

    <div class="section-title">Notification Sinks</div>
    <div class="status-grid" id="sinks"></div>

    <div class="section-title">Recent Activity</div>
    <div class="logs-container" id="logs"></div>

    <script>
        const icons = {
            processor: 'PROC',
            database: 'DB',
            rules: 'RULE',
            rate_limiter: 'RATE',
            sentiment: 'SENT',
            ollama: 'LLM',
            pi: 'PI',
            imessage: 'IMSG',
            sms_assistant: 'SMS',
            bark: 'BARK',
            ntfy: 'NTFY',
            twilio: 'TXT',
            console: 'CLI'
        };

        function renderCheck(key, value) {
            let valueClass = 'info';
            const v = String(value).toLowerCase();
            if (v === 'ok' || v === 'true' || v === 'healthy' || v === 'connected' || v === 'yes') valueClass = 'ok';
            else if (v === 'error' || v === 'false' || v === 'unhealthy' || v === 'unavailable' || v === 'no') valueClass = 'error';
            else if (v === 'degraded' || v === 'warning') valueClass = 'warn';
            return `<div class="check-item"><span class="check-label">${key}</span><span class="check-value ${valueClass}">${value}</span></div>`;
        }

        function formatValue(v) {
            if (Array.isArray(v)) return v.join(', ');
            if (typeof v === 'object' && v !== null) return JSON.stringify(v);
            return String(v);
        }

        function renderService(s) {
            const icon = icons[s.id] || '?';
            const statusClass = s.status.toLowerCase();

            // URL line (for external services)
            let urlHtml = '';
            if (s.url) {
                urlHtml = `<div class="service-url">${s.url}</div>`;
            }

            // Combine checks and response into one details section
            let detailsHtml = '';
            const allChecks = [];

            // Add explicit checks first
            if (s.checks) {
                Object.entries(s.checks).forEach(([k, v]) => allChecks.push([k, v]));
            }

            // Add response fields (if not already in checks)
            if (s.response && typeof s.response === 'object') {
                const checkKeys = new Set(Object.keys(s.checks || {}));
                Object.entries(s.response).forEach(([k, v]) => {
                    if (!checkKeys.has(k)) {
                        allChecks.push([k, formatValue(v)]);
                    }
                });
            }

            if (allChecks.length > 0) {
                detailsHtml = '<div class="service-checks">' +
                    allChecks.map(([k, v]) => renderCheck(k, v)).join('') +
                    '</div>';
            }

            // Error section (if any)
            let errorHtml = '';
            if (s.error) {
                errorHtml = `<div class="service-response error">${s.error}</div>`;
            }

            return `
                <div class="service">
                    <div class="service-header">
                        <div class="service-icon ${statusClass}">${icon}</div>
                        <div class="service-info">
                            <div class="service-name">${s.name}</div>
                            <div class="service-detail">${s.detail || ''}</div>
                            ${urlHtml}
                        </div>
                        <div class="service-status ${statusClass}">${s.status}</div>
                    </div>
                    ${detailsHtml}
                    ${errorHtml}
                </div>
            `;
        }

        function renderWarning(w) {
            return `
                <div class="warning-item">
                    <span class="warning-icon">!</span>
                    <span class="warning-sink">${w.sink}</span>
                    <span class="warning-message">${w.message}</span>
                </div>
            `;
        }

        async function refresh(manual = false) {
            const btn = document.querySelector('.refresh-btn');

            if (manual) {
                btn.disabled = true;
                btn.textContent = 'Checking...';
                document.querySelectorAll('.service-icon, .service-status').forEach(el => {
                    el.className = el.className.replace(/healthy|degraded|unhealthy|disabled/g, 'checking');
                });
            }

            try {
                const resp = await fetch('/api/status');
                const data = await resp.json();

                // Render warnings
                const warningsSection = document.getElementById('warnings-section');
                if (data.warnings && data.warnings.length > 0) {
                    warningsSection.classList.remove('no-warnings');
                    document.getElementById('warnings').innerHTML =
                        data.warnings.map(renderWarning).join('');
                } else {
                    warningsSection.classList.add('no-warnings');
                }

                document.getElementById('core-services').innerHTML =
                    data.core.map(renderService).join('');
                document.getElementById('external-services').innerHTML =
                    data.external.map(renderService).join('');
                document.getElementById('sinks').innerHTML =
                    data.sinks.map(renderService).join('');

                // Render logs
                if (data.logs && data.logs.length > 0) {
                    document.getElementById('logs').innerHTML = data.logs.map(log => `
                        <div class="log-entry">
                            <span class="log-time">${log.time}</span>
                            <span class="log-source ${log.source === 'llm' ? 'llm' : ''}">${log.source}</span>
                            <span class="log-message ${log.type || ''}">${log.message}</span>
                        </div>
                    `).join('');
                } else {
                    document.getElementById('logs').innerHTML = '<div style="color: var(--muted);">No recent activity</div>';
                }

                document.getElementById('last-check').textContent =
                    'Updated: ' + new Date().toLocaleTimeString();
            } catch (e) {
                console.error('Status check failed:', e);
            }

            if (manual) {
                btn.disabled = false;
                btn.textContent = 'Refresh';
            }
        }

        refresh(true);
        setInterval(() => refresh(false), 10000);
    </script>
</body>
</html>
"""
