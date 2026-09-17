"""Status page HTML template."""

STATUS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Status - Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --bg-base: #08090b; --bg-surface: #0f1116; --bg-elevated: #14171f; --bg-inset: #05060a;
            --rule: #1c2330; --rule-strong: #2a3340;
            --fg-primary: #e8e6e1; --fg-secondary: #8b94a3; --fg-muted: #4d5560; --fg-dim: #353c47;
            --accent-live: #9fffb0;
            --accent-cool: #6cd5ff; --accent-cool-rgb: 108,213,255;
            --accent-warn: #ffb86c; --accent-warn-rgb: 255,184,108;
            --accent-success: #4ade80;
            --accent-steel: #7aa9c4;
            --accent-signoff: #c4a1ff;
            --danger: #ff8a7a; --danger-rgb: 255,138,122;
            --fs-xs: 11px; --fs-sm: 12px; --fs-base: 13px; --fs-md: 14px; --fs-lg: 16px; --fs-display: 20px;
            --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            --gap-1: 4px; --gap-2: 8px; --gap-3: 12px; --gap-4: 16px; --gap-5: 24px; --gap-6: 32px;
            --t-fast: 120ms; --t-med: 160ms; --ease-out: cubic-bezier(0.2, 0.7, 0.2, 1);
        }
        @media (prefers-color-scheme: light) {
            :root:not([data-theme="dark"]) {
                --bg-base: #f7f7f5; --bg-surface: #ffffff; --bg-elevated: #ececea; --bg-inset: #ecece9;
                --rule: #d8d8d4; --rule-strong: #b8b8b3;
                --fg-primary: #1a1a18; --fg-secondary: #55565c; --fg-muted: #8a8b8f; --fg-dim: #b4b5b8;
                --accent-live: #0f9d58;
                --accent-cool: #0b6fb0; --accent-cool-rgb: 11,111,176;
                --accent-warn: #b26a00; --accent-warn-rgb: 178,106,0;
                --accent-success: #157f3b;
                --accent-steel: #3d6a86;
                --accent-signoff: #6b3fb0;
                --danger: #cf3b2e; --danger-rgb: 207,59,46;
            }
        }
        * { box-sizing: border-box; border-radius: 0 !important; }
        button:focus-visible, a:focus-visible { outline: 2px solid var(--accent-cool); outline-offset: 1px; }
        body { font-family: var(--font-mono); margin: 0; padding: 20px; background: var(--bg-base); color: var(--fg-primary); }
        h1 { margin: 0 0 20px; font-size: var(--fs-display); font-weight: normal; text-transform: uppercase; letter-spacing: 2px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid var(--rule-strong); padding-bottom: 12px; }
        a.back { color: var(--fg-primary); text-decoration: none; font-size: var(--fs-md); text-transform: none; letter-spacing: normal; }
        a.back:hover { text-decoration: underline; }
        .status-grid { display: grid; gap: 12px; }
        .service { border: 1px solid var(--rule); background: var(--bg-surface); padding: 16px; }
        .service-icon { width: 40px; height: 40px; border: 1px solid var(--fg-muted); color: var(--fg-secondary); display: flex; align-items: center; justify-content: center; font-size: var(--fs-xs); letter-spacing: 0.5px; flex-shrink: 0; }
        .service-header { display: flex; align-items: center; gap: 16px; }
        .service-icon.healthy { border-color: var(--accent-success); color: var(--accent-success); }
        .service-icon.degraded { border-color: var(--accent-warn); color: var(--accent-warn); border-style: dashed; }
        .service-icon.unhealthy { border-color: var(--danger); color: var(--danger); animation: danger-pulse 1.4s var(--ease-out) infinite; }
        .service-icon.disabled { border-color: var(--rule); color: var(--fg-muted); }
        .service-icon.checking { border-color: var(--accent-cool); color: var(--accent-cool); animation: cool-pulse 1.4s var(--ease-out) infinite; }
        @keyframes danger-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(var(--danger-rgb), 0.0); }
            50%      { box-shadow: 0 0 0 4px rgba(var(--danger-rgb), 0.28); }
        }
        @keyframes cool-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(var(--accent-cool-rgb), 0.0); }
            50%      { box-shadow: 0 0 0 4px rgba(var(--accent-cool-rgb), 0.28); }
        }
        @media (prefers-reduced-motion: reduce) {
            .service-icon.unhealthy, .service-status.unhealthy { animation: none; box-shadow: 0 0 0 2px rgba(var(--danger-rgb), 0.34); }
            .service-icon.checking, .service-status.checking { animation: none; box-shadow: 0 0 0 2px rgba(var(--accent-cool-rgb), 0.34); }
        }
        .service-info { flex: 1; min-width: 0; }
        .service-name { font-weight: bold; font-size: var(--fs-lg); margin-bottom: 2px; }
        .service-detail { font-size: var(--fs-base); color: var(--fg-secondary); }
        .service-url { font-family: inherit; font-size: var(--fs-xs); color: var(--fg-muted); margin-top: 4px; word-break: break-all; }
        .service-status { font-size: var(--fs-xs); font-weight: bold; padding: 4px 10px; border: 1px solid currentColor; flex-shrink: 0; text-transform: uppercase; }
        .service-status.healthy { color: var(--accent-success); }
        .service-status.degraded { color: var(--accent-warn); border-style: dashed; }
        .service-status.unhealthy { color: var(--danger); animation: danger-pulse 1.4s var(--ease-out) infinite; }
        .service-status.disabled { color: var(--fg-muted); border-color: var(--rule); }
        .service-status.checking { color: var(--accent-cool); animation: cool-pulse 1.4s var(--ease-out) infinite; }
        .service-checks { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--rule); display: grid; gap: 6px; }
        .check-item { display: flex; justify-content: space-between; align-items: center; font-size: var(--fs-base); }
        .check-label { color: var(--fg-secondary); }
        .check-value { font-family: inherit; }
        .check-value.ok { color: var(--accent-success); }
        .check-value.warn { color: var(--accent-warn); }
        .check-value.error { color: var(--danger); font-weight: bold; }
        .check-value.info { color: var(--accent-cool); }
        .check-value.ok::before { content: "✓ "; }
        .check-value.warn::before { content: "! "; }
        .check-value.error::before { content: "✗ "; }
        .check-value.info::before { content: "› "; }
        .service-response { font-family: inherit; font-size: var(--fs-xs); border: 1px dashed var(--rule); padding: 8px; margin-top: 10px; max-height: 80px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: var(--fg-secondary); }
        .service-response.error { color: var(--danger); border-color: var(--danger); }
        .section-title { font-size: var(--fs-base); text-transform: uppercase; color: var(--fg-secondary); margin: 24px 0 12px; letter-spacing: 1px; }
        .section-title:first-of-type { margin-top: 0; }
        .refresh-btn { background: var(--bg-surface); color: var(--fg-primary); border: 1px solid var(--rule-strong); padding: 8px 16px; cursor: pointer; font-size: var(--fs-base); font-family: inherit; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 0.5px; transition: background var(--t-fast) var(--ease-out); }
        .refresh-btn:hover { background: var(--bg-elevated); }
        .refresh-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .last-check { font-size: var(--fs-sm); color: var(--fg-secondary); margin-left: 12px; }
        .auto-refresh { font-size: var(--fs-xs); color: var(--fg-muted); margin-left: 8px; }
        .logs-container { border: 1px solid var(--rule); background: var(--bg-surface); padding: 12px; font-family: inherit; font-size: var(--fs-sm); max-height: 300px; overflow-y: auto; }
        .log-entry { padding: 4px 0; border-bottom: 1px solid var(--rule); display: flex; gap: 10px; }
        .log-entry:last-child { border-bottom: none; }
        .log-time { color: var(--fg-muted); flex-shrink: 0; }
        .log-source { color: var(--fg-secondary); flex-shrink: 0; min-width: 80px; }
        .log-source.llm { color: var(--accent-steel); font-weight: bold; }
        .log-message { color: var(--fg-primary); word-break: break-word; }
        .log-message.sent { color: var(--accent-success); }
        .log-message.dropped { color: var(--danger); }
        .log-message.rate_limited { color: var(--accent-warn); }
        .log-message.llm { color: var(--accent-steel); }
        .log-message.sent::before { content: "✓ "; }
        .log-message.dropped::before { content: "✗ "; }
        .log-message.rate_limited::before { content: "» "; }
        .log-message.llm::before { content: "† "; }
        .warnings-container { border: 1px solid var(--accent-warn); background: var(--bg-surface); padding: 12px; margin-bottom: 20px; }
        .warning-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--rule); }
        .warning-item:last-child { border-bottom: none; }
        .warning-icon { color: var(--accent-warn); font-size: var(--fs-md); font-weight: bold; }
        .warning-sink { font-weight: bold; color: var(--accent-warn); min-width: 80px; }
        .warning-message { color: var(--fg-secondary); }
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
