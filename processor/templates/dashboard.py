"""Dashboard HTML template."""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {{
            --bg-base: #08090b; --bg-surface: #0f1116; --bg-elevated: #14171f; --bg-inset: #05060a;
            --rule: #1c2330; --rule-strong: #2a3340;
            --fg-primary: #e8e6e1; --fg-secondary: #8b94a3; --fg-muted: #4d5560; --fg-dim: #353c47;
            --accent-live: #9fffb0; --accent-live-rgb: 159,255,176;
            --accent-cool: #6cd5ff;
            --accent-warn: #ffb86c; --accent-warn-rgb: 255,184,108;
            --accent-success: #4ade80;
            --accent-steel: #7aa9c4;
            --accent-signoff: #c4a1ff;
            --danger: #ff8a7a; --danger-rgb: 255,138,122;
            --fs-xs: 11px; --fs-sm: 12px; --fs-base: 13px; --fs-md: 14px; --fs-lg: 16px; --fs-display: 20px;
            --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            --gap-1: 4px; --gap-2: 8px; --gap-3: 12px; --gap-4: 16px; --gap-5: 24px; --gap-6: 32px;
            --t-fast: 120ms; --t-med: 160ms; --ease-out: cubic-bezier(0.2, 0.7, 0.2, 1);
        }}
        @media (prefers-color-scheme: light) {{
            :root:not([data-theme="dark"]) {{
                --bg-base: #f7f7f5; --bg-surface: #ffffff; --bg-elevated: #ececea; --bg-inset: #ecece9;
                --rule: #d8d8d4; --rule-strong: #b8b8b3;
                --fg-primary: #1a1a18; --fg-secondary: #55565c; --fg-muted: #8a8b8f; --fg-dim: #b4b5b8;
                --accent-live: #0f9d58; --accent-live-rgb: 15,157,88;
                --accent-cool: #0b6fb0;
                --accent-warn: #b26a00; --accent-warn-rgb: 178,106,0;
                --accent-success: #157f3b;
                --accent-steel: #3d6a86;
                --accent-signoff: #6b3fb0;
                --danger: #cf3b2e; --danger-rgb: 207,59,46;
            }}
        }}
        * {{ box-sizing: border-box; border-radius: 0 !important; }}
        select {{ -webkit-appearance: none; -moz-appearance: none; appearance: none; background-image: linear-gradient(45deg, transparent 50%, var(--fg-primary) 50%), linear-gradient(135deg, var(--fg-primary) 50%, transparent 50%); background-position: calc(100% - 16px) center, calc(100% - 11px) center; background-size: 5px 5px, 5px 5px; background-repeat: no-repeat; padding-right: 28px !important; }}
        button:focus-visible, a:focus-visible, select:focus-visible, input:focus-visible {{ outline: 2px solid var(--accent-cool); outline-offset: 1px; }}
        body {{ font-family: var(--font-mono); margin: 0; padding: 20px; background: var(--bg-base); color: var(--fg-primary); }}
        h1 {{ margin: 0 0 20px; font-size: var(--fs-display); font-weight: normal; text-transform: uppercase; letter-spacing: 2px; border-bottom: 1px solid var(--rule-strong); padding-bottom: 12px; }}
        a {{ color: var(--fg-primary); }}
        .stats {{ display: flex; gap: 0; margin-bottom: 20px; flex-wrap: wrap; border: 1px solid var(--rule); background: var(--bg-surface); }}
        .stat {{ padding: var(--gap-3) var(--gap-4); min-width: 80px; flex: 1; border-right: 1px solid var(--rule); }}
        .stat:last-child {{ border-right: none; }}
        .stat-value {{ font-size: var(--fs-display); font-weight: 700; font-variant-numeric: tabular-nums; }}
        .stat-label {{ font-size: var(--fs-xs); color: var(--fg-secondary); text-transform: uppercase; letter-spacing: 1px; }}
        .stat.sent .stat-value {{ color: var(--accent-success); }}
        .stat.dropped .stat-value {{ color: var(--danger); }}
        .stat.rate_limited .stat-value {{ color: var(--accent-warn); }}
        .connection {{ border: 1px solid var(--rule); background: var(--bg-surface); padding: var(--gap-3) var(--gap-4); margin-bottom: 20px; display: flex; align-items: center; gap: var(--gap-3); }}
        .connection-dot {{ width: 10px; height: 10px; border: 1px solid var(--fg-muted); flex-shrink: 0; background: transparent; }}
        .connection-dot.connected {{ background: var(--accent-live); border-color: var(--accent-live); animation: live-pulse 2s var(--ease-out) infinite; }}
        .connection-dot.disconnected {{ background: transparent; border-color: var(--danger); }}
        .connection-dot.unknown {{ background: transparent; border-color: var(--accent-warn); }}
        @keyframes live-pulse {{
            0%, 100% {{ box-shadow: 0 0 0 0 rgba(var(--accent-live-rgb), 0.0); }}
            50%      {{ box-shadow: 0 0 0 4px rgba(var(--accent-live-rgb), 0.28); }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            .connection-dot.connected {{ animation: none; box-shadow: 0 0 0 2px rgba(var(--accent-live-rgb), 0.34); }}
        }}
        .connection-info {{ display: flex; flex-direction: column; }}
        .connection-status {{ font-weight: bold; font-size: var(--fs-md); }}
        .connection-detail {{ font-size: var(--fs-sm); color: var(--fg-secondary); }}
        .system-health {{ border: 1px solid var(--rule); background: var(--bg-surface); padding: 10px var(--gap-4); margin-bottom: 20px; display: flex; align-items: center; gap: var(--gap-3); cursor: pointer; text-decoration: none; color: inherit; transition: background var(--t-fast) var(--ease-out); }}
        .system-health:hover {{ background: var(--bg-elevated); }}
        .health-indicator {{ width: 9px; height: 9px; border: 1px solid var(--fg-muted); flex-shrink: 0; background: transparent; }}
        .health-indicator.healthy {{ background: var(--accent-success); border-color: var(--accent-success); }}
        .health-indicator.degraded {{ background: var(--accent-warn); border-color: var(--accent-warn); }}
        .health-indicator.unhealthy {{ background: var(--danger); border-color: var(--danger); animation: danger-blink 1s ease-in-out infinite; }}
        @keyframes danger-blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
        @media (prefers-reduced-motion: reduce) {{
            .health-indicator.unhealthy, .health-item-dot.err {{ animation: none; box-shadow: 0 0 0 2px rgba(var(--danger-rgb), 0.34); }}
        }}
        .health-text {{ font-size: var(--fs-base); flex: 1; }}
        .health-summary {{ display: flex; gap: var(--gap-3); font-size: var(--fs-sm); color: var(--fg-secondary); }}
        .health-item {{ display: flex; align-items: center; gap: 4px; }}
        .health-item-dot {{ width: 6px; height: 6px; border: 1px solid var(--fg-muted); background: transparent; }}
        .health-item-dot.ok {{ background: var(--accent-success); border-color: var(--accent-success); }}
        .health-item-dot.warn {{ background: var(--accent-warn); border-color: var(--accent-warn); }}
        .health-item-dot.err {{ background: var(--danger); border-color: var(--danger); animation: danger-blink 1s ease-in-out infinite; }}
        .filters {{ display: flex; gap: var(--gap-2); margin-bottom: 15px; flex-wrap: wrap; }}
        .filters select, .filters input {{ background-color: var(--bg-inset); border: 1px solid var(--rule); color: var(--fg-primary); padding: 8px 12px; font-family: inherit; font-size: var(--fs-md); }}
        .filters select {{ min-width: 120px; }}
        .filters input {{ flex: 1; min-width: 150px; }}
        .filters select:focus, .filters input:focus {{ outline: none; border-color: var(--accent-cool); }}
        .app-stats {{ margin-bottom: 20px; }}
        .app-stats table {{ font-size: var(--fs-md); width: 100%; border-collapse: collapse; border: 1px solid var(--rule); background: var(--bg-surface); }}
        .app-stats th, .app-stats td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--rule); }}
        .app-stats th {{ font-size: var(--fs-xs); text-transform: uppercase; color: var(--fg-secondary); border-bottom: 1px solid var(--rule-strong); }}
        h2 {{ font-size: var(--fs-md); margin: 24px 0 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--fg-secondary); font-weight: normal; }}

        /* Desktop table */
        .notif-table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--rule); background: var(--bg-surface); }}
        .notif-table th, .notif-table td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--rule); }}
        .notif-table th {{ font-size: var(--fs-xs); text-transform: uppercase; color: var(--fg-secondary); border-bottom: 1px solid var(--rule-strong); }}
        .notif-table tr.notif-row {{ cursor: pointer; transition: background var(--t-fast) var(--ease-out); }}
        .notif-table tr.notif-row:hover {{ background: var(--bg-elevated); }}
        .action-sent {{ color: var(--accent-success); }}
        .action-dropped {{ color: var(--danger); }}
        .action-rate_limited {{ color: var(--accent-warn); }}
        .action-sent::before {{ content: "✓ "; }}
        .action-dropped::before {{ content: "✗ "; }}
        .action-rate_limited::before {{ content: "» "; }}
        .badge-duplicate {{ border: 1px solid var(--fg-muted); color: var(--fg-muted); font-size: 10px; padding: 1px 5px; margin-left: 6px; text-transform: uppercase; }}
        .truncate {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .body-cell {{ color: var(--fg-secondary); }}
        .feedback {{ display: flex; gap: 5px; }}
        .feedback button {{ padding: 4px 8px; border: 1px solid var(--rule); background: var(--bg-surface); color: var(--fg-primary); cursor: pointer; font-size: var(--fs-base); font-family: inherit; transition: background var(--t-fast) var(--ease-out), color var(--t-fast) var(--ease-out), border-color var(--t-fast) var(--ease-out); }}
        .feedback .wrong:hover {{ background: var(--bg-elevated); color: var(--accent-signoff); border-color: var(--accent-signoff); }}
        .feedback .wrong.selected {{ background: var(--accent-signoff); color: var(--bg-base); border-color: var(--accent-signoff); font-weight: 700; }}

        /* Expanded row */
        .notif-expanded {{ display: none; }}
        .notif-expanded.show {{ display: table-row; }}
        .notif-expanded td {{ padding: 15px; border-top: 1px dashed var(--rule); background: var(--bg-inset); }}
        .notif-detail {{ display: grid; gap: 10px; }}
        .notif-detail-row {{ display: flex; gap: 10px; }}
        .notif-detail-label {{ font-size: var(--fs-xs); color: var(--fg-muted); text-transform: uppercase; min-width: 60px; }}
        .notif-detail-value {{ font-size: var(--fs-base); word-break: break-word; }}

        /* Mobile cards */
        .notif-cards {{ display: none; }}
        .notif-card {{ border: 1px solid var(--rule); background: var(--bg-surface); padding: 12px; margin-bottom: 10px; cursor: pointer; }}
        .notif-card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .notif-card-app {{ font-weight: bold; font-size: var(--fs-md); }}
        .notif-card-time {{ font-size: var(--fs-sm); color: var(--fg-secondary); }}
        .notif-card-title {{ font-size: var(--fs-md); margin-bottom: 4px; }}
        .notif-card-body {{ font-size: var(--fs-base); color: var(--fg-secondary); margin-bottom: 8px; }}
        .notif-card-body.truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .notif-card-body.expanded {{ white-space: normal; word-break: break-word; }}
        .notif-card-footer {{ display: flex; justify-content: space-between; align-items: center; }}
        .notif-card-action {{ font-size: var(--fs-sm); font-weight: bold; }}
        .notif-card-reason {{ font-size: var(--fs-xs); color: var(--fg-secondary); margin-top: 4px; }}
        .notif-card-reason.truncate {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }}
        .notif-card-reason.expanded {{ white-space: normal; word-break: break-word; max-width: none; }}

        /* Insights panel */
        .insights {{ border: 1px solid var(--rule); background: var(--bg-surface); padding: var(--gap-4); margin-bottom: 20px; }}
        .insights-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .insights-header h3 {{ margin: 0; font-size: var(--fs-base); text-transform: uppercase; letter-spacing: 1px; font-weight: normal; color: var(--fg-secondary); }}
        .insights-stats {{ font-size: var(--fs-sm); color: var(--fg-secondary); }}
        .insights-empty {{ color: var(--fg-muted); font-size: var(--fs-base); text-align: center; padding: 20px; }}
        .suggestion {{ border: 1px solid var(--rule); background: var(--bg-inset); padding: 12px; margin-bottom: 8px; }}
        .suggestion:last-child {{ margin-bottom: 0; }}
        .suggestion-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .suggestion-type {{ font-size: var(--fs-xs); text-transform: uppercase; font-weight: bold; padding: 1px 6px; border: 1px solid currentColor; }}
        .suggestion-type.drop {{ color: var(--danger); }}
        .suggestion-type.send {{ color: var(--accent-success); }}
        .suggestion-type.drop::before {{ content: "✗ "; }}
        .suggestion-type.send::before {{ content: "✓ "; }}
        .suggestion-app {{ font-size: var(--fs-sm); color: var(--fg-secondary); }}
        .suggestion-pattern {{ font-size: var(--fs-md); margin-bottom: 4px; }}
        .suggestion-reason {{ font-size: var(--fs-sm); color: var(--fg-secondary); margin-bottom: 8px; }}
        .suggestion-rule {{ font-family: inherit; font-size: var(--fs-xs); border: 1px dashed var(--rule); padding: 8px; white-space: pre; overflow-x: auto; color: var(--fg-secondary); }}
        .suggestion-actions {{ display: flex; gap: var(--gap-2); margin-top: 8px; }}
        .suggestion-copy, .suggestion-dismiss, .suggestion-add {{ font-size: var(--fs-xs); font-family: inherit; background: var(--bg-surface); color: var(--fg-primary); border: 1px solid var(--rule-strong); padding: 4px 8px; cursor: pointer; text-transform: uppercase; transition: background var(--t-fast) var(--ease-out); }}
        .suggestion-add {{ color: var(--accent-success); border-color: var(--accent-success); }}
        .suggestion-copy:hover, .suggestion-dismiss:hover {{ background: var(--bg-elevated); }}
        .suggestion-add:hover {{ background: var(--bg-elevated); }}

        /* Rules panel */
        .rules-panel {{ border: 1px solid var(--rule); background: var(--bg-surface); padding: var(--gap-4); margin-bottom: 20px; }}
        .rules-filter {{ margin-bottom: 12px; }}
        .rules-filter select {{ background-color: var(--bg-inset); border: 1px solid var(--rule); color: var(--fg-primary); padding: 6px 10px; font-family: inherit; }}
        .rule-item {{ display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--rule); background: var(--bg-surface); margin-bottom: 6px; flex-wrap: wrap; }}
        .rule-app {{ font-weight: bold; min-width: 80px; color: var(--fg-secondary); }}
        .rule-matcher {{ color: var(--fg-secondary); }}
        .rule-value {{ color: var(--fg-primary); flex: 1; min-width: 150px; word-break: break-all; }}
        .rule-action {{ font-size: var(--fs-sm); font-weight: bold; padding: 1px 8px; border: 1px solid currentColor; text-transform: uppercase; }}
        .rule-action.send {{ color: var(--accent-success); }}
        .rule-action.drop {{ color: var(--danger); }}
        .rule-action.llm {{ color: var(--accent-steel); border-style: dashed; }}
        .rule-action.send::before {{ content: "✓ "; }}
        .rule-action.drop::before {{ content: "✗ "; }}
        .rule-action.llm::before {{ content: "† "; }}
        .rule-default {{ opacity: 0.7; font-style: italic; }}
        .rule-delete {{ background: var(--bg-surface); color: var(--danger); border: 1px solid var(--rule); padding: 4px 8px; cursor: pointer; font-size: var(--fs-xs); font-family: inherit; text-transform: uppercase; transition: background var(--t-fast) var(--ease-out), border-color var(--t-fast) var(--ease-out); }}
        .rule-delete:hover {{ background: var(--bg-elevated); border-color: var(--danger); }}
        .rule-priority {{ font-size: 10px; border: 1px solid var(--fg-secondary); color: var(--fg-secondary); padding: 1px 6px; text-transform: uppercase; }}
        .rule-priority--high {{ border-color: var(--accent-warn); color: var(--accent-warn); }}
        .rule-priority--critical {{ border-color: var(--danger); color: var(--danger); }}
        .ai-button {{ background: var(--bg-surface); color: var(--fg-primary); border: 1px solid var(--rule-strong); padding: 8px 16px; cursor: pointer; font-size: var(--fs-base); font-family: inherit; text-transform: uppercase; letter-spacing: 0.5px; transition: background var(--t-fast) var(--ease-out); }}
        .ai-button:hover {{ background: var(--bg-elevated); }}

        @media (max-width: 768px) {{
            body {{ padding: 12px; }}
            .notif-table {{ display: none; }}
            .notif-cards {{ display: block; }}
            .stat {{ padding: 10px 12px; }}
            .stat-value {{ font-size: var(--fs-lg); }}
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
            <span class="insights-stats" id="insights-stats"></span>
        </div>
        <div id="insights-content">
            <div class="insights-empty">Loading insights...</div>
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
