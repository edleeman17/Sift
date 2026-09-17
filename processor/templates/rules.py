"""Rules page HTML template."""

RULES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Rules - Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --bg: #000; --fg: #fff; --muted: #999; --dim: #666; --border: #333; --border-strong: #fff;
        }
        * { box-sizing: border-box; border-radius: 0 !important; }
        select { -webkit-appearance: none; -moz-appearance: none; appearance: none; background-image: linear-gradient(45deg, transparent 50%, var(--fg) 50%), linear-gradient(135deg, var(--fg) 50%, transparent 50%); background-position: calc(100% - 16px) center, calc(100% - 11px) center; background-size: 5px 5px, 5px 5px; background-repeat: no-repeat; padding-right: 28px !important; }
        body { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; margin: 0; padding: 20px; background: var(--bg); color: var(--fg); }
        h1 { margin: 0 0 20px; font-size: 22px; font-weight: normal; text-transform: uppercase; letter-spacing: 2px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid var(--border-strong); padding-bottom: 12px; }
        a.back { color: var(--fg); text-decoration: none; font-size: 14px; text-transform: none; letter-spacing: normal; }
        a.back:hover { text-decoration: underline; }
        .rules-filter { margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap; }
        .rules-filter select { background-color: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: 8px 12px; font-family: inherit; }
        .rule-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border: 1px solid var(--border); margin-bottom: 8px; flex-wrap: wrap; }
        .rule-app { font-weight: bold; min-width: 100px; color: var(--muted); }
        .rule-matcher { color: var(--muted); min-width: 120px; }
        .rule-value { color: var(--fg); flex: 1; min-width: 150px; word-break: break-all; }
        .rule-action { font-size: 12px; font-weight: bold; padding: 2px 10px; border: 1px solid currentColor; text-transform: uppercase; }
        .rule-action.send::before { content: "✓ "; }
        .rule-action.drop::before { content: "✗ "; }
        .rule-action.llm::before { content: "† "; }
        .rule-default { opacity: 0.8; }
        .default-action-select { background-color: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: 4px 8px; font-family: inherit; cursor: pointer; }
        .rule-global { border: 1px solid var(--border-strong); }
        .rule-global .rule-app { color: var(--fg); }
        .rule-delete { background: var(--bg); color: var(--fg); border: 1px solid var(--border); padding: 5px 10px; cursor: pointer; font-size: 12px; font-family: inherit; text-transform: uppercase; }
        .rule-delete:hover { background: var(--fg); color: var(--bg); border-color: var(--fg); }
        .rule-priority { font-size: 10px; border: 1px solid currentColor; padding: 1px 6px; text-transform: uppercase; }
        .rule-prompt { cursor: help; font-size: 14px; }
        .empty { color: var(--dim); text-align: center; padding: 40px; }

        /* Add rule form */
        .add-rule-form { border: 1px solid var(--border); padding: 16px; margin-bottom: 20px; }
        .add-rule-form h3 { margin: 0 0 12px; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; font-weight: normal; color: var(--muted); }
        .form-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
        .form-row input, .form-row select { background-color: var(--bg); border: 1px solid var(--border); color: var(--fg); padding: 8px 12px; font-family: inherit; font-size: 14px; }
        .form-row input { flex: 1; min-width: 150px; }
        .form-row select { min-width: 120px; }
        .form-row button { background: var(--bg); color: var(--fg); border: 1px solid var(--border-strong); padding: 8px 16px; cursor: pointer; font-size: 14px; font-family: inherit; text-transform: uppercase; letter-spacing: 0.5px; }
        .form-row button:hover { background: var(--fg); color: var(--bg); }
        .form-error { color: var(--fg); font-weight: bold; font-size: 12px; margin-top: 5px; }

        @media (max-width: 768px) {
            .rule-item { padding: 12px; }
            .rule-app { min-width: 70px; font-size: 13px; }
            .rule-matcher { min-width: 100px; font-size: 13px; }
        }
    </style>
</head>
<body>
    <h1><a href="/" class="back">← Dashboard</a> Rules</h1>

    <div class="add-rule-form">
        <h3>Add Rule</h3>
        <div class="form-row">
            <select id="new-app" onchange="toggleCustomApp()">
                <option value="">Select app...</option>
            </select>
            <input type="text" id="new-app-custom" placeholder="Custom app name" style="display: none;">
        </div>
        <div class="form-row">
            <select id="new-matcher">
                <option value="sender_contains">sender contains</option>
                <option value="sender_not_contains">sender not contains</option>
                <option value="body_contains">body contains</option>
                <option value="body_not_contains">body not contains</option>
                <option value="contains">contains (anywhere)</option>
                <option value="sender_regex">sender regex</option>
                <option value="body_regex">body regex</option>
                <option value="regex">regex (anywhere)</option>
            </select>
            <input type="text" id="new-value" placeholder="Match text">
        </div>
        <div class="form-row">
            <select id="new-action">
                <option value="send">send</option>
                <option value="drop">drop</option>
            </select>
            <select id="new-priority">
                <option value="">Priority: default</option>
                <option value="high">Priority: high</option>
                <option value="critical">Priority: critical</option>
            </select>
            <button onclick="addRule()">Add Rule</button>
        </div>
        <div id="form-error" class="form-error"></div>
    </div>

    <div class="rules-filter">
        <select id="rules-app-filter"><option value="">All Apps</option></select>
    </div>

    <div id="rules-content">Loading...</div>

    <script>
        const esc = s => (s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        let allRules = [];

        async function refreshRules() {
            try {
                const resp = await fetch('/api/rules');
                const data = await resp.json();
                allRules = data.rules;

                const apps = [...new Set(allRules.map(r => r.app))].sort();

                // Populate filter dropdown
                const filterEl = document.getElementById('rules-app-filter');
                const current = filterEl.value;
                filterEl.innerHTML = '<option value="">All Apps</option>' +
                    apps.map(a => `<option value="${a}">${a}</option>`).join('');
                filterEl.value = current;

                // Populate add-rule app dropdown
                const appSelect = document.getElementById('new-app');
                const currentApp = appSelect.value;
                appSelect.innerHTML = '<option value="">Select app...</option>' +
                    '<option value="__global__">[GLOBAL] all apps</option>' +
                    apps.filter(a => a !== '__global__').map(a => `<option value="${a}">${a}</option>`).join('') +
                    '<option value="__other__">Other (custom)...</option>';
                appSelect.value = currentApp;

                renderRules();
            } catch (e) {
                console.error('Rules refresh failed:', e);
            }
        }

        function toggleCustomApp() {
            const appSelect = document.getElementById('new-app');
            const customInput = document.getElementById('new-app-custom');
            if (appSelect.value === '__other__') {
                customInput.style.display = 'block';
                customInput.focus();
            } else {
                customInput.style.display = 'none';
                customInput.value = '';
            }
        }

        function renderRules() {
            const filter = document.getElementById('rules-app-filter').value;
            const filtered = filter ? allRules.filter(r => r.app === filter) : allRules;

            const contentEl = document.getElementById('rules-content');
            if (filtered.length === 0) {
                contentEl.innerHTML = '<div class="empty">No rules configured.</div>';
                return;
            }

            contentEl.innerHTML = filtered.map(r => {
                const isGlobal = r.app === '__global__';
                const appDisplay = isGlobal ? '[GLOBAL]' : esc(r.app);
                const itemClass = isGlobal ? 'rule-item rule-global' : 'rule-item';

                if (r.type === 'default') {
                    return `<div class="rule-item rule-default" data-app="${esc(r.app)}">
                        <span class="rule-app">${esc(r.app)}</span>
                        <span class="rule-matcher">default</span>
                        <span class="rule-value"></span>
                        <select class="default-action-select" data-app="${esc(r.app)}" onchange="changeDefault('${esc(r.app)}', this.value)">
                            <option value="drop" ${r.action === 'drop' ? 'selected' : ''}>drop</option>
                            <option value="send" ${r.action === 'send' ? 'selected' : ''}>send</option>
                        </select>
                    </div>`;
                }
                return `<div class="${itemClass}" data-app="${esc(r.app)}" data-index="${r.index}">
                    <span class="rule-app">${appDisplay}</span>
                    <span class="rule-matcher">${r.matcher.replace(/_/g, ' ')}</span>
                    <span class="rule-value">"${esc(r.value)}"</span>
                    <span class="rule-action ${r.action}">${r.action}</span>
                    ${r.priority ? `<span class="rule-priority">${r.priority}</span>` : ''}
                    ${r.prompt ? `<span class="rule-prompt" title="${esc(r.prompt)}">[i]</span>` : ''}
                    <button class="rule-delete">Delete</button>
                </div>`;
            }).join('');
        }

        async function changeDefault(app, action) {
            await fetch('/api/rules/default', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({app, action})
            });
            refreshRules();
        }

        async function addRule() {
            const appSelect = document.getElementById('new-app').value;
            const appCustom = document.getElementById('new-app-custom').value.trim().toLowerCase();
            const app = appSelect === '__other__' ? appCustom : appSelect;
            const matcher = document.getElementById('new-matcher').value;
            const value = document.getElementById('new-value').value.trim();
            const action = document.getElementById('new-action').value;
            const priority = document.getElementById('new-priority').value;
            const errorEl = document.getElementById('form-error');

            if (!app || !value) {
                errorEl.textContent = 'App and match text are required';
                return;
            }

            errorEl.textContent = '';

            const body = {app, matcher, value, action};

            // Add priority if set
            if (priority) {
                body.priority = priority;
            }

            const resp = await fetch('/api/rules', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });

            if (resp.ok) {
                document.getElementById('new-app').value = '';
                document.getElementById('new-app-custom').value = '';
                document.getElementById('new-app-custom').style.display = 'none';
                document.getElementById('new-value').value = '';
                document.getElementById('new-action').value = 'send';
                document.getElementById('new-priority').value = '';
                refreshRules();
            } else {
                const data = await resp.json();
                errorEl.textContent = data.error || 'Failed to add rule';
            }
        }

        document.getElementById('rules-content').addEventListener('click', async (e) => {
            if (!e.target.classList.contains('rule-delete')) return;
            if (!confirm('Delete this rule?')) return;

            const item = e.target.closest('.rule-item');
            const app = item.dataset.app;
            const index = parseInt(item.dataset.index);

            await fetch('/api/rules', {
                method: 'DELETE',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({app, index})
            });
            refreshRules();
        });

        document.getElementById('rules-app-filter').addEventListener('change', renderRules);

        refreshRules();
    </script>
</body>
</html>
"""
