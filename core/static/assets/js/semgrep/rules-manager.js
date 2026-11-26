(function() {
window.loadSemgrepRules = async function() {
    const setsEl = document.getElementById('semgrep-rulesets-list');
    const customEl = document.getElementById('semgrep-custom-rules-list');

    if (!setsEl || !customEl) return;

    try {
        const res = await fetch('/api/semgrep/rules');
        const data = await res.json();

        const fmtSet = (rs) => {
            const id = String(rs?.id || '').trim();
            if (!id) return 'p/custom';
            if (id.startsWith('p/') || id.startsWith('r/')) return id;
            const known = {
                'owasp-top-ten': 'p/owasp-top-ten',
                'php-security': 'p/php',
                'security-audit': 'p/security-audit'
            };
            return known[id] || `p/${id}`;
        };
        const jsArg = (val) => JSON.stringify(String(val || ''));

        let setsHtml = `
            <div class="semgrep-section-head">
                <h3>SECURITY RULESETS</h3>
            </div>
            <div class="semgrep-ruleset-input-row">
                <input type="text" id="new-ruleset-id" placeholder="p/cwe-top-25 or p/owasp-top-ten">
                <button onclick="addSemgrepRuleset()" class="action-btn semgrep-outline-btn">ADD RULESET</button>
            </div>
        `;

        const cardHtml = (rs) => {
            const label = escapeHtml(fmtSet(rs));
            const rawId = escapeHtml(String(rs.id || ''));
            const link = escapeHtml(String(rs.url || '#'));
            const on = !!rs.enabled;
            const tip = on ? 'Set Disabled' : 'Set Active';
            return `
                <div class="semgrep-ruleset-card${on ? '' : ' is-disabled'}">
                    <div class="semgrep-ruleset-row">
                        <div class="semgrep-ruleset-meta">
                            <span class="semgrep-ruleset-id" title="${rawId}">${label}</span>
                            <a class="semgrep-ruleset-view" href="${link}" target="_blank" rel="noreferrer noopener">View ↗</a>
                        </div>
                        <div class="semgrep-card-actions">
                            <button onclick='toggleRuleset(${jsArg(rs.id)})' class="semgrep-mini-toggle${on ? ' is-on' : ''}" title="${tip}" aria-label="${tip}"></button>
                            ${rs.deletable ? `
                            <button onclick='deleteRuleset(${jsArg(rs.id)}, true)' class="action-btn semgrep-icon-btn semgrep-delete-btn" title="Delete Ruleset" aria-label="Delete Ruleset">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                            </button>` : ''}
                        </div>
                    </div>
                </div>
            `;
        };

        if (data.rulesets && data.rulesets.length > 0) {
            const coreIds = new Set(['owasp-top-ten', 'php-security', 'security-audit']);
            const core = data.rulesets.filter(rs => coreIds.has(String(rs.id || '').trim()));
            const extra = data.rulesets.filter(rs => !coreIds.has(String(rs.id || '').trim()));

            setsHtml += core.map(cardHtml).join('');

            if (extra.length > 0) {
                setsHtml += `<div style="margin-top: 12px; margin-bottom: 10px;">
                    <div class="semgrep-subgroup-label">Advanced / Extra Rulesets (${extra.length})</div>
                    ${extra.map(cardHtml).join('')}
                </div>`;
            }
        } else {
            setsHtml += '<div class="semgrep-empty">No rulesets found. Add one above (example: p/cwe-top-25).</div>';
        }

        const custom = data.custom_rules || [];
        const onCount = custom.filter(rule => rule.enabled).length;
        const allOn = custom.length > 0 && onCount === custom.length;
        const nextOn = !allOn;
        const btnText = allOn ? 'ALL OFF' : 'ALL ON';
        const onStyle = allOn
            ? 'background: rgba(255,0,85,0.1); color: #ff0055; border: 1px solid rgba(255,0,85,0.35);'
            : 'background: rgba(0,255,157,0.1); color: var(--accent-primary); border: 1px solid rgba(0,255,157,0.35);';
        const empty = custom.length === 0;
        const disAttr = empty ? 'disabled title="No custom rules to toggle"' : '';
        const btnStyle = empty
            ? 'opacity:0.6; cursor:not-allowed; border:1px solid #444; color:#777; background:rgba(90,90,90,0.1);'
            : onStyle;

        let customHtml = `<div class="semgrep-section-head">
                    <h3>CUSTOM RULES</h3>
                    <button
                        onclick="toggleAllCustomRules(${nextOn})"
                        class="action-btn semgrep-outline-btn ${allOn ? 'is-danger' : ''}"
                        style="${btnStyle}"
                        ${disAttr}
                    >${btnText}</button>
                </div>`;

        if (custom.length > 0) {
            customHtml += custom.map(rule => `
                <div class="semgrep-custom-card${!rule.enabled ? ' is-disabled' : ''}">
                    <div class="semgrep-custom-row">
                        <div class="semgrep-custom-meta">
                            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                                <span class="semgrep-custom-id">${escapeHtml(rule.id)}</span>
                                <span class="tag ${rule.severity === 'ERROR' ? 'risk' : (rule.severity === 'WARNING' ? 'warn' : '')}" style="font-size: 9px;">${escapeHtml(rule.severity)}</span>
                            </div>
                            <div class="semgrep-custom-message">${escapeHtml(rule.message)}</div>
                            <div class="semgrep-custom-pattern">
                                ${escapeHtml(rule.pattern || 'Multiple patterns')}
                            </div>
                        </div>
                        <div class="semgrep-card-actions">
                            <button onclick='toggleSemgrepRule(${jsArg(rule.id)})' class="semgrep-mini-toggle${rule.enabled ? ' is-on' : ''}" title="${rule.enabled ? 'Set Disabled' : 'Set Active'}" aria-label="Toggle rule status"></button>
                        </div>
                    </div>
                </div>
            `).join('');
        } else {
            customHtml += '<div class="semgrep-empty">No custom rules defined. Add one above.</div>';
        }

        setsEl.innerHTML = setsHtml;
        customEl.innerHTML = customHtml;
    } catch (err) {
        console.error('Error loading Semgrep rules:', err);
        const errHtml = `<div class="semgrep-empty" style="color: var(--accent-secondary);">Error loading rules: ${escapeHtml(err.message)}</div>`;
        setsEl.innerHTML = errHtml;
        customEl.innerHTML = errHtml;
    }
};

window.toggleRuleset = async function(rulesetId) {
    try {
        const response = await fetch(`/api/semgrep/rulesets/${encodeURIComponent(rulesetId)}/toggle`, {
            method: 'POST'
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            showToast('Failed to toggle ruleset: ' + (data.detail || data.error || `HTTP ${response.status}`), 'error');
            return;
        }

        if (data.success) {
            loadSemgrepRules();
        } else {
            showToast('Failed to toggle ruleset: ' + (data.detail || data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error toggling ruleset:', error);
        showToast('Error toggling ruleset: ' + (error.message || 'unknown error'), 'error');
    }
}

window.deleteRuleset = async function(rulesetId, deletable = true) {
    if (!deletable) {
        showToast('Built-in rulesets cannot be deleted. You can disable them with the toggle.', 'warn');
        return;
    }
    const confirmed = await showConfirm(`Delete ruleset "${rulesetId}"?`);
    if (!confirmed) return;
    try {
        const response = await fetch(`/api/semgrep/rulesets/${encodeURIComponent(rulesetId)}`, {
            method: 'DELETE'
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            showToast('Failed to delete ruleset: ' + (data.detail || data.error || `HTTP ${response.status}`), 'error');
            return;
        }
        if (data.success) {
            showToast(`Ruleset deleted: ${rulesetId}`, 'success');
            loadSemgrepRules();
        } else {
            showToast('Failed to delete ruleset: ' + (data.detail || data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error deleting ruleset:', error);
        showToast('Error deleting ruleset: ' + error.message, 'error');
    }
}

window.addSemgrepRuleset = async function() {
    const input = document.getElementById('new-ruleset-id');
    const ruleset = (input?.value || '').trim();

    if (!ruleset) {
        showToast('Please enter a ruleset (example: p/cwe-top-25).', 'warn');
        return;
    }

    if (!/^[a-zA-Z0-9_./:-]+$/.test(ruleset)) {
        showToast('Invalid ruleset format. Use values like p/cwe-top-25.', 'warn');
        return;
    }

    try {
        const response = await fetch('/api/semgrep/rulesets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ruleset })
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            showToast('Failed to add ruleset: ' + (data.detail || data.error || `HTTP ${response.status}`), 'error');
            return;
        }

        if (data.success) {
            if (input) input.value = '';
            showToast(`Ruleset added: ${ruleset}`, 'success');
            loadSemgrepRules();
        } else {
            showToast('Failed to add ruleset: ' + (data.detail || data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error adding ruleset: ' + error.message, 'error');
    }
}

window.toggleSemgrepRule = async function(ruleId) {
    try {
        const response = await fetch(`/api/semgrep/rules/${encodeURIComponent(ruleId)}/toggle`, {
            method: 'POST'
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            showToast('Failed to toggle rule: ' + (data.detail || data.error || `HTTP ${response.status}`), 'error');
            return;
        }

        if (data.success) {
            loadSemgrepRules();
        } else {
            showToast('Failed to toggle rule: ' + (data.detail || data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error toggling rule:', error);
        showToast('Error toggling rule: ' + (error.message || 'unknown error'), 'error');
    }
}

window.toggleAllCustomRules = async function(enabled) {
    try {
        const response = await fetch('/api/semgrep/rules/actions/toggle-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            showToast('Failed to update custom rules: ' + (data.detail || data.error || `HTTP ${response.status}`), 'error');
            return;
        }

        if (data.success) {
            showToast(
                `${enabled ? 'Enabled' : 'Disabled'} ${data.changed}/${data.total} custom rule(s)`,
                'success'
            );
            loadSemgrepRules();
        } else {
            showToast('Failed to update custom rules', 'error');
        }
    } catch (error) {
        showToast('Error updating custom rules: ' + (error.message || 'unknown error'), 'error');
    }
}

window.addSemgrepRule = async function() {
    const ruleId = document.getElementById('new-rule-id').value.trim();
    const pattern = document.getElementById('new-rule-pattern').value.trim();
    const message = document.getElementById('new-rule-message').value.trim();
    const severity = document.getElementById('new-rule-severity').value;

    if (!ruleId || !pattern || !message) {
        showToast('Please fill in all fields: Rule ID, Pattern, and Message.', 'warn');
        return;
    }


    if (!/^[a-zA-Z0-9_-]+$/.test(ruleId)) {
        showToast('Rule ID can only contain letters, numbers, hyphens, and underscores.', 'warn');
        return;
    }

    try {
        const response = await fetch('/api/semgrep/rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: ruleId,
                pattern: pattern,
                message: message,
                severity: severity,
                languages: ['php']
            })
        });

        const data = await response.json();

        if (data.success) {

            document.getElementById('new-rule-id').value = '';
            document.getElementById('new-rule-pattern').value = '';
            document.getElementById('new-rule-message').value = '';


            loadSemgrepRules();
        } else {
            showToast('Failed to add rule: ' + (data.detail || data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error adding rule: ' + error.message, 'error');
    }
}

})();
