"""Dashboard HTML template."""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {{
            --bg: #000; --fg: #fff; --muted: #999; --dim: #666; --border: #333; --border-strong: #fff;
        }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; margin: 0; padding: 20px; background: var(--bg); color: var(--fg); }}
        h1 {{ margin: 0 0 20px; font-size: 22px; font-weight: normal; text-transform: uppercase; letter-spacing: 2px; border-bottom: 1px solid var(--border-strong); padding-bottom: 12px; }}
        a {{ color: var(--fg); }}
        .stats {{ display: flex; gap: 0; margin-bottom: 20px; flex-wrap: wrap; border: 1px solid var(--border); }}
        .stat {{ padding: 12px 16px; min-width: 80px; flex: 1; border-right: 1px solid var(--border); }}
        .stat:last-child {{ border-right: none; }}
        .stat-value {{ font-size: 22px; font-weight: bold; }}
        .stat-label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }}
        .connection {{ border: 1px solid var(--border); padding: 12px 16px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; }}
        .connection-dot {{ width: 10px; height: 10px; border-radius: 50%; border: 1px solid var(--border-strong); flex-shrink: 0; background: transparent; }}
        .connection-dot.connected {{ background: var(--fg); animation: pulse 2s ease-in-out infinite; }}
        .connection-dot.disconnected {{ background: transparent; border-style: dashed; }}
        .connection-dot.unknown {{ background: var(--fg); opacity: 0.4; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
        .connection-info {{ display: flex; flex-direction: column; }}
        .connection-status {{ font-weight: bold; font-size: 14px; }}
        .connection-detail {{ font-size: 12px; color: var(--muted); }}
        .system-health {{ border: 1px solid var(--border); padding: 10px 16px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; cursor: pointer; text-decoration: none; color: inherit; }}
        .system-health:hover {{ border-color: var(--border-strong); }}
        .health-indicator {{ width: 9px; height: 9px; border-radius: 50%; border: 1px solid var(--border-strong); flex-shrink: 0; background: transparent; }}
        .health-indicator.healthy {{ background: var(--fg); }}
        .health-indicator.degraded {{ background: var(--fg); opacity: 0.4; }}
        .health-indicator.unhealthy {{ background: var(--fg); animation: blink 1s ease-in-out infinite; }}
        @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.15; }} }}
        .health-text {{ font-size: 13px; flex: 1; }}
        .health-summary {{ display: flex; gap: 12px; font-size: 12px; color: var(--muted); }}
        .health-item {{ display: flex; align-items: center; gap: 4px; }}
        .health-item-dot {{ width: 6px; height: 6px; border-radius: 50%; border: 1px solid var(--muted); background: transparent; }}
        .health-item-dot.ok {{ background: var(--fg); border-color: var(--fg); }}
        .health-item-dot.warn {{ background: var(--fg); opacity: 0.4; border-color: var(--fg); }}
        .health-item-dot.err {{ background: var(--fg); border-color: var(--fg); animation: blink 1s ease-in-out infinite; }}
        .filters {{ display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }}
        .filters select, .filters input {{ background: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: 8px 12px; font-family: inherit; font-size: 14px; }}
        .filters select {{ min-width: 120px; }}
        .filters input {{ flex: 1; min-width: 150px; }}
        .filters select:focus, .filters input:focus {{ outline: none; border-color: var(--border-strong); }}
        .app-stats {{ margin-bottom: 20px; }}
        .app-stats table {{ font-size: 14px; width: 100%; border-collapse: collapse; border: 1px solid var(--border); }}
        .app-stats th, .app-stats td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        .app-stats th {{ font-size: 11px; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--border-strong); }}
        h2 {{ font-size: 14px; margin: 24px 0 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); font-weight: normal; }}

        /* Desktop table */
        .notif-table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--border); }}
        .notif-table th, .notif-table td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        .notif-table th {{ font-size: 11px; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--border-strong); }}
        .notif-table tr.notif-row {{ cursor: pointer; }}
        .notif-table tr.notif-row:hover {{ background: var(--fg); color: var(--bg); }}
        .notif-table tr.notif-row:hover .body-cell {{ color: var(--bg); }}
        .action-sent::before {{ content: "✓ "; }}
        .action-dropped::before {{ content: "✗ "; }}
        .action-rate_limited::before {{ content: "» "; }}
        .badge-duplicate {{ border: 1px solid currentColor; font-size: 10px; padding: 1px 5px; margin-left: 6px; text-transform: uppercase; }}
        .truncate {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .body-cell {{ color: var(--muted); }}
        .feedback {{ display: flex; gap: 5px; }}
        .feedback button {{ padding: 4px 8px; border: 1px solid var(--border); background: var(--bg); color: var(--fg); cursor: pointer; font-size: 13px; font-family: inherit; }}
        .feedback .wrong:hover {{ background: var(--fg); color: var(--bg); }}
        .feedback .wrong.selected {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}

        /* Expanded row */
        .notif-expanded {{ display: none; }}
        .notif-expanded.show {{ display: table-row; }}
        .notif-expanded td {{ padding: 15px; border-top: 1px dashed var(--border); }}
        .notif-detail {{ display: grid; gap: 10px; }}
        .notif-detail-row {{ display: flex; gap: 10px; }}
        .notif-detail-label {{ font-size: 11px; color: var(--dim); text-transform: uppercase; min-width: 60px; }}
        .notif-detail-value {{ font-size: 13px; word-break: break-word; }}

        /* Mobile cards */
        .notif-cards {{ display: none; }}
        .notif-card {{ border: 1px solid var(--border); padding: 12px; margin-bottom: 10px; cursor: pointer; }}
        .notif-card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .notif-card-app {{ font-weight: bold; font-size: 14px; }}
        .notif-card-time {{ font-size: 12px; color: var(--muted); }}
        .notif-card-title {{ font-size: 14px; margin-bottom: 4px; }}
        .notif-card-body {{ font-size: 13px; color: var(--muted); margin-bottom: 8px; }}
        .notif-card-body.truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .notif-card-body.expanded {{ white-space: normal; word-break: break-word; }}
        .notif-card-footer {{ display: flex; justify-content: space-between; align-items: center; }}
        .notif-card-action {{ font-size: 12px; font-weight: bold; }}
        .notif-card-reason {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}
        .notif-card-reason.truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }}
        .notif-card-reason.expanded {{ white-space: normal; word-break: break-word; max-width: none; }}

        /* Insights panel */
        .insights {{ border: 1px solid var(--border); padding: 16px; margin-bottom: 20px; }}
        .insights-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .insights-header h3 {{ margin: 0; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; font-weight: normal; color: var(--muted); }}
        .insights-stats {{ font-size: 12px; color: var(--muted); }}
        .insights-empty {{ color: var(--dim); font-size: 13px; text-align: center; padding: 20px; }}
        .suggestion {{ border: 1px solid var(--border); padding: 12px; margin-bottom: 8px; }}
        .suggestion:last-child {{ margin-bottom: 0; }}
        .suggestion-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .suggestion-type {{ font-size: 11px; text-transform: uppercase; font-weight: bold; padding: 1px 6px; border: 1px solid currentColor; }}
        .suggestion-type.drop::before {{ content: "✗ "; }}
        .suggestion-type.send::before {{ content: "✓ "; }}
        .suggestion-app {{ font-size: 12px; color: var(--muted); }}
        .suggestion-pattern {{ font-size: 14px; margin-bottom: 4px; }}
        .suggestion-reason {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
        .suggestion-rule {{ font-family: inherit; font-size: 11px; border: 1px dashed var(--border); padding: 8px; white-space: pre; overflow-x: auto; }}
        .suggestion-actions {{ display: flex; gap: 8px; margin-top: 8px; }}
        .suggestion-copy, .suggestion-dismiss, .suggestion-add {{ font-size: 11px; font-family: inherit; background: var(--bg); color: var(--fg); border: 1px solid var(--border); padding: 4px 8px; cursor: pointer; text-transform: uppercase; }}
        .suggestion-copy:hover, .suggestion-dismiss:hover, .suggestion-add:hover {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}

        /* Rules panel */
        .rules-panel {{ border: 1px solid var(--border); padding: 16px; margin-bottom: 20px; }}
        .rules-filter {{ margin-bottom: 12px; }}
        .rules-filter select {{ background: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: 6px 10px; font-family: inherit; }}
        .rule-item {{ display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--border); margin-bottom: 6px; flex-wrap: wrap; }}
        .rule-app {{ font-weight: bold; min-width: 80px; color: var(--muted); }}
        .rule-matcher {{ color: var(--muted); }}
        .rule-value {{ color: var(--fg); flex: 1; min-width: 150px; word-break: break-all; }}
        .rule-action {{ font-size: 12px; font-weight: bold; padding: 1px 8px; border: 1px solid currentColor; text-transform: uppercase; }}
        .rule-action.send::before {{ content: "✓ "; }}
        .rule-action.drop::before {{ content: "✗ "; }}
        .rule-action.llm::before {{ content: "† "; }}
        .rule-default {{ opacity: 0.6; font-style: italic; }}
        .rule-delete {{ background: var(--bg); color: var(--fg); border: 1px solid var(--border); padding: 4px 8px; cursor: pointer; font-size: 11px; font-family: inherit; text-transform: uppercase; }}
        .rule-delete:hover {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
        .rule-priority {{ font-size: 10px; border: 1px solid currentColor; padding: 1px 6px; text-transform: uppercase; }}
        .ai-button {{ background: var(--bg); color: var(--fg); border: 1px solid var(--border-strong); padding: 8px 16px; cursor: pointer; font-size: 13px; font-family: inherit; text-transform: uppercase; letter-spacing: 0.5px; }}
        .ai-button:hover {{ background: var(--fg); color: var(--bg); }}
        .ai-button:disabled {{ opacity: 0.4; cursor: not-allowed; }}
        .ai-analysis {{ border: 1px solid var(--border); padding: 16px; margin-top: 12px; white-space: pre-wrap; font-size: 13px; line-height: 1.5; max-height: 400px; overflow-y: auto; }}
        .ai-analysis code {{ border: 1px solid var(--border); padding: 2px 6px; }}
        .ai-analysis pre {{ border: 1px solid var(--border); padding: 12px; overflow-x: auto; }}

        @media (max-width: 768px) {{
            body {{ padding: 12px; }}
            .notif-table {{ display: none; }}
            .notif-cards {{ display: block; }}
            .stat {{ padding: 10px 12px; }}
            .stat-value {{ font-size: 18px; }}
            .app-stats {{ display: none; }}
            .insights-header {{ flex-direction: column; gap: 8px; align-items: flex-start; }}
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

    <a href="/status" class="system-health" id="system-health">
        <div id="health-dot" class="health-indicator"></div>
        <span id="health-text" class="health-text">Checking system...</span>
        <div id="health-summary" class="health-summary"></div>
    </a>

    <div class="stats" onclick="toggleAppStats()" style="cursor: pointer;">
        <div class="stat"><div id="stat-total" class="stat-value">{total}</div><div class="stat-label">Total</div></div>
        <div class="stat sent"><div id="stat-sent" class="stat-value">{sent}</div><div class="stat-label">Sent</div></div>
        <div class="stat dropped"><div id="stat-dropped" class="stat-value">{dropped}</div><div class="stat-label">Dropped</div></div>
        <div class="stat rate_limited"><div id="stat-rate-limited" class="stat-value">{rate_limited}</div><div class="stat-label">Rate Lim</div></div>
    </div>
    <div id="app-stats-panel" class="app-stats" style="display: none;">
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

    <div style="margin-bottom: 20px; display: flex; gap: 10px;">
        <a href="/rules" class="ai-button" style="text-decoration: none;">Manage Rules</a>
        <a href="/status" class="ai-button" style="text-decoration: none;">System Status</a>
        <a href="/debug" class="ai-button" style="text-decoration: none;">Logs</a>
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
        let appStatsVisible = false;

        function toggleAppStats() {{
            appStatsVisible = !appStatsVisible;
            document.getElementById('app-stats-panel').style.display = appStatsVisible ? 'block' : 'none';
        }}

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

        async function refreshSystemHealth() {{
            try {{
                const resp = await fetch('/api/status');
                const data = await resp.json();

                // Count statuses
                const all = [...data.core, ...data.external, ...data.sinks];
                const healthy = all.filter(s => s.status === 'Healthy').length;
                const degraded = all.filter(s => s.status === 'Degraded').length;
                const unhealthy = all.filter(s => s.status === 'Unhealthy').length;
                const active = all.filter(s => s.status !== 'Disabled').length;

                // Determine overall status
                let overallStatus = 'healthy';
                let statusText = 'All Systems Operational';
                if (unhealthy > 0) {{
                    overallStatus = 'unhealthy';
                    statusText = `${{unhealthy}} system${{unhealthy > 1 ? 's' : ''}} down`;
                }} else if (degraded > 0) {{
                    overallStatus = 'degraded';
                    statusText = `${{degraded}} system${{degraded > 1 ? 's' : ''}} degraded`;
                }}

                document.getElementById('health-dot').className = 'health-indicator ' + overallStatus;
                document.getElementById('health-text').textContent = statusText;

                // Build summary items
                const items = [];
                const addItem = (name, status) => {{
                    const dotClass = status === 'Healthy' ? 'ok' : status === 'Degraded' ? 'warn' : status === 'Unhealthy' ? 'err' : 'ok';
                    items.push(`<span class="health-item"><span class="health-item-dot ${{dotClass}}"></span>${{name}}</span>`);
                }};

                // Key services to show
                const pi = data.external.find(s => s.id === 'pi');
                const sms = data.external.find(s => s.id === 'sms_assistant');
                const ollama = data.core.find(s => s.id === 'ollama');
                const imsg = data.sinks.find(s => s.id === 'imessage');

                if (pi) addItem('Pi', pi.status);
                if (sms && sms.status !== 'Disabled') addItem('SMS', sms.status);
                if (ollama) addItem('LLM', ollama.status);
                if (imsg && imsg.status !== 'Disabled') addItem('iMsg', imsg.status);

                document.getElementById('health-summary').innerHTML = items.join('');
            }} catch (e) {{
                document.getElementById('health-dot').className = 'health-indicator degraded';
                document.getElementById('health-text').textContent = 'Status check failed';
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
                    contentEl.innerHTML = '<div class="insights-empty">No suggestions yet. Rate more notifications (mark wrong) to get rule suggestions.</div>';
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
        refreshSystemHealth();
        setInterval(refresh, 5000);
        setInterval(refreshInsights, 30000);
        setInterval(refreshSystemHealth, 10000);
    </script>
</body>
</html>
"""
