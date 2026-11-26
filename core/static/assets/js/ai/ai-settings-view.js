(function() {
    const STATUS_KEY = 'zetatechAgent.aiSettings.testStatusByProfile';
    const PROVIDERS = {
        anthropic: {
            displayName: 'Anthropic',
            baseUrl: 'https://api.anthropic.com',
            modelHint: 'claude-sonnet-4-5',
            apiKeyPlaceholder: 'Enter Anthropic API key',
        },
        openai: {
            displayName: 'OpenAI / OpenAI-compatible',
            baseUrl: 'https://api.openai.com/v1',
            modelHint: 'gpt-4.1-mini',
            apiKeyPlaceholder: 'Enter OpenAI API key',
        },
        copilot: {
            displayName: 'GitHub Copilot',
            baseUrl: 'https://api.githubcopilot.com',
            modelHint: 'gpt-4o-mini',
            apiKeyPlaceholder: 'Enter GitHub token',
        },
        gemini: {
            displayName: 'Google Gemini',
            baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
            modelHint: 'gemini-2.5-pro',
            apiKeyPlaceholder: 'Enter Gemini API key',
        },
        grok: {
            displayName: 'xAI Grok',
            baseUrl: 'https://api.x.ai/v1',
            modelHint: 'grok-3-mini',
            apiKeyPlaceholder: 'Enter xAI API key',
        },
    };

    function defaults(provider) {
        return PROVIDERS[String(provider || 'anthropic').trim()] || PROVIDERS.anthropic;
    }

    function applyHints(provider, { preserveUrl = true } = {}) {
        const cfg = defaults(provider);
        const modelEl = document.getElementById('plugin-ai-model');
        const keyEl = document.getElementById('plugin-ai-api-key');
        const urlEl = document.getElementById('plugin-ai-base-url');
        const hintEl = document.getElementById('plugin-ai-api-key-saved-hint');
        if (modelEl) {
            modelEl.placeholder = `Type model name and press Enter — e.g. ${cfg.modelHint}`;
        }
        if (keyEl) {
            const ph = String(keyEl.dataset.savedPlaceholder || '').trim();
            keyEl.placeholder = ph || cfg.apiKeyPlaceholder;
        }
        if (hintEl) {
            const hint = String(hintEl.dataset.savedHint || '').trim();
            hintEl.textContent = hint;
            hintEl.style.display = hint ? 'block' : 'none';
        }
        if (urlEl) {
            urlEl.placeholder = `${cfg.baseUrl} or local compatible endpoint`;
            const cur = String(urlEl.value || '').trim();
            if (!preserveUrl || !cur) {
                urlEl.value = cur;
            }
        }
    }

    function getState() {
        window.aiSettingsViewState = window.aiSettingsViewState || {
            dashboard: null,
            selectedProfileKey: null,
            loading: false,
            testStatusByProfile: loadStatuses(),
            draftModels: [],
        };
        return window.aiSettingsViewState;
    }

    function loadStatuses() {
        try {
            const raw = window.localStorage?.getItem(STATUS_KEY);
            const parsed = raw ? JSON.parse(raw) : {};
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch (_) {
            return {};
        }
    }

    function saveStatuses() {
        try {
            window.localStorage?.setItem(
                STATUS_KEY,
                JSON.stringify(getState().testStatusByProfile || {})
            );
        } catch (_) {

        }
    }

    function setStatus(key, entry) {
        const id = String(key || '').trim();
        if (!id) return;
        const state = getState();
        state.testStatusByProfile = state.testStatusByProfile || {};
        state.testStatusByProfile[id] = entry;
        saveStatuses();
    }

    function delStatus(key) {
        const id = String(key || '').trim();
        if (!id) return;
        const state = getState();
        if (state.testStatusByProfile && Object.prototype.hasOwnProperty.call(state.testStatusByProfile, id)) {
            delete state.testStatusByProfile[id];
            saveStatuses();
        }
    }

    function pruneStatuses() {
        const keys = new Set(getProfiles().map((item) => String(item.profile_key || '')).filter(Boolean));
        const state = getState();
        const entries = state.testStatusByProfile || {};
        let changed = false;
        for (const key of Object.keys(entries)) {
            if (!keys.has(key)) {
                delete entries[key];
                changed = true;
            }
        }
        if (changed) saveStatuses();
    }

    function getProfiles() {
        return Array.isArray(getState().dashboard?.profiles)
            ? getState().dashboard.profiles
            : [];
    }

    function findProfile(key) {
        return getProfiles().find((item) => String(item.profile_key || '') === String(key || '')) || null;
    }

    function getModels() {
        return Array.isArray(getState().draftModels) ? getState().draftModels : [];
    }

    function setModels(models = []) {
        const uniq = [];
        for (const item of models) {
            const val = String(item || '').trim();
            if (!val || uniq.includes(val)) continue;
            uniq.push(val);
        }
        getState().draftModels = uniq;
        renderChips();
    }

    function addModel(model) {
        const val = String(model || '').trim();
        if (!val) return;
        setModels([...getModels(), val]);
    }

    function removeModel(model) {
        const val = String(model || '').trim();
        setModels(getModels().filter((item) => item !== val));
    }

    function renderChips() {
        const box = document.getElementById('ai-settings-model-chips');
        if (!box) return;
        const models = getModels();
        box.innerHTML = models.map((model) => `
            <span class="ai-settings-model-chip">
                <span>${escapeHtml(model)}</span>
                <button type="button" data-model-remove="${escapeHtml(model)}" aria-label="Remove model">×</button>
            </span>
        `).join('');
    }

    function maskKey(val) {
        const raw = String(val || '').trim();
        if (!raw) return 'No key saved';
        if (raw.length <= 8) return `${raw.slice(0, 2)}••••${raw.slice(-2)}`;
        return `${raw.slice(0, 6)}••••••${raw.slice(-4)}`;
    }

    function keySummary(profile) {
        if (profile?.api_key_masked) return String(profile.api_key_masked);
        if (profile?.has_api_key) return 'Saved';
        return 'No key saved';
    }

    function keyPlaceholder(profile) {
        const cfg = defaults(profile?.provider);
        return profile?.has_api_key
            ? 'Saved API key will be kept unless you enter a new one'
            : cfg.apiKeyPlaceholder;
    }

    function keyHint(profile) {
        if (!profile?.has_api_key) return '';
        const masked = String(profile?.api_key_masked || '').trim();
        return masked
            ? `Saved key: ${masked}. Enter a new key only if you want to replace it.`
            : 'A saved API key already exists. Enter a new key only if you want to replace it.';
    }

    function renderDash() {
        const state = getState();
        const dash = state.dashboard || { profiles: [], stats: {} };

        const table = document.getElementById('ai-settings-profiles-table');
        const empty = document.getElementById('ai-settings-profiles-empty');
        const tbody = document.getElementById('ai-settings-profiles-list');
        if (!table || !empty || !tbody) return;

        const profiles = Array.isArray(dash.profiles) ? dash.profiles : [];
        if (!profiles.length) {
            table.style.display = 'none';
            empty.style.display = 'block';
            tbody.innerHTML = '';
            return;
        }

        empty.style.display = 'none';
        table.style.display = 'table';
        tbody.innerHTML = profiles.map((p) => {
            const selected = String(p.profile_key || '') === String(state.selectedProfileKey || '');
            const key = String(p.profile_key || '');
            const entry = state.testStatusByProfile?.[key] || null;
            const tone = entry?.tone === 'success'
                ? 'is-active'
                : entry?.tone === 'error'
                    ? 'is-error'
                    : '';
            const label = entry?.label || 'Not tested';
            const models = Array.isArray(p.models) && p.models.length ? p.models.join(', ') : String(p.model || '—');
            return `
                <tr data-profile-key="${escapeHtml(key)}" class="${selected ? 'is-active' : ''}">
                    <td>
                        <div class="ai-profile-name">
                            <strong>${escapeHtml(String(p.display_name || 'Untitled profile'))}</strong>
                            <span>${escapeHtml(keySummary(p))}</span>
                        </div>
                    </td>
                    <td>${escapeHtml(String(p.provider_label || p.provider || '—'))}</td>
                    <td>${escapeHtml(models)}</td>
                    <td><span class="ai-profile-chip ${tone}">${escapeHtml(label)}</span></td>
                </tr>
            `;
        }).join('');
    }

    function fillForm(profile = null) {
        const provEl = document.getElementById('plugin-ai-provider');
        const modelEl = document.getElementById('plugin-ai-model');
        const nameEl = document.getElementById('plugin-ai-display-name');
        const keyEl = document.getElementById('plugin-ai-api-key');
        const hintEl = document.getElementById('plugin-ai-api-key-saved-hint');
        const toggle = document.getElementById('plugin-ai-api-key-toggle');
        const urlEl = document.getElementById('plugin-ai-base-url');
        const models = Array.isArray(profile?.models) && profile.models.length
            ? profile.models
            : (profile?.model ? [String(profile.model)] : []);
        const provider = String(profile?.provider || 'anthropic');
        if (provEl) provEl.value = provider;
        if (modelEl) modelEl.value = '';
        if (nameEl) nameEl.value = String(profile?.display_name || '');
        if (keyEl) {
            keyEl.value = '';
            keyEl.dataset.savedPlaceholder = keyPlaceholder(profile);
            keyEl.placeholder = keyEl.dataset.savedPlaceholder;
            keyEl.type = 'password';
        }
        if (toggle) {
            toggle.setAttribute('aria-pressed', 'false');
            toggle.setAttribute('title', 'Show API key');
            toggle.setAttribute('aria-label', 'Show API key');
        }
        if (hintEl) {
            const hint = keyHint(profile);
            hintEl.dataset.savedHint = hint;
            hintEl.textContent = hint;
            hintEl.style.display = hint ? 'block' : 'none';
        }
        if (urlEl) urlEl.value = String(profile?.base_url || '');
        setModels(models);
        applyHints(provider, { preserveUrl: true });
    }

    function buildPayload() {
        const models = getModels();
        return {
            profile_key: getState().selectedProfileKey || undefined,
            display_name: String(document.getElementById('plugin-ai-display-name')?.value || '').trim() || undefined,
            provider: String(document.getElementById('plugin-ai-provider')?.value || 'anthropic').trim(),
            model: String(models[0] || '').trim(),
            models,
            api_key: String(document.getElementById('plugin-ai-api-key')?.value || '').trim() || undefined,
            base_url: String(document.getElementById('plugin-ai-base-url')?.value || '').trim() || null,
            is_active: false,
        };
    }

    function validatePayload(payload, { requireKey = false } = {}) {
        if (!Array.isArray(payload.models) || payload.models.length === 0) return 'At least one model is required.';
        if (!payload.model) return 'Provider model is required.';
        if (requireKey && !payload.api_key && payload.provider !== 'copilot') return 'API key is required for this action.';
        const prev = payload.profile_key ? findProfile(payload.profile_key) : null;
        const cur = String(payload.api_key || '').trim();
        const saved = String(prev?.api_key_masked || '').trim();
        const hasNew = cur && cur !== saved;
        if (!hasNew && !prev?.has_api_key && payload.provider !== 'copilot') {
            return 'API key is required for the first save.';
        }
        return null;
    }

    async function fetchDash() {
        const res = await fetch('/api/ai/settings');
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        return data;
    }

    async function loadDash() {
        const state = getState();
        if (state.loading) return;
        state.loading = true;
        try {
            const dash = await fetchDash();
            state.dashboard = dash;
            pruneStatuses();
            const key = state.selectedProfileKey || dash?.profiles?.[0]?.profile_key || dash?.active_profile?.profile_key || null;
            state.selectedProfileKey = key;
            renderDash();
            fillForm(findProfile(key) || dash?.active_profile || null);
        } catch (err) {
            showToast(`Failed to load AI settings: ${err.message}`, 'error');
        } finally {
            state.loading = false;
        }
    }

    async function saveProfile(event) {
        event.preventDefault();
        const payload = buildPayload();
        const err = validatePayload(payload);
        if (err) {
            showToast(err, 'warn');
            return;
        }

        const prev = payload.profile_key ? findProfile(payload.profile_key) : null;
        if (prev && payload.api_key === prev.api_key) {
            delete payload.api_key;
        }

        try {
            const res = await fetch('/api/ai/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

            const state = getState();
            state.selectedProfileKey = data.profile_key || payload.profile_key || null;
            setStatus(state.selectedProfileKey, { label: 'Testing...', tone: '' });
            await loadDash();
            showToast('AI profile saved.', 'success');
            await testConn({ silentSuccess: true });
        } catch (saveErr) {
            showToast(`Failed to save AI settings: ${saveErr.message}`, 'error');
        }
    }

    async function testConn(opts = {}) {
        const payload = buildPayload();
        const err = validatePayload(payload, { requireKey: false });
        const state = getState();
        const key = String(payload.profile_key || state.selectedProfileKey || '').trim();
        const prev = payload.profile_key ? findProfile(payload.profile_key) : null;
        if (prev && payload.api_key === prev.api_key) {
            delete payload.api_key;
        }

        if (err) {
            if (key) {
                setStatus(key, { label: 'Failed', tone: 'error' });
                renderDash();
            }
            if (!opts.silentValidation) showToast(err, 'warn');
            return false;
        }

        if (key) {
            setStatus(key, { label: 'Testing...', tone: '' });
            renderDash();
        }

        try {
            const res = await fetch('/api/ai/settings/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            const resolved = String(data.profile_key || key || '').trim();
            if (resolved) {
                setStatus(resolved, { label: 'Success', tone: 'success' });
                if (resolved !== key) delStatus(key);
                renderDash();
            }
            if (!opts.silentSuccess) showToast('AI connection test passed.', 'success');
            return true;
        } catch (testErr) {
            if (key) {
                setStatus(key, { label: 'Failed', tone: 'error' });
                renderDash();
            }
            if (!opts.silentError) showToast(`AI connection test failed: ${testErr.message}`, 'error');
            return false;
        }
    }

    function selectProfile(key) {
        const state = getState();
        state.selectedProfileKey = key;
        renderDash();
        fillForm(findProfile(key));
    }

    function bindEvents() {
        const list = document.getElementById('ai-settings-profiles-list');
        if (list && !list.dataset.bound) {
            list.addEventListener('click', (event) => {
                const row = event.target.closest('[data-profile-key]');
                if (!row) return;
                selectProfile(row.getAttribute('data-profile-key'));
            });
            list.dataset.bound = '1';
        }

        const chips = document.getElementById('ai-settings-model-chips');
        if (chips && !chips.dataset.bound) {
            chips.addEventListener('click', (event) => {
                const btn = event.target.closest('[data-model-remove]');
                if (!btn) return;
                removeModel(btn.getAttribute('data-model-remove'));
            });
            chips.dataset.bound = '1';
        }

        const form = document.getElementById('plugin-ai-settings-form');
        if (form && !form.dataset.bound) {
            form.addEventListener('submit', saveProfile);
            form.dataset.bound = '1';
        }

        const newBtn = document.getElementById('ai-settings-new-profile-btn');
        if (newBtn && !newBtn.dataset.bound) {
            newBtn.addEventListener('click', () => {
                getState().selectedProfileKey = null;
                fillForm(null);
                renderDash();
            });
            newBtn.dataset.bound = '1';
        }

        const provEl = document.getElementById('plugin-ai-provider');
        if (provEl && !provEl.dataset.bound) {
            provEl.addEventListener('change', () => {
                applyHints(provEl.value, { preserveUrl: true });
                renderChips();
            });
            provEl.dataset.bound = '1';
        }

        const modelEl = document.getElementById('plugin-ai-model');
        if (modelEl && !modelEl.dataset.bound) {
            modelEl.addEventListener('keydown', (event) => {
                if (event.key !== 'Enter') return;
                event.preventDefault();
                const val = String(modelEl.value || '').trim();
                if (!val) return;
                addModel(val);
                modelEl.value = '';
            });
            modelEl.dataset.bound = '1';
        }

        const keyToggle = document.getElementById('plugin-ai-api-key-toggle');
        if (keyToggle && !keyToggle.dataset.bound) {
            keyToggle.addEventListener('click', () => {
                const input = document.getElementById('plugin-ai-api-key');
                if (!input) return;
                const show = input.type === 'password';
                input.type = show ? 'text' : 'password';
                keyToggle.setAttribute('aria-pressed', show ? 'true' : 'false');
                keyToggle.setAttribute('title', show ? 'Hide API key' : 'Show API key');
                keyToggle.setAttribute('aria-label', show ? 'Hide API key' : 'Show API key');
            });
            keyToggle.dataset.bound = '1';
        }

        const advToggle = document.getElementById('plugin-ai-advanced-toggle');
        const advPanel = document.getElementById('plugin-ai-advanced-panel');
        const stratChip = document.getElementById('plugin-ai-runtime-strategy-chip');
        const appChip = document.getElementById('plugin-ai-runtime-approval-chip');
        const stratSel = document.getElementById('plugin-ai-strategy');
        const appSel = document.getElementById('plugin-ai-approval-mode');
        const fieldIds = [
            'plugin-ai-strategy',
            'plugin-ai-loop-mode',
            'plugin-ai-trace-enabled',
            'plugin-ai-structured-enabled',
            'plugin-ai-output-schema',
            'plugin-ai-tasks-json',
            'plugin-ai-approval-mode',
            'plugin-ai-retry-preset',
            'plugin-ai-fanout-json',
            'plugin-ai-before-run-json',
            'plugin-ai-after-run-json',
        ];
        const col = document.querySelector('.plugin-ai-chat-column');
        if (typeof window.hydratePluginAiRuntimePrefs === 'function') {
            window.hydratePluginAiRuntimePrefs();
        }
        if (typeof window.refreshPluginAiRuntimeSummary === 'function') {
            window.refreshPluginAiRuntimeSummary();
        }
        if (stratChip && !stratChip.dataset.bound) {
            stratChip.addEventListener('click', () => {
                if (typeof window.cyclePluginAiStrategy === 'function') {
                    window.cyclePluginAiStrategy();
                }
            });
            stratChip.dataset.bound = '1';
        }
        if (appChip && !appChip.dataset.bound) {
            appChip.addEventListener('click', () => {
                if (typeof window.cyclePluginAiApprovalMode === 'function') {
                    window.cyclePluginAiApprovalMode();
                }
            });
            appChip.dataset.bound = '1';
        }
        [stratSel, appSel].forEach((el) => {
            if (!el || el.dataset.summaryBound === '1') return;
            el.addEventListener('change', () => {
                if (typeof window.syncPluginAiApprovalModeUi === 'function') {
                    window.syncPluginAiApprovalModeUi();
                }
                if (typeof window.persistPluginAiRuntimePrefs === 'function') {
                    window.persistPluginAiRuntimePrefs();
                }
                if (typeof window.refreshPluginAiRuntimeSummary === 'function') {
                    window.refreshPluginAiRuntimeSummary();
                }
            });
            el.dataset.summaryBound = '1';
        });
        fieldIds.forEach((id) => {
            const el = document.getElementById(id);
            if (!el || el.dataset.runtimePersistBound === '1') return;
            const evt = el.tagName === 'TEXTAREA' || el.type === 'text' ? 'input' : 'change';
            el.addEventListener(evt, () => {
                if (typeof window.persistPluginAiRuntimePrefs === 'function') {
                    window.persistPluginAiRuntimePrefs();
                }
                if (typeof window.refreshPluginAiRuntimeSummary === 'function') {
                    window.refreshPluginAiRuntimeSummary();
                }
            });
            el.dataset.runtimePersistBound = '1';
        });
        if (advToggle && advPanel && !advToggle.dataset.bound) {
            if (col) {
                col.classList.toggle('is-advanced-open', !advPanel.hasAttribute('hidden'));
            }
            advToggle.addEventListener('click', () => {
                const open = advPanel.hasAttribute('hidden');
                if (open) {
                    advPanel.removeAttribute('hidden');
                } else {
                    advPanel.setAttribute('hidden', 'hidden');
                }
                if (col) {
                    col.classList.toggle('is-advanced-open', open);
                }
                advToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
                if (typeof window.refreshPluginAiRuntimeSummary === 'function') {
                    window.refreshPluginAiRuntimeSummary();
                }
            });
            advToggle.dataset.bound = '1';
        }
    }

    window.loadAiSettingsDashboard = loadDash;
    window.bindAiSettingsEvents = bindEvents;
})();
