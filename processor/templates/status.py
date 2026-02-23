"""Status page HTML template."""

STATUS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Status - Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: #e0e0e0; }
        h1 { margin: 0 0 20px; font-size: 24px; display: flex; align-items: center; gap: 15px; }
        a.back { color: #60a5fa; text-decoration: none; font-size: 14px; }
        a.back:hover { text-decoration: underline; }
        .status-grid { display: grid; gap: 12px; }
        .service { background: #2a2a2a; border-radius: 8px; padding: 16px; }
        .service-header { display: flex; align-items: center; gap: 16px; }
        .service-icon { width: 40px; height: 40px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
        .service-icon.healthy { background: #166534; }
        .service-icon.degraded { background: #854d0e; }
        .service-icon.unhealthy { background: #991b1b; }
        .service-icon.disabled { background: #374151; }
        .service-icon.checking { background: #1e3a5f; animation: pulse 1s ease-in-out infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .service-info { flex: 1; min-width: 0; }
        .service-name { font-weight: bold; font-size: 16px; margin-bottom: 2px; }
        .service-detail { font-size: 13px; color: #9ca3af; }
        .service-url { font-family: monospace; font-size: 11px; color: #6b7280; margin-top: 4px; word-break: break-all; }
        .service-status { font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 4px; flex-shrink: 0; }
        .service-status.healthy { background: #166534; color: white; }
        .service-status.degraded { background: #854d0e; color: white; }
        .service-status.unhealthy { background: #991b1b; color: white; }
        .service-status.disabled { background: #374151; color: #9ca3af; }
        .service-status.checking { background: #1e3a5f; color: #60a5fa; }
        .service-checks { margin-top: 12px; padding-top: 12px; border-top: 1px solid #3a3a3a; display: grid; gap: 6px; }
        .check-item { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
        .check-label { color: #9ca3af; }
        .check-value { font-family: monospace; }
        .check-value.ok { color: #4ade80; }
        .check-value.warn { color: #fbbf24; }
        .check-value.error { color: #f87171; }
        .check-value.info { color: #60a5fa; }
        .service-response { font-family: monospace; font-size: 11px; background: #1a1a1a; padding: 8px; border-radius: 4px; margin-top: 10px; max-height: 80px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: #9ca3af; }
        .service-response.error { color: #f87171; background: #1f1515; }
        .section-title { font-size: 14px; text-transform: uppercase; color: #6b7280; margin: 24px 0 12px; letter-spacing: 0.5px; }
        .section-title:first-of-type { margin-top: 0; }
        .refresh-btn { background: #3b82f6; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; margin-bottom: 20px; }
        .refresh-btn:hover { background: #2563eb; }
        .refresh-btn:disabled { background: #4b5563; cursor: not-allowed; }
        .last-check { font-size: 12px; color: #6b7280; margin-left: 12px; }
        .auto-refresh { font-size: 11px; color: #4b5563; margin-left: 8px; }
        .logs-container { background: #2a2a2a; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; }
        .log-entry { padding: 4px 0; border-bottom: 1px solid #333; display: flex; gap: 10px; }
        .log-entry:last-child { border-bottom: none; }
        .log-time { color: #6b7280; flex-shrink: 0; }
        .log-source { color: #60a5fa; flex-shrink: 0; min-width: 80px; }
        .log-source.llm { color: #a78bfa; font-weight: bold; }
        .log-message { color: #e0e0e0; word-break: break-word; }
        .log-message.sent { color: #4ade80; }
        .log-message.dropped { color: #f87171; }
        .log-message.rate_limited { color: #fbbf24; }
        .log-message.llm { color: #c4b5fd; }
        .warnings-container { background: #451a03; border: 1px solid #854d0e; border-radius: 8px; padding: 12px; margin-bottom: 20px; }
        .warning-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid #713f12; }
        .warning-item:last-child { border-bottom: none; }
        .warning-icon { color: #fbbf24; font-size: 16px; }
        .warning-sink { font-weight: bold; color: #fcd34d; min-width: 80px; }
        .warning-message { color: #fef3c7; }
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
            processor: '⚙️',
            database: '🗄️',
            rules: '📋',
            rate_limiter: '🚦',
            sentiment: '🧠',
            ollama: '🤖',
            pi: '📡',
            imessage: '💬',
            sms_assistant: '📱',
            bark: '🔔',
            ntfy: '📢',
            twilio: '📲',
            console: '🖥️'
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
            const icon = icons[s.id] || '❓';
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
                    <span class="warning-icon">⚠</span>
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
                    document.getElementById('logs').innerHTML = '<div style="color: #6b7280;">No recent activity</div>';
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
