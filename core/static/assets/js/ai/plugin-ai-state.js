(function() {
    function scanId() {
        return typeof window.getCurrentScanId === 'function' ? window.getCurrentScanId() : null;
    }

    function escOpt(val) {
        return String(val ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    const PENDING_KEY = 'zetatechAgentPluginAiPending';
    const EVENTS_KEY = 'zetatechAgentPluginAiLiveEvents';
    const THREAD_KEY = 'zetatechAgentPluginAiSelectedThread';
    const UI_KEY = 'zetatechAgentPluginAiThreadUi';
    const PREFS_KEY = 'zetatechAgentPluginAiRuntimePrefs';

    const DEFAULT_PREFS = {
        strategy: 'auto',
        loop_mode: '',
        trace_enabled: false,
        structured_enabled: false,
        output_schema_text: '',
        tasks_json_text: '',
        approval_mode: 'manual',
        retry_preset: '',
        fanout_json_text: '',
        before_run_json_text: '',
        after_run_json_text: '',
    };

    function normStrat(val) {
        const res = String(val || 'auto').trim().toLowerCase();
        return res || 'auto';
    }

    function allowedModes(strat = 'auto') {
        if (normStrat(strat) === 'tasks') {
            return ['manual', 'auto_approve', 'off'];
        }
        return ['manual', 'off'];
    }

    function normMode(val, strat = 'auto') {
        const res = String(val || 'manual').trim().toLowerCase();
        const ok = allowedModes(strat);
        if (ok.includes(res)) return res;
        return ok[0] || 'manual';
    }

    function syncModeUi(pref = null) {
        const stratEl = document.getElementById('plugin-ai-strategy');
        const modeEl = document.getElementById('plugin-ai-approval-mode');
        if (!modeEl) return 'manual';

        const strat = normStrat(stratEl?.value || 'auto');
        const ok = allowedModes(strat);
        const labels = {
            manual: 'Manual gate',
            auto_approve: 'Auto approve',
            off: 'Off (YOLO • Dangerous)',
        };
        const cur = pref != null ? String(pref).trim() : String(modeEl.value || '').trim();
        const mode = normMode(cur, strat);

        modeEl.innerHTML = ok
            .map((item) => `<option value="${escOpt(item)}">${escOpt(labels[item] || item)}</option>`)
            .join('');
        modeEl.value = mode;
        return mode;
    }

    function getState() {
        return window.currentPluginAi || {};
    }

    function itemKey(plugin, tid, theme = false) {
        return [
            String(plugin || '').trim(),
            String(tid || '').trim(),
            theme ? 'theme' : 'plugin',
        ].join('::');
    }

    function scopeKey(plugin, theme = false) {
        return [
            String(plugin || '').trim(),
            theme ? 'theme' : 'plugin',
        ].join('::');
    }

    function readMap(storageKey) {
        try {
            const raw = window.sessionStorage?.getItem(storageKey);
            if (!raw) return {};
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch (_) {
            return {};
        }
    }

    function writeMap(storageKey, map) {
        try {
            if (!map || typeof map !== 'object' || !window.sessionStorage) return;
            window.sessionStorage.setItem(storageKey, JSON.stringify(map));
        } catch (_) {

        }
    }

    function saveThread(plugin, tid, theme = false) {
        const key = scopeKey(plugin, theme);
        if (!key.replace(/:/g, '').trim()) return null;
        const safeId = Number(tid || 0) || null;
        const map = readMap(THREAD_KEY);
        if (!safeId) {
            delete map[key];
            writeMap(THREAD_KEY, map);
            return null;
        }
        map[key] = {
            plugin: String(plugin || '').trim(),
            threadId: safeId,
            isTheme: !!theme,
            updatedAt: new Date().toISOString(),
        };
        writeMap(THREAD_KEY, map);
        return map[key];
    }

    function getThread(plugin, theme = false) {
        const key = scopeKey(plugin, theme);
        const item = readMap(THREAD_KEY)[key] || null;
        return Number(item?.threadId || 0) || null;
    }

    function saveUiSnap(snap = {}) {
        const state = getState();
        const plugin = String(snap.plugin || state.plugin || '').trim();
        const tid = Number(snap.threadId || state.threadId || 0) || null;
        const theme = !!(snap.isTheme ?? state.isTheme);
        const key = itemKey(plugin, tid, theme);
        if (!plugin || !tid || !key.replace(/:/g, '').trim()) return null;
        const map = readMap(UI_KEY);
        map[key] = {
            plugin,
            threadId: tid,
            isTheme: theme,
            messages: Array.isArray(snap.messages) ? snap.messages : (Array.isArray(state.messages) ? state.messages : []),
            events: Array.isArray(snap.events) ? snap.events : (Array.isArray(state.events) ? state.events : []),
            liveActivity: Array.isArray(snap.liveActivity) ? snap.liveActivity : (Array.isArray(state.liveActivity) ? state.liveActivity : []),
            sending: Object.prototype.hasOwnProperty.call(snap, 'sending') ? !!snap.sending : !!state.sending,
            runStartedAt: String(snap.runStartedAt ?? state.runStartedAt ?? '').trim(),
            statusText: String(snap.statusText ?? state.statusText ?? '').trim(),
            badgeText: String(snap.badgeText ?? state.badgeText ?? '').trim(),
            sourceStatus: snap.sourceStatus && typeof snap.sourceStatus === 'object'
                ? snap.sourceStatus
                : (state.sourceStatus && typeof state.sourceStatus === 'object' ? state.sourceStatus : {}),
            pendingApproval: snap.pendingApproval && typeof snap.pendingApproval === 'object'
                ? snap.pendingApproval
                : (state.pendingApproval && typeof state.pendingApproval === 'object' ? state.pendingApproval : null),
            updatedAt: new Date().toISOString(),
        };
        writeMap(UI_KEY, map);
        return map[key];
    }

    function getUiSnap(plugin, tid, theme = false) {
        const key = itemKey(plugin, tid, theme);
        return readMap(UI_KEY)[key] || null;
    }

    function loadUiSnap(plugin, tid, theme = false) {
        const state = getState();
        const snap = getUiSnap(plugin, tid, theme);
        if (!snap) return null;
        state.plugin = String(plugin || state.plugin || '').trim();
        state.threadId = Number(tid || state.threadId || 0) || null;
        state.isTheme = !!theme;
        state.messages = Array.isArray(snap.messages) ? snap.messages : [];
        state.events = Array.isArray(snap.events) ? snap.events : [];
        state.liveActivity = Array.isArray(snap.liveActivity) ? snap.liveActivity : (Array.isArray(snap.events) ? snap.events : []);
        state.sending = !!snap.sending;
        state.runStartedAt = String(snap.runStartedAt || '').trim();
        state.statusText = String(snap.statusText || '').trim();
        state.badgeText = String(snap.badgeText || '').trim();
        state.sourceStatus = snap.sourceStatus && typeof snap.sourceStatus === 'object'
            ? snap.sourceStatus
            : (state.sourceStatus || {});
        state.pendingApproval = snap.pendingApproval && typeof snap.pendingApproval === 'object'
            ? snap.pendingApproval
            : null;
        return snap;
    }

    function syncSnap(over = {}) {
        const state = getState();
        const tid = Number(over.threadId || state.threadId || 0) || null;
        if (!tid) return null;
        return saveUiSnap({
            plugin: String(over.plugin || state.plugin || '').trim(),
            threadId: tid,
            isTheme: !!(over.isTheme ?? state.isTheme),
            messages: Array.isArray(over.messages) ? over.messages : state.messages,
            events: Array.isArray(over.events) ? over.events : state.events,
            liveActivity: Array.isArray(over.liveActivity) ? over.liveActivity : state.liveActivity,
            sending: Object.prototype.hasOwnProperty.call(over, 'sending') ? !!over.sending : !!state.sending,
            runStartedAt: Object.prototype.hasOwnProperty.call(over, 'runStartedAt') ? over.runStartedAt : state.runStartedAt,
            statusText: Object.prototype.hasOwnProperty.call(over, 'statusText') ? over.statusText : state.statusText,
            badgeText: Object.prototype.hasOwnProperty.call(over, 'badgeText') ? over.badgeText : state.badgeText,
            sourceStatus: over.sourceStatus || state.sourceStatus,
            pendingApproval: Object.prototype.hasOwnProperty.call(over, 'pendingApproval') ? over.pendingApproval : state.pendingApproval,
        });
    }

    function saveEvents(snap = {}) {
        const state = getState();
        const key = itemKey(snap.plugin || state.plugin, snap.threadId || state.threadId, snap.isTheme ?? state.isTheme);
        if (!key.replace(/:/g, '').trim()) return null;
        const events = Array.isArray(snap.events) ? snap.events : [];
        const map = readMap(EVENTS_KEY);
        map[key] = {
            plugin: String(snap.plugin || state.plugin || '').trim(),
            threadId: Number(snap.threadId || state.threadId || 0) || null,
            isTheme: !!(snap.isTheme ?? state.isTheme),
            events,
            createdAt: String(snap.createdAt || new Date().toISOString()),
        };
        writeMap(EVENTS_KEY, map);
        return map[key];
    }

    function getEvents(plugin, tid, theme = false) {
        const key = itemKey(plugin, tid, theme);
        return readMap(EVENTS_KEY)[key] || null;
    }

    function clearEvents(plugin, tid, theme = false) {
        const key = itemKey(plugin, tid, theme);
        const map = readMap(EVENTS_KEY);
        if (!Object.prototype.hasOwnProperty.call(map, key)) return;
        delete map[key];
        writeMap(EVENTS_KEY, map);
    }

    function savePending(snap = {}) {
        const state = getState();
        const key = itemKey(snap.plugin || state.plugin, snap.threadId || state.threadId, snap.isTheme ?? state.isTheme);
        if (!key.replace(/:/g, '').trim()) return null;
        const map = readMap(PENDING_KEY);
        map[key] = {
            plugin: String(snap.plugin || state.plugin || '').trim(),
            threadId: Number(snap.threadId || state.threadId || 0) || null,
            isTheme: !!(snap.isTheme ?? state.isTheme),
            content: String(snap.content || '').trim(),
            createdAt: String(snap.createdAt || new Date().toISOString()),
        };
        writeMap(PENDING_KEY, map);
        return map[key];
    }

    function getPending(plugin, tid, theme = false) {
        const key = itemKey(plugin, tid, theme);
        return readMap(PENDING_KEY)[key] || null;
    }

    function clearPending(plugin, tid, theme = false) {
        const key = itemKey(plugin, tid, theme);
        const map = readMap(PENDING_KEY);
        if (!Object.prototype.hasOwnProperty.call(map, key)) return;
        delete map[key];
        writeMap(PENDING_KEY, map);
    }

    function beginView(slug, theme = false) {
        const state = getState();
        state.plugin = String(slug || '').trim();
        state.isTheme = !!theme;
        state.threadId = null;
        state.threads = [];
        state.messages = [];
        state.events = [];
        state.liveActivity = [];
        state.loading = false;
        state.sending = false;
        state.sourcePreparing = false;
        state.streamRequestId = null;
        state.streamThreadId = null;
        state.pendingSnapshotRetryInFlight = false;
        state.runStartedAt = '';
        state.statusText = '';
        state.badgeText = '';
        state.sourceStatus = {
            source_available: false,
            source_context_mode: 'metadata_only',
            source_path: '',
            workspace_path: '',
        };
        if (typeof window.stopPluginAiPendingRunPoll === 'function') {
            window.stopPluginAiPendingRunPoll();
        }
        if (typeof window.stopPluginAiThreadSyncPoll === 'function') {
            window.stopPluginAiThreadSyncPoll();
        }
        state.viewToken = (Number(state.viewToken) || 0) + 1;
        if (typeof window.updatePluginAiSessionUi === 'function') {
            window.updatePluginAiSessionUi();
        }
        return state.viewToken;
    }

    function samePlugin(plugin, state) {
        const slug = String(plugin?.slug || '').trim();
        return state.plugin === slug && state.isTheme === !!plugin?.is_theme;
    }

    function isView(slug, token) {
        const state = getState();
        return state.plugin === String(slug || '').trim() && state.viewToken === token;
    }

    function ignoreRes(slug, token, tid) {
        const state = getState();
        return !isView(slug, token) || Number(state.threadId || 0) !== Number(tid || 0);
    }

    function clearTransient(state) {
        state.messages = [];
        state.events = [];
        state.liveActivity = [];
        state.streamRequestId = null;
        state.streamThreadId = null;
        state.pendingSnapshotRetryInFlight = false;
        state.liveActivityOptions = {};
        state.ui = {
            activityExpanded: false,
            summaryExpanded: false,
            traceExpanded: false,
        };
    }

    function ensureUi() {
        const state = getState();
        if (!state.ui || typeof state.ui !== 'object') {
            state.ui = {
                activityExpanded: false,
                summaryExpanded: false,
                traceExpanded: false,
            };
        }
        return state.ui;
    }

    function toggleFlag(key) {
        const ui = ensureUi();
        ui[key] = !ui[key];
        return ui[key];
    }

    function setFlag(key, val) {
        const ui = ensureUi();
        ui[key] = !!val;
        return ui[key];
    }

    function setActivityOpts(opts = {}) {
        const state = getState();
        state.liveActivityOptions = opts && typeof opts === 'object' ? { ...opts } : {};
        return state.liveActivityOptions;
    }

    function beginReq(tid = null) {
        const state = getState();
        const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        state.streamRequestId = id;
        state.streamThreadId = Number(tid || state.threadId || 0) || null;
        return id;
    }

    function isReq(id) {
        return String(getState().streamRequestId || '') === String(id || '');
    }

    function endReq(id) {
        const state = getState();
        if (!id || isReq(id)) {
            state.streamRequestId = null;
            state.streamThreadId = null;
        }
    }

    function resetThread(plugin) {
        const state = getState();
        state.plugin = String(plugin?.slug || '').trim();
        state.isTheme = !!plugin?.is_theme;
        state.threadId = null;
        state.threads = [];
        clearTransient(state);
        if (typeof window.updatePluginAiSessionUi === 'function') {
            window.updatePluginAiSessionUi();
        }
    }

    function startView(plugin) {
        const token = beginView(String(plugin?.slug || '').trim(), !!plugin?.is_theme);
        resetThread(plugin);
        return token;
    }

    function threadReq(plugin) {
        return {
            plugin_slug: String(plugin?.slug || '').trim(),
            is_theme: !!plugin?.is_theme,
            title: null,
            last_scan_session_id: scanId() || null,
        };
    }

    function parseJson(id, label, fallback = null) {
        const raw = String(document.getElementById(id)?.value || '').trim();
        if (!raw) return fallback;
        try {
            return JSON.parse(raw);
        } catch (_) {
            throw new Error(`${label} must be valid JSON.`);
        }
    }

    function applyRetry(tasks = [], preset = '') {
        const key = String(preset || '').trim();
        if (!key || !Array.isArray(tasks) || !tasks.length) return tasks;
        const map = {
            light: { maxRetries: 1, retryDelayMs: 750, retryBackoff: 1.5 },
            normal: { maxRetries: 2, retryDelayMs: 1000, retryBackoff: 2 },
            aggressive: { maxRetries: 3, retryDelayMs: 1500, retryBackoff: 2 },
        };
        const cfg = map[key];
        if (!cfg) return tasks;
        return tasks.map((task) => ({ ...task, ...cfg, ...(task && typeof task === 'object' ? task : {}) }));
    }

    function loadPrefs() {
        try {
            const raw = window.localStorage?.getItem(PREFS_KEY);
            if (!raw) return { ...DEFAULT_PREFS };
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object'
                ? { ...DEFAULT_PREFS, ...parsed }
                : { ...DEFAULT_PREFS };
        } catch (_) {
            return { ...DEFAULT_PREFS };
        }
    }

    function collectPrefs() {
        const strategy = normStrat(document.getElementById('plugin-ai-strategy')?.value || DEFAULT_PREFS.strategy);
        const approval = normMode(
            document.getElementById('plugin-ai-approval-mode')?.value || DEFAULT_PREFS.approval_mode,
            strategy,
        );
        return {
            strategy,
            loop_mode: String(document.getElementById('plugin-ai-loop-mode')?.value || DEFAULT_PREFS.loop_mode).trim(),
            trace_enabled: !!document.getElementById('plugin-ai-trace-enabled')?.checked,
            structured_enabled: !!document.getElementById('plugin-ai-structured-enabled')?.checked,
            output_schema_text: String(document.getElementById('plugin-ai-output-schema')?.value || '').trim(),
            tasks_json_text: String(document.getElementById('plugin-ai-tasks-json')?.value || '').trim(),
            approval_mode: approval,
            retry_preset: String(document.getElementById('plugin-ai-retry-preset')?.value || '').trim(),
            fanout_json_text: String(document.getElementById('plugin-ai-fanout-json')?.value || '').trim(),
            before_run_json_text: String(document.getElementById('plugin-ai-before-run-json')?.value || '').trim(),
            after_run_json_text: String(document.getElementById('plugin-ai-after-run-json')?.value || '').trim(),
        };
    }

    function savePrefs() {
        try {
            const prefs = collectPrefs();
            window.localStorage?.setItem(PREFS_KEY, JSON.stringify(prefs));
            return prefs;
        } catch (_) {
            return null;
        }
    }

    function applyPrefs(prefs = null) {
        const safe = prefs && typeof prefs === 'object'
            ? { ...DEFAULT_PREFS, ...prefs }
            : loadPrefs();
        safe.strategy = normStrat(safe.strategy || 'auto');
        safe.approval_mode = normMode(safe.approval_mode || 'manual', safe.strategy);
        const map = [
            ['plugin-ai-strategy', safe.strategy],
            ['plugin-ai-loop-mode', safe.loop_mode],
            ['plugin-ai-output-schema', safe.output_schema_text],
            ['plugin-ai-tasks-json', safe.tasks_json_text],
            ['plugin-ai-retry-preset', safe.retry_preset],
            ['plugin-ai-fanout-json', safe.fanout_json_text],
            ['plugin-ai-before-run-json', safe.before_run_json_text],
            ['plugin-ai-after-run-json', safe.after_run_json_text],
        ];
        map.forEach(([id, val]) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.value = val ?? '';
        });
        safe.approval_mode = syncModeUi(safe.approval_mode || 'manual');
        const traceEl = document.getElementById('plugin-ai-trace-enabled');
        if (traceEl) traceEl.checked = !!safe.trace_enabled;
        const structEl = document.getElementById('plugin-ai-structured-enabled');
        if (structEl) structEl.checked = !!safe.structured_enabled;
        const state = getState();
        state.runtimeOverrides = {
            strategy: safe.strategy || 'auto',
            trace_enabled: !!safe.trace_enabled,
            output_schema: null,
            tasks: [],
            fanout: null,
            loop_detection: safe.loop_mode
                ? {
                    maxRepetitions: 3,
                    loopDetectionWindow: 5,
                    onLoopDetected: safe.loop_mode,
                }
                : null,
            approval_mode: safe.approval_mode || 'manual',
        };
        return safe;
    }

    function hydratePrefs() {
        const prefs = applyPrefs(loadPrefs());
        if (typeof window.refreshPluginAiRuntimeSummary === 'function') {
            window.refreshPluginAiRuntimeSummary();
        }
        return prefs;
    }

    function readOverrides() {
        const strategy = normStrat(document.getElementById('plugin-ai-strategy')?.value || 'auto');
        const trace = !!document.getElementById('plugin-ai-trace-enabled')?.checked;
        const structured = !!document.getElementById('plugin-ai-structured-enabled')?.checked;
        const loop = String(document.getElementById('plugin-ai-loop-mode')?.value || '').trim();
        const approval = normMode(document.getElementById('plugin-ai-approval-mode')?.value || 'manual', strategy);
        const retry = String(document.getElementById('plugin-ai-retry-preset')?.value || '').trim();
        const schema = structured
            ? parseJson('plugin-ai-output-schema', 'Output schema', { type: 'object', properties: { summary: { type: 'string' } } })
            : null;
        const rawTasks = parseJson('plugin-ai-tasks-json', 'Tasks JSON', []);
        const tasks = applyRetry(Array.isArray(rawTasks) ? rawTasks : [], retry);
        const fanout = parseJson('plugin-ai-fanout-json', 'Fanout JSON', null);
        const before = parseJson('plugin-ai-before-run-json', 'Before-run hook JSON', null);
        const after = parseJson('plugin-ai-after-run-json', 'After-run hook JSON', null);
        const loopCfg = loop
            ? {
                maxRepetitions: 3,
                loopDetectionWindow: 5,
                onLoopDetected: loop,
            }
            : null;
        const over = {
            strategy,
            trace_enabled: trace,
            output_schema: schema,
            tasks,
            fanout: fanout && typeof fanout === 'object' ? fanout : null,
            loop_detection: loopCfg,
            approval_mode: approval,
            before_run: before && typeof before === 'object' ? before : null,
            after_run: after && typeof after === 'object' ? after : null,
        };
        const state = getState();
        state.runtimeOverrides = over;
        return over;
    }

    function stratLabel(val) {
        const key = String(val || 'auto').trim().toLowerCase();
        const labels = {
            auto: 'Auto',
            agent: 'Agent',
            team: 'Team',
            tasks: 'Tasks',
            fanout: 'Fan-out',
        };
        return labels[key] || 'Auto';
    }

    function approvalLabel(val) {
        const key = String(val || 'manual').trim().toLowerCase();
        const labels = {
            off: 'Off (YOLO • Dangerous)',
            auto_approve: 'Auto',
            manual: 'Manual',
        };
        return labels[key] || 'Manual';
    }

    function stratTip(val) {
        const key = String(val || 'auto').trim().toLowerCase();
        const desc = {
            auto: 'Auto picks the best execution style for the prompt.',
            agent: 'Single agent uses one focused AI worker.',
            team: 'Team uses multiple collaborating AI roles.',
            tasks: 'Tasks runs a step-by-step task pipeline.',
            fanout: 'Fan-out runs parallel branches and combines results.',
        };
        return `Strategy: ${stratLabel(key)}. ${desc[key] || desc.auto} Click to change.`;
    }

    function approvalTip(val, strat = 'auto') {
        const key = String(val || 'manual').trim().toLowerCase();
        const normS = normStrat(strat);
        const desc = {
            manual: 'The run pauses and asks for your approval before gated steps continue.',
            auto_approve: 'Approval checks are accepted automatically.',
            off: 'YOLO mode: no approval pause is used. This is dangerous because risky tool calls (write/edit/bash/network/delete) can run immediately without a human checkpoint.',
        };
        const tail = normS === 'tasks'
            ? 'Click to change.'
            : 'Click to change. (Auto approve is available only for Task pipeline.)';
        return `Approval: ${approvalLabel(key)}. ${desc[key] || desc.manual} ${tail}`;
    }

    function refreshSummary() {
        const stratEl = document.getElementById('plugin-ai-strategy');
        const appEl = document.getElementById('plugin-ai-approval-mode');
        const stratChip = document.getElementById('plugin-ai-runtime-strategy-chip');
        const appChip = document.getElementById('plugin-ai-runtime-approval-chip');
        const strat = normStrat(stratEl?.value || 'auto');
        const app = syncModeUi(appEl?.value || 'manual');
        if (stratChip) {
            stratChip.textContent = stratLabel(strat);
            stratChip.dataset.strategy = strat;
            stratChip.dataset.tooltip = stratTip(strat);
            stratChip.setAttribute('aria-label', stratTip(strat));
        }
        if (appChip) {
            appChip.textContent = approvalLabel(app);
            appChip.dataset.approval = app;
            appChip.dataset.tooltip = approvalTip(app, strat);
            appChip.setAttribute('aria-label', approvalTip(app, strat));
        }
    }

    function cycleStrat() {
        const el = document.getElementById('plugin-ai-strategy');
        if (!el) return;
        const order = ['auto', 'team', 'agent', 'tasks', 'fanout'];
        const idx = Math.max(0, order.indexOf(String(el.value || 'auto').trim()));
        el.value = order[(idx + 1) % order.length];
        syncModeUi();
        if (typeof window.persistPluginAiRuntimePrefs === 'function') {
            window.persistPluginAiRuntimePrefs();
        }
        refreshSummary();
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function cycleMode() {
        const stratEl = document.getElementById('plugin-ai-strategy');
        const appEl = document.getElementById('plugin-ai-approval-mode');
        if (!appEl) return;
        const strat = normStrat(stratEl?.value || 'auto');
        const order = allowedModes(strat);
        const idx = Math.max(0, order.indexOf(String(appEl.value || 'manual').trim()));
        appEl.value = order[(idx + 1) % order.length];
        if (typeof window.persistPluginAiRuntimePrefs === 'function') {
            window.persistPluginAiRuntimePrefs();
        }
        refreshSummary();
        appEl.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function buildPayload({ threadId: tid, content }) {
        const state = getState();
        return {
            thread_id: tid,
            content,
            last_scan_session_id: scanId() || null,
            plugin_slug: String(state.plugin || '').trim() || undefined,
            is_theme: !!state.isTheme,
            profile_key: String(state.selectedProfileKey || '').trim() || undefined,
            model: String(state.selectedModel || '').trim() || undefined,
            ...readOverrides(),
        };
    }

    function firstThreadId(threads = []) {
        const first = Array.isArray(threads) ? threads[0] : null;
        return first && first.id ? first.id : null;
    }

    function saveActiveThread(data = {}) {
        const state = getState();
        state.threadId = data.id || null;
        state.isTheme = !!data.is_theme;
        state.sourceStatus = {
            source_available: !!data.source_available,
            source_context_mode: String(data.source_context_mode || 'metadata_only'),
            source_path: String(data.source_path || ''),
            workspace_path: String(data.workspace_path || ''),
        };
        saveThread(String(data.plugin_slug || state.plugin || '').trim(), state.threadId, !!state.isTheme);
    }

    function saveThreads(threads = []) {
        const state = getState();
        state.threads = Array.isArray(threads) ? threads : [];
    }

    function getAiConfig() {
        return window.currentAiConfig || {};
    }

    function syncProfiles() {
        const state = getState();
        const profiles = Array.isArray(state.profiles) ? state.profiles : [];
        const active = window.currentAiConfig || null;
        const prefKey = String(state.selectedProfileKey || active?.profile_key || profiles[0]?.profile_key || '').trim();
        const profile = profiles.find((item) => String(item.profile_key || '') === prefKey) || active || profiles[0] || null;
        state.selectedProfileKey = profile ? String(profile.profile_key || '').trim() : null;

        const models = Array.isArray(profile?.models) && profile.models.length
            ? profile.models
            : (profile?.model ? [String(profile.model)] : []);
        const prefModel = String(state.selectedModel || profile?.model || models[0] || '').trim();
        state.selectedModel = models.includes(prefModel) ? prefModel : (models[0] || null);
        return { selectedProfile: profile, models };
    }

    function renderProfiles() {
        const state = getState();
        const sel = document.getElementById('plugin-ai-profile-model-select');
        if (!sel) return;

        const profiles = Array.isArray(state.profiles) ? state.profiles : [];
        const { selectedProfile } = syncProfiles();
        const curKey = String(state.selectedProfileKey || selectedProfile?.profile_key || '').trim();
        const curModel = String(state.selectedModel || '').trim();

        const opts = [];
        profiles.forEach((profile) => {
            const pKey = String(profile.profile_key || '').trim();
            const pModels = Array.isArray(profile.models) && profile.models.length
                ? profile.models
                : (profile?.model ? [String(profile.model)] : []);
            pModels.forEach((model) => {
                const mVal = String(model || '').trim();
                if (!pKey || !mVal) return;
                const val = `${pKey}::${mVal}`;
                const picked = pKey === curKey && mVal === curModel ? ' selected' : '';
                opts.push(`<option value="${escOpt(val)}"${picked}>${escOpt(mVal)}</option>`);
            });
        });

        sel.innerHTML = opts.length ? opts.join('') : '<option value="">No models found</option>';

        const streaming = !!state.sending
            && Number(state.streamThreadId || 0) === Number(state.threadId || 0)
            && !!String(state.streamRequestId || '').trim();
        sel.disabled = opts.length === 0 || state.loading || streaming;
    }

    function updateSelections(part = {}) {
        const state = getState();
        if (Object.prototype.hasOwnProperty.call(part, 'profiles')) {
            state.profiles = Array.isArray(part.profiles) ? part.profiles : [];
        }
        if (Object.prototype.hasOwnProperty.call(part, 'selectedProfileKey')) {
            state.selectedProfileKey = part.selectedProfileKey ? String(part.selectedProfileKey).trim() : null;
        }
        if (Object.prototype.hasOwnProperty.call(part, 'selectedModel')) {
            state.selectedModel = part.selectedModel ? String(part.selectedModel).trim() : null;
        }
        renderProfiles();
    }

    window.getPluginAiState = getState;
    window.beginPluginAiView = beginView;
    window.currentPluginMatchesState = samePlugin;
    window.isPluginAiViewCurrent = isView;
    window.shouldIgnorePluginAiResponse = ignoreRes;
    window.clearPluginAiTransientState = clearTransient;
    window.beginPluginAiStreamRequest = beginReq;
    window.isCurrentPluginAiStreamRequest = isReq;
    window.endPluginAiStreamRequest = endReq;
    window.setPluginAiLiveActivityOptions = setActivityOpts;
    window.ensurePluginAiUiState = ensureUi;
    window.togglePluginAiUiFlag = toggleFlag;
    window.setPluginAiUiFlag = setFlag;
    window.rememberPluginAiEventsSnapshot = saveEvents;
    window.getPluginAiEventsSnapshot = getEvents;
    window.clearPluginAiEventsSnapshot = clearEvents;
    window.rememberPluginAiPendingSnapshot = savePending;
    window.getPluginAiPendingSnapshot = getPending;
    window.clearPluginAiPendingSnapshot = clearPending;
    window.rememberPluginAiSelectedThread = saveThread;
    window.getPluginAiSelectedThread = getThread;
    window.rememberPluginAiThreadUiSnapshot = saveUiSnap;
    window.getPluginAiThreadUiSnapshot = getUiSnap;
    window.hydratePluginAiThreadUiSnapshot = loadUiSnap;
    window.syncCurrentPluginAiThreadSnapshot = syncSnap;
    window.resetPluginAiThreadState = resetThread;
    window.startPluginAiView = startView;
    window.buildPluginThreadRequest = threadReq;
    window.readPluginAiRuntimeOverrides = readOverrides;
    window.persistPluginAiRuntimePrefs = savePrefs;
    window.hydratePluginAiRuntimePrefs = hydratePrefs;
    window.applyPluginAiRuntimePrefsToDom = applyPrefs;
    window.refreshPluginAiRuntimeSummary = refreshSummary;
    window.syncPluginAiApprovalModeUi = syncModeUi;
    window.cyclePluginAiStrategy = cycleStrat;
    window.cyclePluginAiApprovalMode = cycleMode;
    window.buildPluginAiMessagePayload = buildPayload;
    window.resolvePreferredPluginAiThreadId = firstThreadId;
    window.rememberPluginAiThread = saveActiveThread;
    window.rememberPluginAiThreads = saveThreads;
    window.extractCurrentAiConfig = getAiConfig;
    window.syncPluginAiProfileSelections = syncProfiles;
    window.renderPluginAiComposerProfiles = renderProfiles;
    window.updatePluginAiComposerSelections = updateSelections;
})();
