"""Rules page HTML template."""

RULES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Rules - Sift</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: #e0e0e0; }
        h1 { margin: 0 0 20px; font-size: 24px; display: flex; align-items: center; gap: 15px; }
        a.back { color: #60a5fa; text-decoration: none; font-size: 14px; }
        a.back:hover { text-decoration: underline; }
        .rules-filter { margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap; }
        .rules-filter select { background: #2a2a2a; border: 1px solid #3a3a3a; color: #e0e0e0; padding: 8px 12px; border-radius: 6px; }
        .rule-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: #2a2a2a; border-radius: 6px; margin-bottom: 8px; flex-wrap: wrap; }
        .rule-app { font-weight: bold; min-width: 100px; color: #9ca3af; }
        .rule-matcher { color: #60a5fa; min-width: 120px; }
        .rule-value { color: #fbbf24; flex: 1; min-width: 150px; word-break: break-all; }
        .rule-action { font-size: 12px; font-weight: bold; padding: 3px 10px; border-radius: 4px; }
        .rule-action.send { background: #166534; color: white; }
        .rule-action.drop { background: #991b1b; color: white; }
        .rule-action.llm { background: #7c3aed; color: white; }
        .rule-default { opacity: 0.8; }
        .default-action-select { background: #333; border: 1px solid #555; color: #e0e0e0; padding: 4px 8px; border-radius: 4px; cursor: pointer; }
        .rule-global { background: #1e3a5f; border: 1px solid #3b82f6; }
        .rule-global .rule-app { color: #60a5fa; }
        .rule-delete { background: #dc2626; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .rule-delete:hover { background: #b91c1c; }
        .rule-priority { font-size: 10px; background: #f97316; color: white; padding: 2px 6px; border-radius: 3px; }
        .rule-prompt { cursor: help; font-size: 14px; }
        .empty { color: #666; text-align: center; padding: 40px; }

        /* Add rule form */
        .add-rule-form { background: #2a2a2a; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
        .add-rule-form h3 { margin: 0 0 12px; font-size: 14px; }
        .form-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
        .form-row input, .form-row select { background: #333; border: 1px solid #444; color: #e0e0e0; padding: 8px 12px; border-radius: 4px; font-size: 14px; }
        .form-row input { flex: 1; min-width: 150px; }
        .form-row select { min-width: 120px; }
        .form-row button { background: #166534; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .form-row button:hover { background: #15803d; }
        .form-error { color: #f87171; font-size: 12px; margin-top: 5px; }

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
            <select id="new-action" onchange="togglePrompt()">
                <option value="send">send</option>
                <option value="drop">drop</option>
                <option value="llm">llm</option>
            </select>
            <select id="new-priority">
                <option value="">Priority: default</option>
                <option value="high">Priority: high</option>
                <option value="critical">Priority: critical</option>
            </select>
            <button onclick="addRule()">Add Rule</button>
        </div>
        <div class="form-row" id="prompt-row" style="display: none;">
            <select id="new-prompt-type" onchange="toggleCustomPrompt()">
                <option value="default">Default LLM prompt</option>
                <option value="custom">Custom prompt</option>
            </select>
            <input type="text" id="new-prompt" placeholder="Custom prompt - must ask for SEND or DROP response" style="display: none;">
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
                    '<option value="__global__">⭐ Global (all apps)</option>' +
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
                const appDisplay = isGlobal ? '⭐ Global' : esc(r.app);
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
                    ${r.prompt ? `<span class="rule-prompt" title="${esc(r.prompt)}">📝</span>` : ''}
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

        function togglePrompt() {
            const action = document.getElementById('new-action').value;
            document.getElementById('prompt-row').style.display = action === 'llm' ? 'flex' : 'none';
        }

        function toggleCustomPrompt() {
            const type = document.getElementById('new-prompt-type').value;
            document.getElementById('new-prompt').style.display = type === 'custom' ? 'block' : 'none';
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

            // Add prompt if LLM action with custom prompt
            if (action === 'llm') {
                const promptType = document.getElementById('new-prompt-type').value;
                if (promptType === 'custom') {
                    const prompt = document.getElementById('new-prompt').value.trim();
                    if (prompt) body.prompt = prompt;
                }
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
                document.getElementById('new-prompt').value = '';
                document.getElementById('new-action').value = 'send';
                document.getElementById('new-priority').value = '';
                document.getElementById('new-prompt-type').value = 'default';
                togglePrompt();
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
